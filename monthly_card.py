"""月卡弹窗检测与关闭。

独立模块,可在实时检测、自动登录等阶段并行运行。
检测策略:截取游戏客户区中央区域,用 OCR 识别"汐月之礼""晶珀""剩余"等关键字,
命中即认为出现月卡弹窗,连续按两下 ESC 关闭。

为什么不用时间窗口:用户截图说明月卡界面"游戏界面出现后一会出现",并不固定在某个小时,
所以本模块不依赖 monthly_card_hour 配置,只依赖 monthly_card_check 总开关。
"""
from __future__ import annotations

import time

import cv2
import numpy as np

from fishing.matcher import _get_ocr
from runtime_guard import dev_log, safe_press_key
from winenv import activate_game_window, find_game_hwnd

# 月卡弹窗特征关键字(出现任意一个即认为弹窗)
KEYWORDS = ("汐月之礼", "晶珀", "剩余", "月之礼", "点击空白处继续")
# 检测 ROI:中央区域(避开边缘 HUD,专注弹窗卡片)
ROI_CENTER = (0.25, 0.20, 0.75, 0.75)
# OCR 最低置信度
MIN_CONF = 0.45


class MonthlyCardHandler:
    """常驻检测月卡弹窗,出现后按两下 ESC。"""

    TICK = 2.0          # 检测间隔(秒)
    TIMEOUT = 300.0     # 单次最长检测时间(防无限挂起)
    DEBOUNCE = 5.0      # 关闭后多久不再重复触发

    def __init__(self, log=print) -> None:
        self.log = log
        self.stop_flag = False
        self.paused = False
        self._last_closed = 0.0

    def stop(self):
        self.stop_flag = True

    def set_paused(self, on: bool):
        self.paused = on

    def _stopped(self) -> bool:
        return bool(self.stop_flag)

    def _foreground(self) -> bool:
        # 月卡检测不强求前台,后台发现也尝试按 ESC(ESC 通常能被系统转发到前台游戏)
        return True

    def _press_esc(self) -> None:
        try:
            safe_press_key(0x1B, self._stopped, self._foreground, None, 0.05)
        except Exception as exc:
            dev_log("月卡 ESC 失败", exc)

    def _ocr_text(self, frame: np.ndarray) -> str:
        """OCR 指定 ROI,返回拼接文字。"""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = ROI_CENTER
        sub = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if sub.size == 0:
            return ""
        try:
            res, _ = _get_ocr()(sub)
        except Exception:
            return ""
        parts = []
        for it in (res or []):
            try:
                if float(it[2]) >= MIN_CONF:
                    parts.append(str(it[1]))
            except (TypeError, ValueError):
                parts.append(str(it[1]))
        return "".join(parts)

    def _is_monthly_card(self, frame: np.ndarray) -> bool:
        """判断当前帧是否为月卡弹窗。"""
        if frame is None or frame.size == 0:
            return False
        txt = self._ocr_text(frame)
        if not txt:
            return False
        # 需要至少命中一个关键字,且整体不是纯 HUD 文字(简单长度过滤)
        if len(txt) < 2:
            return False
        return any(kw in txt for kw in KEYWORDS)

    def run(self) -> bool:
        """开始常驻检测,直到 stop_flag=True 或超时。返回是否成功关闭过一次。"""
        self.stop_flag = False
        self._last_closed = 0.0
        closed_once = False
        deadline = time.time() + self.TIMEOUT

        self.log("[月卡] 开始常驻检测…")
        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.5)
                continue

            # 尽量激活游戏窗口,让后续按键有效
            activate_game_window(self.log)
            hwnd = find_game_hwnd()
            if not hwnd:
                time.sleep(2)
                continue

            # 截图(优先用 capture.GameCapture,失败回退全屏)
            frame = self._grab(hwnd)
            if frame is not None and self._is_monthly_card(frame):
                # 去重:如果刚刚关闭过,短时间内不再触发
                if time.time() - self._last_closed < self.DEBOUNCE:
                    time.sleep(self.TICK)
                    continue
                self.log("[月卡] 检测到月卡弹窗(汐月之礼),按两下 ESC 关闭")
                self._press_esc()
                time.sleep(0.3)
                self._press_esc()
                self._last_closed = time.time()
                closed_once = True
                self.log("[月卡] 已发送 ESC*2,继续监控…")
                time.sleep(2)
                continue

            time.sleep(self.TICK)

        self.log("[月卡] 检测结束")
        return closed_once

    def _grab(self, hwnd: int) -> np.ndarray | None:
        """截图游戏客户区。"""
        try:
            from capture import GameCapture
            cap = GameCapture(hwnd)
            cap.start()
            return cap.grab()
        except Exception as exc:
            dev_log("月卡截图失败", exc)
            return None
