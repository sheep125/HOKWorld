"""WaterBot — 自动浇水状态机。

基于 MaaHKWorld farmforfriends.json 流水线翻译为键鼠操作:

状态机:
  INIT → TELEPORT_START → LOADING → FRIEND_LOOP → GO_HOME → DONE

FRIEND_LOOP 内部:
  遍历 friends 列表 → CHECK_WATER → (可浇水时) WATERING → NEXT_FRIEND

所有键位从 water/keys.py 加载,可通过 config.json 的 "water_keys" 段覆盖。
"""
from __future__ import annotations

import random
import time
from enum import Enum, auto

import cv2
import numpy as np

from runtime_guard import dev_log, release_known_keys, safe_click_norm, safe_press_key
from water.keys import load_water_keys
from water.recognizer import WaterRecognizer
from winenv import find_game_hwnd


class State(Enum):
    INIT = auto()
    TELEPORT_START = auto()
    LOADING = auto()           # 等待传送完成
    FRIEND_LOOP = auto()       # 遍历好友列表
    CHECK_WATER = auto()       # 检查当前好友能否浇水
    WATERING = auto()          # 在好友的田里浇水
    NEXT_FRIEND = auto()       # 下一个好友
    GO_HOME = auto()           # 回家
    DONE = auto()


class WaterBot:
    """自动浇水 Bot — 键鼠操作版本。

    用法:
        bot = WaterBot(
            log=print,
            friends=["好友A", "好友B", "好友C"],
            fields_per_friend=3,
        )
        bot.run()
    """

    TICK = 0.5                  # 主循环间隔
    TOTAL_TIMEOUT = 600.0       # 总超时(秒)
    LOAD_TIMEOUT = 60.0         # 加载超时
    CLICK_DELAY = (0.15, 0.4)   # 点击前随机延迟
    AFTER_CLICK = 0.6           # 点击后等待
    AFTER_KEY = 0.3             # 按键后等待
    STABLE_FRAMES = 3           # OCR 连续确认帧数

    def __init__(
        self,
        log=print,
        friends: list[str] | None = None,
        fields_per_friend: int = 3,
    ) -> None:
        self.log = log
        self.friends = friends or []
        self.fields_per_friend = fields_per_friend
        self.stop_flag = False
        self.paused = False
        self._keys = load_water_keys()
        self._rec = WaterRecognizer(log=log)
        self._state = State.INIT
        self._friend_idx = 0
        self._watered_count = 0
        self._stable = 0         # OCR 稳定计数

        self.log(f"浇水 Bot 初始化:键位={list(self._keys.keys())}, "
                 f"好友数={len(self.friends)}, 每好友浇={fields_per_friend} 块田")

    # ---- 控制接口 ----
    def stop(self) -> None:
        self.stop_flag = True
        release_known_keys(self.log)

    def set_paused(self, on: bool) -> None:
        self.paused = on

    # ---- 键鼠原子操作 ----
    def _press(self, key_name: str, hold: float = 0.08) -> bool:
        """按一次键(防抖:先抬起再按下)。"""
        vk = self._keys.get(key_name)
        if vk is None:
            return False
        return safe_press_key(vk, self._stopped, self._foreground, self.log, hold)

    def _click_norm(self, hwnd, pt) -> bool:
        """归一化点击(客户区坐标分数)。"""
        time.sleep(random.uniform(*self.CLICK_DELAY))
        return safe_click_norm(hwnd, pt, self._stopped, self._foreground, self.log)

    def _stopped(self) -> bool:
        return bool(self.stop_flag)

    def _foreground(self) -> bool:
        return True  # 键鼠不需要前台检测(与 runtime_guard 一致)

    # ---- 状态机主循环 ----
    def run(self) -> bool:
        # 激活游戏窗口(后台无法读屏/输入)
        from winenv import activate_game_window
        activate_game_window(self.log)

        self.stop_flag = False
        self._state = State.INIT
        self._friend_idx = 0
        self._watered_count = 0

        deadline = time.time() + self.TOTAL_TIMEOUT
        self.log("自动浇水:开始(键鼠操作,按 config.json 中 water_keys 映射)")

        while not self.stop_flag and time.time() < deadline:
            if self.paused:
                time.sleep(0.2)
                continue

            if self._state == State.INIT:
                self._do_init()
            elif self._state == State.TELEPORT_START:
                self._do_teleport()
            elif self._state == State.LOADING:
                self._do_loading()
            elif self._state == State.FRIEND_LOOP:
                self._do_friend_loop()
            elif self._state == State.CHECK_WATER:
                self._do_check_water()
            elif self._state == State.WATERING:
                self._do_watering()
            elif self._state == State.NEXT_FRIEND:
                self._do_next_friend()
            elif self._state == State.GO_HOME:
                self._do_go_home()
            elif self._state == State.DONE:
                self.log("自动浇水:完成")
                return True

        if self.stop_flag:
            self.log("自动浇水:已停止")
        else:
            self.log("自动浇水:超时")
        return False

    # ================================================================
    # INIT — 找游戏窗口,准备开始
    # ================================================================
    def _do_init(self) -> None:
        hwnd = find_game_hwnd()
        if not hwnd:
            self.log("未找到游戏窗口,请确认游戏已运行")
            time.sleep(2.0)
            return
        self.log(f"找到游戏窗口 hwnd={hwnd},准备传送")
        self._state = State.TELEPORT_START

    # ================================================================
    # TELEPORT — 打开地图 → OCR 找「农贸作物」→ 传送
    # 参考 MaaHKWorld: 通用_传送到目标 流程
    # ================================================================
    def _do_teleport(self) -> None:
        """传送到农贸作物区域(好友浇水入口)。

        流程(MaaHKWorld → KBM 映射):
          1. 按 KEY_menu 打开地图
          2. OCR 找「居所」→ 点击
          3. 按 KEY_tab_next 切到管理 Tab
          4. OCR 找目标位置 → 点击
          5. 确认传送 → 等待加载
        """
        hwnd = find_game_hwnd()
        if not hwnd:
            self._state = State.INIT
            return

        self.log("传送:打开地图…")
        self._press("menu")
        time.sleep(2.0)

        # 尝试 OCR 找「居所」并点击
        frame = self._rec._grab()
        if frame is not None:
            fn = self._rec._norm1920(frame)
            home_pt = self._rec.find_friend_in_list(fn, "居所")
            if home_pt:
                self.log("传送:找到「居所」→ 点击")
                self._click_norm(hwnd, home_pt)
                time.sleep(1.5)
                self._press("tab_next")   # 切换到管理 Tab
                time.sleep(1.0)

        # 寻找农贸作物
        frame = self._rec._grab()
        if frame is not None:
            fn = self._rec._norm1920(frame)
            farm_pt = self._rec.find_friend_in_list(fn, "农贸")
            if farm_pt:
                self.log("传送:找到「农贸作物」→ 点击")
                self._click_norm(hwnd, farm_pt)
                time.sleep(1.0)
                self._press("confirm")    # 确认传送
                time.sleep(1.0)

        self._state = State.LOADING
        self._load_deadline = time.time() + self.LOAD_TIMEOUT

    # ================================================================
    # LOADING — 等待传送加载完成
    # ================================================================
    def _do_loading(self) -> None:
        if time.time() > getattr(self, "_load_deadline", 0):
            self.log("传送加载超时,尝试继续")
            self._state = State.FRIEND_LOOP
            return

        frame = self._rec._grab()
        if frame is None:
            time.sleep(1.0)
            return

        if self._rec.is_loading(frame):
            self._stable = 0
            time.sleep(1.0)
            return

        # 连续确认已不在加载画面
        self._stable += 1
        if self._stable >= self.STABLE_FRAMES:
            self.log("传送完成,开始遍历好友列表")
            self._state = State.FRIEND_LOOP
            self._stable = 0
        else:
            time.sleep(0.5)

    # ================================================================
    # FRIEND_LOOP — 遍历好友列表
    # ================================================================
    def _do_friend_loop(self) -> None:
        if self._friend_idx >= len(self.friends):
            self.log("所有好友已处理完毕")
            self._state = State.GO_HOME
            return

        friend = self.friends[self._friend_idx]
        self.log(f"好友 [{self._friend_idx + 1}/{len(self.friends)}]: {friend}")
        self._state = State.CHECK_WATER

    # ================================================================
    # CHECK_WATER — OCR 检测当前好友是否可浇水
    # ================================================================
    def _do_check_water(self) -> None:
        friend = self.friends[self._friend_idx]

        # 打开好友交互菜单
        hwnd = find_game_hwnd()
        if not hwnd:
            time.sleep(self.TICK)
            return

        # 在好友列表中找到并点击好友
        frame = self._rec._grab()
        if frame is None:
            time.sleep(self.TICK)
            return

        fn = self._rec._norm1920(frame)
        pt = self._rec.find_friend_in_list(fn, friend)
        if pt is None:
            self.log(f"  未找到好友「{friend}」在列表中,跳过")
            self._state = State.NEXT_FRIEND
            return

        self.log(f"  找到好友「{friend}」→ 点击")
        self._click_norm(hwnd, pt)
        time.sleep(self.AFTER_CLICK)

        # 检查是否有浇水按钮
        time.sleep(0.5)
        frame = self._rec._grab()
        if frame is not None and self._rec.has_watering_button(self._rec._norm1920(frame)):
            self.log(f"  可以浇水 → 点击传送去好友农场")
            self._press("interact")      # 点击浇水/传送按钮
            time.sleep(1.0)
            self._press("confirm")       # 确认传送
            time.sleep(2.0)
            self._watered_count = 0
            self._state = State.WATERING
        else:
            self.log(f"  无需浇水(已浇过或不可用)")
            self._press("cancel")        # 关闭菜单
            time.sleep(0.5)
            self._state = State.NEXT_FRIEND

    # ================================================================
    # WATERING — 在好友田里执行浇水
    # ================================================================
    def _do_watering(self) -> None:
        """在好友农场里浇水。

        参考 MaaHKWorld 浇水循环:
          前进一步 → 按浇水键(RB → F) × 2 → 检查是否已浇水 → 重复到 3 块田
        """
        if self._watered_count >= self.fields_per_friend:
            self.log(f"  已完成浇水 {self._watered_count}/{self.fields_per_friend} 块田")
            self._state = State.NEXT_FRIEND
            return

        self.log(f"  浇水 {self._watered_count + 1}/{self.fields_per_friend}…")

        # 向前走一步(对齐下一块田)
        self._press("forward", hold=0.18)
        time.sleep(0.5)

        # 按浇水键 × 2
        self._press("water")
        time.sleep(0.5)
        self._press("water")
        time.sleep(1.0)

        # 检查是否已浇水(中上部提示)
        frame = self._rec._grab()
        if frame is not None:
            fn = self._rec._norm1920(frame)
            if self._rec.is_field_watered(fn):
                self._watered_count += 1
                self.log(f"    → 浇水成功({self._watered_count}/{self.fields_per_friend})")
            else:
                self.log(f"    → 未检测到浇水提示,继续尝试")
                self._watered_count += 1  # 即使没读到也计数,避免死循环

        time.sleep(0.5)

    # ================================================================
    # NEXT_FRIEND — 切换到下一个好友
    # ================================================================
    def _do_next_friend(self) -> None:
        self._friend_idx += 1
        # 按向下键滚动好友列表
        self._press("scroll_down")
        time.sleep(0.3)
        self._state = State.FRIEND_LOOP

    # ================================================================
    # GO_HOME — 传送回家
    # ================================================================
    def _do_go_home(self) -> None:
        self.log("回家…")
        self._press("menu")
        time.sleep(1.5)

        hwnd = find_game_hwnd()
        if hwnd:
            frame = self._rec._grab()
            if frame is not None:
                fn = self._rec._norm1920(frame)
                home_pt = self._rec.find_friend_in_list(fn, "回家")
                if home_pt:
                    self._click_norm(hwnd, home_pt)
                    time.sleep(2.0)

        self._state = State.DONE
