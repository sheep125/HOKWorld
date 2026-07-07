"""浇水任务页 — 自动给自己/好友的农场浇水。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    BodyLabel, CardWidget, ComboBox, ExpandGroupSettingCard, FluentIcon as FIF,
    IconWidget, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, SpinBox,
    SwitchButton,
)
from ui.scroll_interface import ScrollInterface
from winenv import is_admin


class WateringInterface(ScrollInterface):
    _CARD_DESC = "自动浇水:传送到农田后按W+左键循环浇水"

    def __init__(self) -> None:
        super().__init__("wateringInterface")
        self._worker = None

        root = self.vbox
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self.card = ExpandGroupSettingCard(FIF.CAFE, "自动浇水", self._CARD_DESC, self)
        self.start_btn = PrimaryPushButton(FIF.PLAY, "开始")
        self.stop_btn = PushButton(FIF.PAUSE, "停止")
        self.stop_btn.setEnabled(False)
        self.card.addWidget(self.start_btn)
        self.card.addWidget(self.stop_btn)

        self.mode_combo = ComboBox()
        self.mode_combo.addItems(["自己农场", "好友农场"])
        # 从 config 读取上次选择的模式
        from config import cfg
        _saved = cfg.get("auto_water_mode")
        self.mode_combo.setCurrentIndex(0 if _saved != "friends" else 1)
        self.mode_combo.setFixedWidth(140)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.card.addGroup(FIF.CAFE, "浇水模式", "自己农场=居所封面路线;好友农场=遍历好友列表;联动浇水也用这个模式", self.mode_combo)

        self.exit_switch = SwitchButton()
        self.card.addGroup(FIF.POWER_BUTTON, "完成后退出",
                           "完成后自动关闭游戏进程和HOKWorld\n"
                           "(游戏进程名可在设置→游戏进程名称中修改,默认NGR-Win64-Shipping.exe)",
                           self.exit_switch)
        root.addWidget(self.card)

        self.status_card = CardWidget()
        sl = QHBoxLayout(self.status_card)
        sl.setContentsMargins(16, 10, 16, 10)
        sl.setSpacing(10)
        self._status_icon = IconWidget(FIF.CAFE, self.status_card)
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
        from workers.water_worker import WaterWorker
        if self._worker:
            return
        if not is_admin():
            InfoBar.warning("需要管理员", "请以管理员重启后再开始", duration=4000, position=InfoBarPosition.TOP, parent=self)
        mode_map = {"自己农场": "self", "好友农场": "friends"}
        m = mode_map.get(self.mode_combo.currentText(), "self")
        self._worker = WaterWorker(mode=m, exit_after=self.exit_switch.isChecked())
        self._worker.sig_log.connect(self._append)
        self._worker.sig_done.connect(self._on_done)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_content("运行中…")
        self._show_status(f"[浇水] {self.mode_combo.currentText()} 开始…")
        self._worker.start()

    def _on_mode_changed(self, text: str) -> None:
        """浇水模式切换时持久化,联动浇水时读取同一设置。"""
        from config import cfg
        cfg.set("auto_water_mode", "friends" if text == "好友农场" else "self")

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._append("停止中…")

    def _on_done(self) -> None:
        w = self._worker
        if w:
            w.wait(1500)
            if getattr(w, "_exit_after", False):
                self._do_exit()
            self._worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_content(self._CARD_DESC)

    def _do_exit(self) -> None:
        import subprocess, sys
        try:
            subprocess.run(["taskkill", "/f", "/im", "HOKWorld.exe"], capture_output=True)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
        except Exception:
            sys.exit(0)

    def _show_status(self, msg: str) -> None:
        self._last_msg = msg
        self.status_card.show()
        self.status.setText(msg)

    def _set_content(self, text: str) -> None:
        try:
            self.card.card.setContent(text)
        except Exception:
            pass

    def _append(self, msg: str) -> None:
        self._last_msg = msg
        self.status.setText(msg)

    def emergency_stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._append("F12 急停")
