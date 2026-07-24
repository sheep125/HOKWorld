"""月卡弹窗检测与关闭。

独立模块,可在实时检测、自动登录等阶段并行运行。
检测策略:截取游戏客户区,用 OCR 识别"汐月之礼"等月卡特征,
确认弹窗后优先点击"点击空白处继续";若 OCR 找不到该文字,
则退回到点击屏幕中间弹窗卡片外的空白区域(游戏内任意空白处均可关闭)。

为什么不用时间窗口:用户截图说明月卡界面"游戏界面出现后一会出现",并不固定在某个小时,
所以本模块不依赖 monthly_card_hour 配置,只依赖 monthly_card_check 总开关。
"""
from __future__ import annotations

import time

import numpy as np

from runtime_guard import dev_log, safe_click_norm
from winenv import activate_game_window, find_game_hwnd

# 月卡弹窗特征关键字(出现任意一个即认为弹窗)
KEYWORDS = ("汐月之礼", "晶珀", "剩余", "月之礼")
# 关闭按钮文字
CLOSE_TEXT = "点击空白处继续"
# 获得奖励画面关键字
REWARD_KEYWORDS = ("获得奖励", "元流经验", "点击空白处继续")
# 弹窗检测 ROI:覆盖整个月卡/奖励卡片(含顶部标题和底部关闭文字)
POPUP_ROI = (0.15, 0.15, 0.85, 0.90)
# 底部关闭文字专用 ROI(当全区域没找到时,再专门扫底部)
BOTTOM_ROI = (0.10, 0.70, 0.90, 0.95)
# OCR 最低置信度(月卡弹窗文字偏艺术字体,适当放宽)
MIN_CONF = 0.35
# 弹窗卡片外、可安全点击的空白区域候选位置(归一化 x,y)
# 选左下/右下/左中/右中,避开中央卡片和常见 HUD 角落
FALLBACK_POSITIONS = (
    (0.12, 0.85),   # 左下空白
    (0.88, 0.85),   # 右下空白
    (0.10, 0.50),   # 左中空白
    (0.90, 0.50),   # 右中空白
)


class MonthlyCardHandler:
    """常驻检测月卡弹窗,出现后点击关闭文字或空白处关闭。"""

    TICK = 2.0          # 检测间隔(秒)
    TIMEOUT = 300.0     # 单次最长检测时间(防无限挂起)
    DEBOUNCE = 5.0      # 关闭后多久不再重复触发
    MAX_RETRY = 2       # 点击后最多验证几次(防点击失效)

    def __init__(self, log=print, on_popup_closed=None) -> None:
        self.log = log
        self.stop_flag = False
        self.paused = False
        self._last_closed = 0.0
        self.on_popup_closed = on_popup_closed  # 弹窗关闭时回调(无参数,用于联动重启)

    def stop(self):
        self.stop_flag = True

    def set_paused(self, on: bool):
        self.paused = on

    def _stopped(self) -> bool:
        return bool(self.stop_flag)

    def _ocr_detect(self, frame: np.ndarray, roi: tuple):
        """OCR 指定 ROI,返回 (拼接文字, 识别项列表)。
        roi = (x0, y0, x1, y1) 为归一化坐标。
        识别项: [(text, confidence, (norm_x, norm_y)), ...],坐标已归一化到整帧。
        转发到 ocr_utils.ocr_items(月卡 MIN_CONF=0.35,比通用 0.5 松,适配艺术字体)。"""
        from ocr_utils import ocr_items
        items = ocr_items(frame, roi, MIN_CONF)
        return "".join(t[0] for t in items), items

    def _find_close_position(self, items: list) -> tuple[float, float] | None:
        """从 OCR 结果中找到"点击空白处继续"的位置,返回归一化坐标(x,y)或 None。"""
        best = None
        best_conf = 0.0
        for text, conf, pos in items:
            if not pos:
                continue
            if CLOSE_TEXT in text and conf > best_conf:
                best, best_conf = pos, conf
        if best:
            return best
        # 备选:找不到完整文字时,尝试找"空白处"或"继续"等片段
        for text, conf, pos in items:
            if pos and ("空白处" in text or ("继续" in text and len(text) <= 4)):
                return pos
        return None

    def _is_popup(self, full_text: str) -> bool:
        """判断当前帧是否为月卡弹窗(或获得奖励等需要关闭的界面)。"""
        if len(full_text) < 2:
            return False
        # 月卡关键字
        if any(kw in full_text for kw in KEYWORDS):
            return True
        # 获得奖励关键字
        if "获得奖励" in full_text or "元流经验" in full_text:
            return True
        return False

    def _click_continue(self, hwnd: int, pos: tuple[float, float]) -> bool:
        """在游戏客户区指定归一化坐标处点击。"""
        try:
            return safe_click_norm(hwnd, pos, self._stopped, None, self.log, 0.05)
        except Exception as exc:
            dev_log("月卡点击失败", exc)
            self.log(f"[月卡] 点击失败: {exc}")
            return False

    def _click_blank_area(self, hwnd: int) -> bool:
        """点击屏幕中央弹窗卡片外的空白区域。逐个尝试候选位置。"""
        for pos in FALLBACK_POSITIONS:
            if self.stop_flag:
                return False
            self.log(f"[月卡] 尝试点击空白处(归一化坐标: {pos[0]:.3f}, {pos[1]:.3f})")
            if self._click_continue(hwnd, pos):
                return True
            time.sleep(0.2)
        return False

    def run(self) -> bool:
        """开始常驻检测,直到 stop_flag=True 或超时。返回是否成功关闭过一次。"""
        self.stop_flag = False
        self._last_closed = 0.0
        closed_once = False
        deadline = time.time() + self.TIMEOUT

        self.log("[月卡] 开始常驻检测(OCR定位→点击关闭)…")
        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.5)
                continue

            # 截图 + OCR 不需要前台,不抢焦点(用户可能在用别的程序)
            # → 只在确认弹窗、准备点击时才激活(见下方)
            hwnd = find_game_hwnd()
            if not hwnd:
                time.sleep(2)
                continue

            # 截图
            frame = self._grab(hwnd)
            if frame is None or frame.size == 0:
                time.sleep(self.TICK)
                continue

            # 1) 全弹窗区域 OCR
            full_text, items = self._ocr_detect(frame, POPUP_ROI)

            if not self._is_popup(full_text):
                time.sleep(self.TICK)
                continue

            # 去重:刚关闭过,短时间内不再触发
            if time.time() - self._last_closed < self.DEBOUNCE:
                time.sleep(self.TICK)
                continue

            # 2) 先在整个弹窗区域找关闭文字
            click_pos = self._find_close_position(items)

            # 3) 没找到 → 再专门扫底部区域
            if click_pos is None:
                _, bottom_items = self._ocr_detect(frame, BOTTOM_ROI)
                click_pos = self._find_close_position(bottom_items)

            # 4) 还是没找到 → 退回到点击空白处
            use_blank_fallback = False
            if click_pos is None:
                self.log("[月卡] 检测到弹窗,但未定位到关闭文字,将点击空白处关闭")
                use_blank_fallback = True

            for retry in range(self.MAX_RETRY):
                if self.stop_flag:
                    break

                # 弹窗已确认 → 点击前才激活窗口(让 safe_click_norm 守卫通过)
                activate_game_window(self.log)

                if use_blank_fallback:
                    ok = self._click_blank_area(hwnd)
                else:
                    self.log(f"[月卡] 检测到弹窗,点击关闭文字(归一化坐标: {click_pos[0]:.3f}, {click_pos[1]:.3f})")
                    ok = self._click_continue(hwnd, click_pos)

                if not ok:
                    self.log(f"[月卡] 点击失败(第{retry + 1}次重试)")
                    time.sleep(0.3)
                    continue

                time.sleep(0.5)
                # 验证:截图确认弹窗是否已关闭
                verify_frame = self._grab(hwnd)
                if verify_frame is not None:
                    verify_text, _ = self._ocr_detect(verify_frame, POPUP_ROI)
                    if not self._is_popup(verify_text):
                        self.log("[月卡] 弹窗已关闭 ✓")
                        self._last_closed = time.time()
                        closed_once = True
                        # 通知外部:弹窗已关闭(用于浇水联动重启等)
                        try:
                            if self.on_popup_closed:
                                self.on_popup_closed()
                        except Exception:
                            pass
                        break
                    else:
                        self.log(f"[月卡] 弹窗仍在(第{retry + 1}次重试),再次点击…")
                        continue
                else:
                    # 截图失败,假定成功
                    self._last_closed = time.time()
                    closed_once = True
                    break

            time.sleep(2)

        self.log("[月卡] 检测结束")
        return closed_once

    def _grab(self, hwnd: int) -> np.ndarray | None:
        """截图游戏客户区(用 with 上下文管理,确保 GDI 资源释放)。"""
        try:
            from capture import GameCapture
            with GameCapture(hwnd) as cap:
                return cap.grab()
        except Exception as exc:
            dev_log("月卡截图失败", exc)
            return None
