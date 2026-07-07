"""SelfFarmWaterBot — 给自己的农场浇水(居所封面路线)。

流程:
  ESC → 居所 → 点击封面大图 → 确定传送 → 加载 → 走进田地+左键浇水 → 碰到摊位/树停止

浇水方式: W 走一步 + 左键点击右下角浇水/动作按钮,每次浇水前检测弹窗和终点。
"""
from __future__ import annotations

import random
import time
from enum import Enum, auto

from runtime_guard import release_known_keys, safe_click_norm, safe_press_key
from water.keys import load_water_keys
from water.recognizer import WaterRecognizer
from winenv import find_game_hwnd


class SelfFarmState(Enum):
    INIT = auto()
    OPEN_MENU = auto()
    CLICK_HOME = auto()
    CLICK_COVER = auto()
    CONFIRM_RESIDENCE = auto()
    LOADING = auto()
    WATERING = auto()       # 走进田地 + 浇水(边走边浇)
    DONE = auto()


class SelfFarmWaterBot:
    TICK = 0.5
    TOTAL_TIMEOUT = 600.0
    LOAD_TIMEOUT = 60.0
    CLICK_DELAY = (0.15, 0.4)
    STABLE_FRAMES = 3
    MAX_WATER_STEPS = 40    # 最多浇水步数(防止无限循环)
    # —— 游戏就绪预检(修复定时调度启动后浇水卡住)——
    READY_TIMEOUT = 180.0        # 等游戏画面就绪上限(覆盖着色器编译等长加载)
    READY_STABLE_FRAMES = 5      # 连续多少帧"非加载/非黑屏"才算就绪
    READY_TICK = 1.0             # 预检轮询间隔
    MENU_RETRY_MAX = 8           # OPEN_MENU 状态按 ESC 最多重试次数(防死循环)

    def __init__(self, log=print) -> None:
        self.log = log
        self.stop_flag = False
        self.paused = False
        self._keys = load_water_keys()
        self._rec = WaterRecognizer(log=log)
        self._state = SelfFarmState.INIT
        self._stable = 0
        self._load_deadline = 0.0
        self._step = 0
        self._menu_tries = 0       # OPEN_MENU 按 ESC 重试计数(防死循环)

    def stop(self) -> None:
        self.stop_flag = True
        release_known_keys(self.log)

    def set_paused(self, on: bool) -> None:
        self.paused = on

    def _stopped(self) -> bool:
        return bool(self.stop_flag)

    def _foreground(self) -> bool:
        return True

    # ---- 原子操作 ----
    def _press(self, key_name: str, hold: float = 0.08) -> bool:
        vk = self._keys.get(key_name)
        if vk is None:
            return False
        return safe_press_key(vk, self._stopped, self._foreground, self.log, hold)

    def _click_norm(self, pt, down_s: float = 0.02) -> bool:
        hwnd = find_game_hwnd()
        if not hwnd:
            return False
        time.sleep(random.uniform(*self.CLICK_DELAY))
        return safe_click_norm(hwnd, pt, self._stopped, self._foreground, self.log, down_s)

    def _left_click_water(self) -> bool:
        """点击右下角浇水/动作按钮。"""
        hwnd = find_game_hwnd()
        if not hwnd:
            return False
        frame = self._rec._grab()
        pt = self._rec.PT_WATER_ACTION
        if frame is not None:
            pt = self._rec.find_water_action_pos(self._rec._norm1920(frame))
        time.sleep(random.uniform(*self.CLICK_DELAY))
        return safe_click_norm(hwnd, pt, self._stopped, self._foreground, self.log, 0.02)

    # ---- 主循环 ----
    def run(self) -> bool:
        from winenv import activate_game_window
        activate_game_window(self.log)

        self.stop_flag = False
        self._state = SelfFarmState.INIT
        self._stable = 0
        self._step = 0
        self._menu_tries = 0       # OPEN_MENU 按 ESC 重试计数(防死循环)

        # ===== 游戏画面就绪预检 =====
        # launcher 返回成功 ≠ 游戏世界已可操作:
        # 点完「开始游戏」后还有进入世界的加载/渲染过渡(黑屏/着色器编译),
        # 此时按 ESC 无效、is_menu_open() 永远 False → 死循环卡住。
        # 这里先等画面"稳定下来"(连续 N 帧非黑屏/非加载),再进浇水流程。
        if not self._wait_game_ready():
            return False

        deadline = time.time() + self.TOTAL_TIMEOUT
        self.log("自农场浇水:开始(居所封面路线)")

        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.2)
                continue
            if self._state == SelfFarmState.INIT:
                self._do_init()
            elif self._state == SelfFarmState.OPEN_MENU:
                self._do_open_menu()
            elif self._state == SelfFarmState.CLICK_HOME:
                self._do_click_home()
            elif self._state == SelfFarmState.CLICK_COVER:
                self._do_click_cover()
            elif self._state == SelfFarmState.CONFIRM_RESIDENCE:
                self._do_confirm_residence()
            elif self._state == SelfFarmState.LOADING:
                self._do_loading()
            elif self._state == SelfFarmState.WATERING:
                self._do_watering()
            elif self._state == SelfFarmState.DONE:
                self.log("自农场浇水:完成")
                return True

        self.log(f"自农场浇水:{'已停止' if self.stop_flag else '超时'}")
        return False

    # ---- 游戏画面就绪预检 ----
    def _wait_game_ready(self) -> bool:
        """等待游戏画面从加载/黑屏过渡中稳定下来。

        launcher 返回 True 只代表「开始游戏」已点击并从画面消失,
        但游戏可能还在着色器编译 / 进入世界的渲染过渡中,
        此时按键无响应、ESC 打不开菜单 → 浇水会死循环卡住。

        这里连续 READY_STABLE_FRAMES 帧检测到「非黑屏 + 非加载画面」才放行。
        """
        self.log("等待游戏画面就绪(加载/过渡中,暂不操作)…")
        stable = 0
        deadline = time.time() + self.READY_TIMEOUT
        last_log = 0.0
        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.3)
                continue
            frame = self._rec._grab()
            if frame is None:
                # 游戏窗口还没出现 → 继续等(launcher 刚交班)
                stable = 0
                if time.time() - last_log > 5.0:
                    self.log("等待游戏窗口出现…")
                    last_log = time.time()
                time.sleep(self.READY_TICK)
                continue
            fn = self._rec._norm1920(frame)
            if self._rec.is_loading(fn):
                stable = 0
                if time.time() - last_log > 5.0:
                    self.log("游戏仍在加载中(黑屏/过场),继续等待…")
                    last_log = time.time()
                time.sleep(self.READY_TICK)
                continue
            # 非加载画面 → 累积稳定帧
            stable += 1
            if stable >= self.READY_STABLE_FRAMES:
                self.log(f"游戏画面已就绪(连续 {stable} 帧非加载)")
                return True
            time.sleep(self.READY_TICK)
        if self.stop_flag:
            self.log("等待游戏就绪:已停止")
        else:
            self.log("等待游戏就绪:超时,仍尝试继续(可能浇水失败)")
        return not self.stop_flag

    # ---- 状态处理 ----
    def _do_init(self) -> None:
        hwnd = find_game_hwnd()
        if not hwnd:
            time.sleep(2.0)
            return
        self._state = SelfFarmState.OPEN_MENU

    def _do_open_menu(self) -> None:
        self._menu_tries += 1
        if self._menu_tries > self.MENU_RETRY_MAX:
            # 连续按 ESC 多次仍打不开菜单 → 游戏可能卡在不可操作状态
            # (登录界面/过场/弹窗),不再死按,转去检测是否已在游戏内可操作画面
            self.log(f"ESC 已重试 {self.MENU_RETRY_MAX} 次仍未打开菜单,尝试重新激活窗口")
            from winenv import activate_game_window
            activate_game_window(self.log)
            self._menu_tries = 0
            time.sleep(2.0)
            return
        self._press("menu")
        time.sleep(2.0)
        frame = self._rec._grab()
        if frame is not None and self._rec.is_menu_open(self._rec._norm1920(frame)):
            self._menu_tries = 0
            self._state = SelfFarmState.CLICK_HOME
        else:
            time.sleep(0.5)

    def _do_click_home(self) -> None:
        frame = self._rec._grab()
        if frame is None:
            time.sleep(0.5)
            return
        fn = self._rec._norm1920(frame)
        pt = self._rec.find_home_icon(fn)
        self._click_norm(pt)
        time.sleep(2.5)
        self._state = SelfFarmState.CLICK_COVER

    def _do_click_cover(self) -> None:
        frame = self._rec._grab()
        if frame is None:
            time.sleep(0.5)
            return
        fn = self._rec._norm1920(frame)
        if not self._rec.is_residence_overview(fn):
            time.sleep(1.0)
            return
        pt = self._rec.find_cover_image(fn)
        self._click_norm(pt)
        time.sleep(1.5)
        self._state = SelfFarmState.CONFIRM_RESIDENCE

    def _do_confirm_residence(self) -> None:
        frame = self._rec._grab()
        if frame is None:
            time.sleep(0.5)
            return
        fn = self._rec._norm1920(frame)
        if not self._rec.has_residence_confirm_dialog(fn):
            self._state = SelfFarmState.LOADING
            self._load_deadline = time.time() + self.LOAD_TIMEOUT
            return
        pt = self._rec.find_residence_confirm_button(fn)
        self._click_norm(pt)
        time.sleep(1.5)
        self._state = SelfFarmState.LOADING
        self._load_deadline = time.time() + self.LOAD_TIMEOUT

    def _do_loading(self) -> None:
        if time.time() > self._load_deadline:
            self._state = SelfFarmState.WATERING
            return
        frame = self._rec._grab()
        if frame is None:
            time.sleep(1.0)
            return
        if self._rec.is_loading(self._rec._norm1920(frame)):
            self._stable = 0
            time.sleep(1.0)
            return
        self._stable += 1
        if self._stable >= self.STABLE_FRAMES:
            self._stable = 0
            self._state = SelfFarmState.WATERING
        else:
            time.sleep(0.5)

    # ---- 浇水(边走边浇) ----
    def _do_watering(self) -> None:
        """走进田地 + 浇水。
        每次: W 前进一步 → 检测弹窗/终点 → 左键点击浇水按钮。
        碰到 F 交互(摊位/升级)或走到头(树)就停止。
        """
        self._step += 1
        if self._step > self.MAX_WATER_STEPS:
            self.log(f"浇水达到最大步数 {self.MAX_WATER_STEPS},停止")
            self._state = SelfFarmState.DONE
            return

        self.log(f"浇水 第{self._step}步")

        # W 前进一步
        self._press("forward", hold=0.15)
        time.sleep(0.3)

        # 截图检测状态
        frame = self._rec._grab()
        if frame is not None:
            fn = self._rec._norm1920(frame)
            # 误触弹窗 → ESC
            if self._rec.has_change_crop_dialog(fn):
                self.log("误触弹窗,按 ESC 返回")
                self._press("cancel")
                time.sleep(0.5)
            # F 交互出现 → 走到摊位/可交互区域,完成
            if self._rec.has_f_interaction(fn):
                self.log("已走到可交互区域,浇水结束")
                self._state = SelfFarmState.DONE
                return

        # 左键点击浇水
        self._left_click_water()
        time.sleep(0.6)
