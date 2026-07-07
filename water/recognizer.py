"""浇水模块 — 视觉识别:OCR 检测好友列表、浇水按钮、传送确认、已浇水田地等。

基于 MaaHKWorld farmforfriends.json 流水线翻译为键鼠操作。
所有识别基于 client_rect_on_screen + OCR/template matching。
"""
from __future__ import annotations

import time
from capture import NORM_W

import cv2
import numpy as np

from capture import GameCapture
from fishing.matcher import _get_ocr
from runtime_guard import dev_log
from winenv import client_rect_on_screen, find_game_hwnd


class WaterRecognizer:
    """浇水视觉识别器。提供各种 UI 状态检测方法。"""

    # OCR 相关 —— 复用 fishing.matcher 的 OCR 单例
    MIN_CONF = 0.5
    NORM_W = NORM_W  # 从 capture 导入的动态基准宽

    # 归一化 ROI —— 参考 MaaHKWorld 的 roi 参数
    # 好友列表区域(右侧,1200~1660,250~1020)
    ROI_FRIEND_LIST = (0.625, 0.23, 0.865, 0.94)
    # 浇水按钮区域(好友菜单中下部)
    ROI_WATER_BTN = (0.25, 0.55, 0.75, 0.75)
    # "回家"按钮(右上角)
    ROI_GO_HOME = (0.83, 0.0, 1.0, 0.09)
    # 已浇水田地提示(中上部)
    ROI_WATERED_FIELD = (0.43, 0.17, 0.57, 0.20)

    # 自农场 UI 固定位置(归一化坐标,1920x1080 基准)
    PT_HOME_ICON = (0.74, 0.55)       # ESC 菜单中「居所」图标
    PT_MANAGE_TAB = (0.46, 0.05)      # 居所页面「管理」Tab
    PT_FARM_FIELD = (0.50, 0.72)      # 管理页「农贸作物」区域
    PT_CONFIRM_BTN = (0.58, 0.60)     # 传送确认弹窗「确定」按钮
    PT_WATER_ACTION = (0.92, 0.92)     # 右下角浇水动作按钮(铲除/浇水等)

    def __init__(self, log=print) -> None:
        self.log = log

    # ---- 截图 ----
    def _grab(self) -> np.ndarray | None:
        """获取当前游戏窗口截图(后台 PrintWindow 优先,失败退回 GDI)。"""
        hwnd = find_game_hwnd()
        if not hwnd:
            return None
        try:
            from launcher import _print_window_bgr
            f = _print_window_bgr(hwnd)
            if f is not None:
                return f
        except Exception:
            pass
        try:
            with GameCapture(hwnd) as cap:
                return cap.grab()
        except Exception as exc:
            dev_log("WaterRecognizer 截图失败", exc)
            return None

    def _norm1920(self, frame):
        """宽 > NORM_W 时按比例降采样到 NORM_W,省 OCR 时间。"""
        h, w = frame.shape[:2]
        if w <= self.NORM_W:
            return frame
        nh = max(1, int(round(h * self.NORM_W / w)))
        return cv2.resize(frame, (self.NORM_W, nh), interpolation=cv2.INTER_AREA)

    def _crop(self, frame, roi):
        """按归一化 roi=(x0,y0,x1,y1) 切子图。"""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = roi
        return frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]

    def _ocr_text(self, frame, roi) -> str:
        """OCR 指定 ROI,返回拼接文本。"""
        sub = self._crop(frame, roi)
        if sub is None or sub.size == 0:
            return ""
        try:
            res, _ = _get_ocr()(sub)
        except Exception as exc:
            dev_log("Water OCR 失败", exc)
            return ""
        parts = []
        for it in (res or []):
            try:
                if float(it[2]) >= self.MIN_CONF:
                    parts.append(str(it[1]))
            except (TypeError, ValueError, IndexError):
                pass
        return "".join(parts)

    def _ocr_lines(self, frame, roi):
        """OCR 该 ROI → [(text, cx_norm, cy_norm), ...](文字框中心按客户区归一化)。"""
        sub = self._crop(frame, roi)
        if sub is None or sub.size == 0:
            return []
        try:
            res, _ = _get_ocr()(sub)
        except Exception as exc:
            dev_log("Water OCR 失败", exc)
            return []
        H, W = frame.shape[:2]
        ox, oy = roi[0] * W, roi[1] * H
        out = []
        for it in (res or []):
            try:
                box, txt, score = it[0], str(it[1]).strip(), float(it[2])
            except (IndexError, ValueError, TypeError):
                continue
            if not txt or score < self.MIN_CONF:
                continue
            cx = (ox + sum(p[0] for p in box) / len(box)) / W
            cy = (oy + sum(p[1] for p in box) / len(box)) / H
            out.append((txt, cx, cy))
        return out

    def find_text(self, frame, roi, keyword: str) -> tuple[float, float] | None:
        """在 ROI 中 OCR 查找包含 keyword 的文字,返回归一化中心坐标。"""
        for txt, cx, cy in self._ocr_lines(frame, roi):
            if keyword in txt:
                return (cx, cy)
        return None

    # ---- 业务检测 ----
    def has_go_home(self, frame) -> bool:
        """右上角是否有「回家」按钮。"""
        return "回家" in self._ocr_text(frame, self.ROI_GO_HOME)

    # ---- 自农场浇水相关 ----
    def is_menu_open(self, frame) -> bool:
        """ESC 菜单是否打开(检查是否有居所/背包等入口图标)。"""
        txt = self._ocr_text(frame, (0.65, 0.35, 0.95, 0.75))
        return "居所" in txt or "背包" in txt or "商城" in txt or "外观" in txt

    def find_home_icon(self, frame) -> tuple[float, float]:
        """ESC 菜单中「居所」图标位置。先 OCR,失败用固定坐标。"""
        pt = self.find_text(frame, (0.65, 0.35, 0.95, 0.75), "居所")
        return pt or self.PT_HOME_ICON

    def _current_home_tab(self, frame) -> str | None:
        """返回当前居所页面的激活 Tab 名称。优先用内容区域判断,再用 Tab 栏兜底。"""
        # 1. 内容区域判断(比 Tab 栏可靠,Tab 栏会显示所有 Tab 名字)
        content = self._ocr_text(frame, (0.15, 0.15, 0.95, 0.95))
        # 留言页: 有「我要留言」按钮 或 左侧简介 "这家伙很懒"
        if "我要留言" in content or "这家伙很懒" in content:
            return "留言"
        # 访客页
        if "访客" in content and "我要留言" not in content:
            return "访客"
        # 管理页: 有农贸/派遣/牧场/蔬菜摊等建筑
        if any(k in content for k in ("农贸", "派遣", "牧场", "蔬菜摊", "培养箱", "区域一")):
            return "管理"
        # 总览页: 有封面和「的居所」
        if "的居所" in content and ("更换封面" in content or "封面" in content):
            return "总览"

        # 2. Tab 栏兜底
        txt = self._ocr_text(frame, (0.35, 0.0, 0.65, 0.12))
        if "管理" in txt and any(k in content for k in ("农贸", "派遣", "牧场")):
            return "管理"
        if "总览" in txt:
            return "总览"
        if "留言" in txt:
            return "留言"
        if "访客" in txt:
            return "访客"
        return None

    def is_home_management_tab(self, frame) -> bool:
        """是否已经在居所的「管理」Tab。"""
        return self._current_home_tab(frame) == "管理"

    def find_manage_tab(self, frame) -> tuple[float, float]:
        """居所页「管理」Tab 位置。"""
        pt = self.find_text(frame, (0.35, 0.0, 0.65, 0.12), "管理")
        return pt or self.PT_MANAGE_TAB

    def find_farm_field(self, frame) -> tuple[float, float]:
        """管理页「农贸作物」区域位置。"""
        pt = self.find_text(frame, (0.2, 0.5, 0.8, 0.85), "农贸")
        if pt:
            return pt
        pt = self.find_text(frame, (0.2, 0.5, 0.8, 0.85), "作物")
        if pt:
            return pt
        return self.PT_FARM_FIELD

    def has_confirm_dialog(self, frame) -> bool:
        """是否有传送确认弹窗。"""
        txt = self._ocr_text(frame, (0.3, 0.35, 0.7, 0.65))
        return "是否" in txt and "传送" in txt

    def find_confirm_button(self, frame) -> tuple[float, float]:
        """传送确认弹窗「确定」按钮位置。"""
        pt = self.find_text(frame, (0.5, 0.5, 0.7, 0.7), "确定")
        if pt:
            return pt
        return self.PT_CONFIRM_BTN

    # ---- 自农场浇水 — 居所封面路径 ----
    PT_COVER_IMAGE = (0.35, 0.50)     # 居所「总览」页左侧封面大图
    PT_RESIDENCE_CONFIRM = (0.58, 0.60)  # "是否传送至居所" 确定按钮

    def is_residence_overview(self, frame) -> bool:
        """是否在居所「总览」页(有封面大图)。"""
        txt = self._ocr_text(frame, (0.35, 0.0, 0.65, 0.12))
        has_tabs = "总览" in txt and "管理" in txt
        has_cover = self._ocr_text(frame, (0.15, 0.15, 0.55, 0.85)) != ""
        return has_tabs and has_cover

    def find_cover_image(self, frame) -> tuple[float, float]:
        """居所总览页左侧封面大图位置。"""
        pt = self.find_text(frame, (0.15, 0.15, 0.55, 0.85), "的居所")
        if pt:
            return pt
        return self.PT_COVER_IMAGE

    def has_residence_confirm_dialog(self, frame) -> bool:
        """是否有「是否传送至居所？」确认弹窗。"""
        txt = self._ocr_text(frame, (0.3, 0.35, 0.7, 0.65))
        return "是否" in txt and "传送至居所" in txt

    def find_residence_confirm_button(self, frame) -> tuple[float, float]:
        """「是否传送至居所」确认弹窗的确定按钮。"""
        pt = self.find_text(frame, (0.5, 0.5, 0.7, 0.7), "确定")
        if pt:
            return pt
        return self.PT_RESIDENCE_CONFIRM

    def has_change_crop_dialog(self, frame) -> bool:
        """是否误触「更换作物/选择作物」弹窗。"""
        txt = self._ocr_text(frame, (0.3, 0.35, 0.7, 0.65))
        # "更换作物" 或 "选择作物" 或标题为 "农贸作物" 的弹窗
        if "作物" in txt and any(k in txt for k in ("更换", "选择")):
            return True
        if "农贸作物" in txt and ("选择" in txt or "解锁" in txt):
            return True
        return False

    def has_f_interaction(self, frame) -> bool:
        """是否有 F 交互提示(如「出售作物」「升级蔬菜摊」),表示走到摊位附近,该停了。"""
        txt = self._ocr_text(frame, (0.55, 0.45, 0.75, 0.65))
        return "F" in txt and any(k in txt for k in ("出售", "升级", "交互"))

    def has_water_or_remove_icon(self, frame) -> bool:
        """右下角是否有浇水/铲除等交互图标。"""
        txt = self._ocr_text(frame, (0.80, 0.85, 1.0, 1.0))
        return any(k in txt for k in ("浇水", "铲除", "收获", "种植", "交互"))

    def find_water_action_pos(self, frame) -> tuple[float, float]:
        """右下角动作按钮位置(浇水/铲除)。"""
        pt = self.find_text(frame, (0.80, 0.85, 1.0, 1.0), "浇水")
        if pt:
            return pt
        pt = self.find_text(frame, (0.80, 0.85, 1.0, 1.0), "铲除")
        if pt:
            return pt
        return self.PT_WATER_ACTION

    def is_in_farm_scene(self, frame) -> bool:
        """是否已经在农田场景(有浇水图标或作物)。"""
        return self.has_water_or_remove_icon(frame)

    def find_friend_in_list(self, frame, friend_name: str) -> tuple[float, float] | None:
        """在好友列表中 OCR 查找指定好友名。返回归一化坐标(cx, cy)或 None。"""
        sub = self._crop(frame, self.ROI_FRIEND_LIST)
        if sub is None or sub.size == 0:
            return None
        try:
            res, _ = _get_ocr()(sub)
        except Exception:
            return None
        H, W = frame.shape[:2]
        ox, oy = self.ROI_FRIEND_LIST[0] * W, self.ROI_FRIEND_LIST[1] * H
        for it in (res or []):
            try:
                box, txt, score = it[0], str(it[1]).strip(), float(it[2])
            except (IndexError, ValueError, TypeError):
                continue
            if not txt or score < self.MIN_CONF:
                continue
            if friend_name in txt:
                cx = (ox + sum(p[0] for p in box) / len(box)) / W
                cy = (oy + sum(p[1] for p in box) / len(box)) / H
                return (cx, cy)
        return None

    def has_watering_button(self, frame) -> bool:
        """当前画面是否有「浇水」按钮(在好友菜单中)。"""
        txt = self._ocr_text(frame, self.ROI_WATER_BTN)
        return "浇水" in txt or "浇灌" in txt

    def has_confirm_teleport(self, frame) -> bool:
        """是否有传送确认弹窗。"""
        txt = self._ocr_text(frame, (0.3, 0.35, 0.7, 0.65))
        return "传送" in txt and ("确认" in txt or "是" in txt or "前往" in txt)

    def is_field_watered(self, frame) -> bool:
        """当前田地是否已浇水(中上部提示)。"""
        txt = self._ocr_text(frame, self.ROI_WATERED_FIELD)
        return "已浇水" in txt or "已浇灌" in txt or "浇水成功" in txt

    def is_loading(self, frame) -> bool:
        """是否处于加载/过场画面。"""
        # 加载画面通常全黑或有 loading 文字
        h, w = frame.shape[:2]
        center = frame[h // 4:3 * h // 4, w // 4:3 * w // 4]
        mean_val = np.mean(center)
        if mean_val < 30:
            return True
        txt = self._ocr_text(frame, (0.35, 0.4, 0.65, 0.6))
        load_keys = ("加载", "读取", "进入", "传送", "Loading", "loading")
        return any(k in txt for k in load_keys)
