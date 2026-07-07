"""钓鱼页面 — 自动完成多轮钓鱼:抛竿 → 上钩啦 → 拉杆 → 收线 → 结算。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from qfluentwidgets import (
    BodyLabel, CardWidget, ExpandGroupSettingCard, FluentIcon as FIF,
    IconWidget, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton,
    SpinBox, SwitchButton,
)

from ui.scroll_interface import ScrollInterface
from winenv import is_admin


class FishingInterface(ScrollInterface):
    _CARD_DESC = "自动完成多轮钓鱼:抛竿 → 上钩啦 → 拉杆 → 收线 → 结算"

    def __init__(self) -> None:
        super().__init__("fishingInterface")
        self._worker = None

        root = self.vbox
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        # 可展开任务卡片:折叠态显示开始/停止,下拉后才显示循环次数 / 完成后退出
        self.card = ExpandGroupSettingCard(FIF.GAME, "自动钓鱼", self._CARD_DESC, self)
        self.start_btn = PrimaryPushButton(FIF.PLAY, "开始")
        self.stop_btn = PushButton(FIF.PAUSE, "停止")
        self.stop_btn.setEnabled(False)
        self.card.addWidget(self.start_btn)
        self.card.addWidget(self.stop_btn)

        self.count_spin = SpinBox()
        self.count_spin.setRange(0, 9999)
        self.count_spin.setValue(0)
        self.count_spin.setFixedWidth(150)
        self.card.addGroup(FIF.SYNC, "循环次数", "目标钓鱼条数(0 = 只钓一次,达到后自动停止)", self.count_spin)
        self.exit_switch = SwitchButton()
        self.card.addGroup(FIF.POWER_BUTTON, "完成后退出", "完成任务后退出游戏 App", self.exit_switch)
        root.addWidget(self.card)

        # 单行运行状态条:点开始后才显示,只显示最新一条
        self.status_card = CardWidget()
        sl = QHBoxLayout(self.status_card)
        sl.setContentsMargins(16, 10, 16, 10)
        sl.setSpacing(10)
        self._status_icon = IconWidget(FIF.SYNC, self.status_card)
        self._status_icon.setFixedSize(16, 16)
        self.status = BodyLabel("")
        sl.addWidget(self._status_icon)
        sl.addWidget(self.status, 1)
        self.status_card.hide()
        root.addWidget(self.status_card)
        root.addStretch(1)

        self._last_msg = ""
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

    def _start(self) -> None:
        from workers.fish_worker import FishWorker
        if self._worker:
            return
        self._warn_admin()
        self._show_status("自动钓鱼启动中…(游戏需前台;F12 急停)")
        self._worker = FishWorker(self.count_spin.value(), self.exit_switch.isChecked())
        self._worker.sig_log.connect(self._append)
        self._worker.sig_count.connect(lambda n: self._set_card_content(self.card, f"运行中 · 已钓 {n}"))
        self._worker.sig_done.connect(self._on_done)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_card_content(self.card, "运行中…")
        self._worker.start()

    def _stop(self) -> None:
        if self._worker:
            self._append("停止中…")
            self._worker.stop()

    def _on_done(self) -> None:
        if self._worker:
            self._worker.wait(1500)
            self._worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_card_content(self.card, self._CARD_DESC)

    def _warn_admin(self) -> None:
        if not is_admin():
            InfoBar.warning("需要管理员", "请以管理员重启后再开始(游戏提权)。",
                            duration=4000, position=InfoBarPosition.TOP, parent=self)

    def _show_status(self, msg: str) -> None:
        self._last_msg = msg
        self.status_card.show()
        self._refresh_status()

    def _set_card_content(self, card, text: str) -> None:
        try:
            card.card.setContent(text)
        except Exception:
            pass

    def _append(self, msg: str) -> None:
        self._last_msg = msg
        self._refresh_status()

    def _refresh_status(self) -> None:
        self.status.setText(self._last_msg)

    def emergency_stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._append("F12 急停")
