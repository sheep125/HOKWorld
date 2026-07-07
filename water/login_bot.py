"""LoginBot — 自动登录游戏 + 月卡检测。

实时触发模式: 检测游戏窗口,自动点击登录/进入游戏按钮。
月卡检测: 定时检查是否有月卡弹窗并关闭。
"""
from __future__ import annotations

import time
from runtime_guard import safe_press_key
from water.recognizer import WaterRecognizer
from winenv import find_game_hwnd, activate_game_window


class LoginBot:

    TICK = 1.0
    TIMEOUT = 120.0

    def __init__(self, log=print, check_monthly=False, monthly_hour=0, monthly_window_mins=30):
        self.log = log
        self.check_monthly = check_monthly
        self.monthly_hour = monthly_hour
        self.monthly_window_mins = monthly_window_mins
        self.stop_flag = False
        self.paused = False
        self._rec = WaterRecognizer(log=log)

    def stop(self): self.stop_flag = True
    def set_paused(self, on): self.paused = on

    def run(self) -> bool:
        self.stop_flag = False
        activate_game_window(self.log)

        deadline = time.time() + self.TIMEOUT
        self.log("[自动登录] 开始检查登录状态…")

        # Phase 1: 检测登录/启动界面
        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.5)
                continue
            hwnd = find_game_hwnd()
            if not hwnd:
                time.sleep(2)
                continue
            frame = self._rec._grab()
            if frame is None:
                time.sleep(1)
                continue
            fn = self._rec._norm1920(frame)
            # 检测"开始游戏"或"进入游戏"按钮
            txt = self._rec._ocr_text(fn, (0.3, 0.6, 0.7, 0.9))
            if any(k in txt for k in ("开始游戏", "进入游戏")):
                self.log("[自动登录] 检测到进入游戏按钮,点击")
                self._press_enter()
                time.sleep(3)
                break
            # 检测公告弹窗
            if "公告" in self._rec._ocr_text(fn, (0.1, 0.15, 0.4, 0.35)):
                self.log("[自动登录] 检测到公告,按 ESC 关闭")
                self._press_esc()
                time.sleep(1)
            time.sleep(2)

        # Phase 2: 等待进入游戏后检测月卡
        if self.check_monthly:
            self._handle_monthly_card()

        self.log("[自动登录] 完成")
        return True

    def _handle_monthly_card(self):
        """检测并关闭月卡弹窗(可能不是即时出现,需要等一段时间)。"""
        import datetime
        now = datetime.datetime.now()
        target = now.replace(hour=self.monthly_hour, minute=0, second=0, microsecond=0)
        window_min = self.monthly_window_mins

        # 检查当前时间是否在月卡窗口内
        delta = abs((now - target).total_seconds()) / 60
        if delta > window_min:
            self.log(f"[月卡] 当前不在月卡检测窗口(当前{now.hour}:{now.minute:02d}, 目标{self.monthly_hour}:00±{window_min}分)")
            return

        self.log(f"[月卡] 进入月卡检测窗口,等待月卡弹窗…")
        deadline = time.time() + window_min * 60
        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.5)
                continue
            frame = self._rec._grab()
            if frame is None:
                time.sleep(2)
                continue
            fn = self._rec._norm1920(frame)
            # 检测月卡弹窗特征: "月卡" "领取" "已续费" 等
            txt = self._rec._ocr_text(fn, (0.3, 0.3, 0.7, 0.7))
            if "月卡" in txt and any(k in txt for k in ("领取", "已续费", "续费", "关闭")):
                self.log("[月卡] 检测到月卡弹窗,按 ESC 关闭")
                self._press_esc()
                time.sleep(1)
                return
            if "月卡" in txt:
                self.log("[月卡] 检测到月卡,但无关闭按钮,按 ESC 尝试")
                self._press_esc()
                time.sleep(1)
                return
            time.sleep(5)

    def _press_esc(self):
        safe_press_key(0x1B, self._stopped, self._foreground, None, 0.05)

    def _press_enter(self):
        safe_press_key(0x0D, self._stopped, self._foreground, None, 0.05)

    def _stopped(self): return bool(self.stop_flag)

    def _foreground(self): return True
