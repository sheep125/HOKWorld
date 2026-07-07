"""实时检测页 — 点开始后实时读屏:自动识别跳过剧情;可选开「经过材料自动采集」一起跑。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from qfluentwidgets import (
    BodyLabel, CardWidget, ExpandGroupSettingCard, FluentIcon as FIF,
    IconWidget, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton,
    SwitchButton,
)

from runtime_guard import registry, release_known_keys
from ui.scroll_interface import ScrollInterface
from winenv import is_admin


class RealtimeInterface(ScrollInterface):
    """实时检测页:点开始后实时读屏,自动识别跳过剧情;
    可选开启「经过材料自动采集」,与剧情跳过同时跑。无触发状态时不动作。"""
    _DESC = "点开始后实时读屏:自动识别跳过剧情;可选开「经过材料自动采集」一起跑。无触发状态时不动作"

    def __init__(self) -> None:
        super().__init__("realtimeInterface")
        self._worker = None
        self._gather = None
        self._launcher = None
        self._water = None         # 联动浇水线程
        self._monthly = None       # 月卡检测线程
        self._paused = False
        self._aborting = False
        self._last_msg = ""

        root = self.vbox
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self.card = ExpandGroupSettingCard(FIF.VIDEO, "实时检测(剧情跳过 + 自动采集)", self._DESC, self)
        self.start_btn = PrimaryPushButton(FIF.PLAY, "开始")
        self.pause_btn = PushButton(FIF.PAUSE, "暂停")
        self.stop_btn = PushButton(FIF.CLOSE, "停止")
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.card.addWidget(self.start_btn)
        self.card.addWidget(self.pause_btn)
        self.card.addWidget(self.stop_btn)
        self.nudge_switch = SwitchButton()
        self.nudge_switch.setChecked(False)
        self.nudge_switch.setEnabled(False)          # 已废弃:代码不再微动鼠标,避免用户误开导致误解
        self.gather_switch = SwitchButton()
        self.gather_switch.setChecked(True)          # 默认开启:点开始即跳剧情 + 自动采集
        self.card.addGroup(FIF.SYNC, "经过材料自动采集(F)",
                           "经过材料/宝箱/重现自动按 F(按图标识别;NPC/商店/对话/组队不动)。"
                           "误采的交互可在「设置 · 采集碰撞名单」里加一行排除",
                           self.gather_switch)
        # 自动启动游戏(副栏开关)
        self.launch_switch = SwitchButton()
        self.launch_switch.setChecked(True)          # 默认开:点「开始」即自动启动游戏(已在游戏则跳过)
        self.card.addGroup(FIF.GAME, "自动启动游戏",
                           "点击「开始」自动启动游戏", self.launch_switch)

        # 游戏启动后自动浇水(副栏开关)
        from config import cfg
        self.water_switch = SwitchButton()
        self.water_switch.setChecked(bool(cfg.get("auto_water_after_game")))
        self.water_switch.checkedChanged.connect(
            lambda on: cfg.set("auto_water_after_game", bool(on)))
        self.card.addGroup(FIF.CAFE, "游戏启动后自动浇水",
                           "游戏启动完成→先浇水→再开始实时检测(浇水模式在「浇水」页选)",
                           self.water_switch)
        root.addWidget(self.card)

        self.status_card = CardWidget()
        sl = QHBoxLayout(self.status_card)
        sl.setContentsMargins(16, 10, 16, 10)
        sl.setSpacing(10)
        self._status_icon = IconWidget(FIF.VIDEO, self.status_card)
        self._status_icon.setFixedSize(16, 16)
        self.status = BodyLabel("")
        sl.addWidget(self._status_icon)
        sl.addWidget(self.status, 1)
        self.status_card.hide()
        root.addWidget(self.status_card)
        root.addStretch(1)

        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn.clicked.connect(self._stop)

    # ---- 启动 / 停止 / 暂停 ----
    def _start(self) -> None:
        if self._paused and (self._worker or self._launcher or self._gather):
            self._toggle_pause()
            return
        if self._worker or self._launcher:
            return
        ok, reason = registry.start("实时检测")
        if not ok:
            InfoBar.warning("任务已在运行", reason, duration=4000,
                            position=InfoBarPosition.TOP, parent=self)
            return
        if not is_admin():
            InfoBar.warning("需要管理员", "请以管理员重启后再开始(游戏提权)。",
                            duration=4000, position=InfoBarPosition.TOP, parent=self)
        self._paused = False
        self._aborting = False
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(True)
        registry.set_stopper("实时检测", self._stop_workers_no_ui)
        if self.launch_switch.isChecked():
            self._show_status("自动启动游戏中…(到游戏后自动开始实时检测;仅前台时动作;F12 急停)")
            self._set_content("自动启动游戏中…")
            from workers.launch_worker import LaunchWorker
            self._launcher = LaunchWorker()
            self._launcher.sig_log.connect(self._append)
            self._launcher.sig_done_ok.connect(self._on_launch_then_detect)
            self._launcher.start()
        else:
            self._begin_detection()
    def _on_launch_then_detect(self, ok: bool) -> None:
        if self._launcher:
            self._launcher.wait(1500)
            self._launcher = None
        if self._aborting:
            self._maybe_reset_ui()
            return
        if not ok:
            self._append("自动启动未完成,仍尝试开始实时检测(无游戏则自动收尾)")
        # 游戏启动成功 → 按设置最小化窗口(让出前台给游戏)
        if ok:
            self._maybe_minimize_window()
        # 开了联动浇水 → 先浇水,浇完再检测;否则直接检测
        if self.water_switch.isChecked():
            self._begin_watering()
        else:
            self._begin_detection()

    def _maybe_minimize_window(self) -> None:
        """游戏启动后按设置最小化 HOKWorld 窗口。"""
        try:
            from config import cfg
            if not bool(cfg.get("minimize_after_game_start")):
                return
            from PySide6.QtWidgets import QApplication
            win = QApplication.instance().activeWindow()
            while win is not None and win.parentWidget() is not None:
                win = win.parentWidget()
            if win is not None:
                win.showMinimized()
                self._append("[最小化] HOKWorld 已最小化到任务栏")
        except Exception as exc:
            self._append(f"[最小化] 失败:{type(exc).__name__}")

    # ---- 联动浇水(游戏启动后→浇水→实时检测) ----
    def _begin_watering(self) -> None:
        from workers.water_worker import WaterWorker
        from config import cfg
        mode = "friends" if self.watering_page_mode() == "friends" else "self"
        # 退出模式统一走 cfg.water_exit_mode()(修复 AUTO-MAS 启动后脚本被关闭的 bug)
        # 旧的 auto_water_exit=True 不再强制覆盖新字段 auto_water_exit_mode
        exit_mode = cfg.water_exit_mode()
        self._water_exit_mode = exit_mode
        tail = {"none": "→ 实时检测", "game_only": "→ 仅退出游戏", "all": "→ 退出(供调度)"}.get(exit_mode, "→ 实时检测")
        self._show_status(f"[联动] 游戏已启动,开始浇水({mode})…{tail}")
        self._set_content("联动浇水中…")
        # WaterWorker 自己读 config 兜底,这里传 exit_after=False 让它走新逻辑
        self._water = WaterWorker(mode=mode, exit_after=False)
        self._water.sig_log.connect(self._append)
        self._water.sig_done.connect(self._on_water_done)
        self._water.start()

    def _on_water_done(self) -> None:
        if self._water:
            self._water.wait(1500)
            self._water = None
        if self._aborting:
            self._maybe_reset_ui()
            return
        # 退出方式:none=转入实时检测 / game_only=仅退出游戏,保留HOKWorld / all=退出游戏+App
        exit_mode = getattr(self, "_water_exit_mode", "none")
        if exit_mode == "all":
            self._append("[联动] 浇水完成,准备退出游戏和 HOKWorld(供调度)")
            self._exit_chain()
            return
        if exit_mode == "game_only":
            self._append("[联动] 浇水完成,游戏已退出;HOKWorld 保持运行")
            self._reset_ui_after_water()
            return
        self._append("[联动] 浇水完成,转入实时检测…")
        self._begin_detection()

    def _reset_ui_after_water(self) -> None:
        """仅退出游戏后,把实时检测页的 UI 复位到初始态(不退出 HOKWorld)。"""
        try:
            registry.finish("实时检测")
        except Exception:
            pass
        self._aborting = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self._set_content(self._DESC)
        self._show_status("已就绪")

    def _exit_chain(self) -> None:
        """联动浇水完成后退出整个链路,让外部调度器(如 AUTO-MAS)接管下一个任务。"""
        try:
            registry.finish("实时检测")
        except Exception:
            pass
        self._aborting = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self._set_content(self._DESC)
        self._append("[联动] 正在退出 HOKWorld…")
        import os
        os._exit(0)

    def watering_page_mode(self) -> str:
        """读取浇水页选的模式,联动时复用浇水页的设置。"""
        try:
            from config import cfg
            m = cfg.get("auto_water_mode")
            if m == "friends":
                return "friends"
        except Exception:
            pass
        return "self"


    def _begin_detection(self) -> None:
        from workers.story_worker import StoryWorker
        from workers.gather_worker import GatherWorker
        self._show_status("实时检测启动中…(无剧情不动作;游戏需前台;F12 急停)")
        self._worker = StoryWorker(self.nudge_switch.isChecked())
        self._worker.sig_log.connect(self._append)
        self._worker.sig_done.connect(self._on_done)
        self._set_content("运行中…")
        self._worker.start()
        if self.gather_switch.isChecked():
            self._gather = GatherWorker()
            self._gather.sig_log.connect(self._append)
            self._gather.sig_count.connect(lambda n: self._append(f"已采集 {n} 个材料"))
            self._gather.sig_done.connect(self._on_gather_done)
            self._gather.start()
        # 月卡检测：配置开了就常驻并行
        try:
            from config import cfg
            if bool(cfg.get("monthly_card_check")):
                from workers.monthly_card_worker import MonthlyCardWorker
                self._monthly = MonthlyCardWorker()
                self._monthly.sig_log.connect(self._append)
                self._monthly.sig_done.connect(self._on_monthly_done)
                self._monthly.start()
        except Exception:
            pass

    def _toggle_pause(self) -> None:
        if not (self._worker or self._launcher or self._water or self._monthly):
            return
        self._paused = not self._paused
        for w in (self._launcher, self._water, self._worker, self._gather, self._monthly):
            if w:
                w.set_paused(self._paused)
        self.pause_btn.setText("继续" if self._paused else "暂停")
        self.start_btn.setEnabled(self._paused)
        self._append("已暂停" if self._paused else "已继续")
        self._set_content("已暂停" if self._paused else "运行中…")

    def _stop(self) -> None:
        self._aborting = True
        self._append("停止中…")
        self._stop_workers_no_ui()

    def _stop_workers_no_ui(self) -> None:
        for w in (self._launcher, self._water, self._worker, self._gather, self._monthly):
            if w: w.stop()

    # ---- 完成回调 ----
    def _on_done(self) -> None:
        if self._worker:
            self._worker.wait(1500)
            self._worker = None
        if self._gather:
            self._gather.stop()
        self._maybe_reset_ui()

    def _on_gather_done(self) -> None:
        if self._gather:
            self._gather.wait(1500)
            self._gather = None
        self._maybe_reset_ui()

    def _on_monthly_done(self) -> None:
        if self._monthly:
            self._monthly.wait(1500)
            self._monthly = None
        self._maybe_reset_ui()

    def _maybe_reset_ui(self) -> None:
        if self._worker or self._gather or self._launcher or self._water or self._monthly:
            return
        registry.finish("实时检测")
        self._aborting = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(False)
        self._set_content(self._DESC)

    # ---- UI 辅助 ----
    def _set_content(self, text: str) -> None:
        try:
            self.card.card.setContent(text)
        except Exception:
            pass

    def _show_status(self, msg: str) -> None:
        self._last_msg = msg
        self.status_card.show()
        self.status.setText(msg)

    def _append(self, msg: str) -> None:
        self._last_msg = msg
        self.status.setText(msg)

    def emergency_stop(self) -> None:
        self._aborting = True
        stopped = False
        for w in (self._worker, self._gather, self._launcher, self._water, self._monthly):
            if w:
                w.stop()
                stopped = True
        if stopped:
            self._append("F12 急停")
        release_known_keys(self._append)

    # ====================================================================
    # 调度器入口(由 scheduler.py 通过回调调用,跑在主线程)
    # ====================================================================
    def schedule_start(self) -> None:
        """定时器:开始实时检测(若已在跑则忽略)。"""
        if self._worker or self._launcher or self._water:
            self._append("[定时] 实时检测已在运行,跳过")
            return
        self._append("[定时] 触发:开始实时检测")
        self._start()

    def schedule_stop(self) -> None:
        """定时器:停止实时检测。"""
        if not (self._worker or self._launcher or self._water or self._gather):
            self._append("[定时] 当前无任务运行,跳过停止")
            return
        self._append("[定时] 触发:停止实时检测")
        self._stop()

    def schedule_restart(self) -> None:
        """定时器:强制定时启动 —— 先停当前,等 2 秒收尾,再启动。

        用 QTimer.singleShot 把"启动"放到下一轮事件循环,避免和 stop 的
        收尾流程抢资源。"""
        from PySide6.QtCore import QTimer
        if self._worker or self._launcher or self._water or self._gather:
            self._append("[定时] 触发:强制重启 → 先停止当前任务")
            self._stop()
            # 等 2 秒让 worker 真正停下来再启动
            QTimer.singleShot(2000, self._restart_after_stop)
        else:
            self._append("[定时] 触发:强制重启 → 无运行任务,直接启动")
            self._start()

    def _restart_after_stop(self) -> None:
        """强制重启的"启动"阶段:检查是否真停了,再 start。"""
        if self._worker or self._launcher or self._water:
            # 还有 worker 在收尾,再等 1 秒
            from PySide6.QtCore import QTimer
            self._append("[定时] 任务仍在收尾,再等 1 秒…")
            QTimer.singleShot(1000, self._restart_after_stop)
            return
        self._append("[定时] 收尾完成,启动实时检测")
        self._start()

