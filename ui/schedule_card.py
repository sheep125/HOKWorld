"""定时调度卡片 — 嵌入设置页的可展开卡片。

UI 组成:
  · 总开关 (SwitchButton) — 开关整个调度器
  · 3 个默认格子 + 用户可"+ 添加一条"扩展
  · 每条:启用 / 时间(小时下拉+分钟下拉) / 动作(开始|停止|强制重启) / 标签(可选) / 删除

数据持久化:
  写入 config.schedule_entries (list) 和 config.schedule_enabled (bool)
  改完任何字段 → cfg.save() + scheduler.reload_entries() 实时生效
"""
from __future__ import annotations

from qfluentwidgets import (
    BodyLabel, CardWidget, CheckBox, ComboBox, FluentIcon as FIF,
    IconWidget, LineEdit, PushButton, StrongBodyLabel, SwitchButton,
)
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from scheduler import default_schedule, normalize_entry


class _ScheduleRow(QWidget):
    """单条调度项的 UI。"""

    def __init__(self, entry: dict, on_change, on_remove, parent=None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._on_remove = on_remove
        e = normalize_entry(entry)
        # 解析初始时分
        try:
            _hh, _mm = e["time"].split(":")
            init_hh, init_mm = int(_hh), int(_mm)
        except Exception:
            init_hh, init_mm = 8, 0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        # 启用复选框
        self.enable_cb = CheckBox()
        self.enable_cb.setChecked(e["enabled"])
        self.enable_cb.stateChanged.connect(self._changed)
        lay.addWidget(self.enable_cb)

        # 小时下拉(0-23)
        self.hour_combo = ComboBox()
        self.hour_combo.addItems([f"{h:02d}" for h in range(24)])
        self.hour_combo.setCurrentIndex(init_hh)
        self.hour_combo.setFixedWidth(62)
        self.hour_combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.hour_combo)

        lay.addWidget(BodyLabel(":"))

        # 分钟下拉(0-59)
        self.min_combo = ComboBox()
        self.min_combo.addItems([f"{m:02d}" for m in range(60)])
        self.min_combo.setCurrentIndex(init_mm)
        self.min_combo.setFixedWidth(62)
        self.min_combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.min_combo)

        # 动作下拉
        self.action_combo = ComboBox()
        self.action_combo.addItems(["开始", "停止", "强制重启"])
        idx = {"start": 0, "stop": 1, "restart": 2}.get(e["action"], 0)
        self.action_combo.setCurrentIndex(idx)
        self.action_combo.setFixedWidth(100)
        self.action_combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.action_combo)

        # 标签(可选)
        self.label_edit = LineEdit()
        self.label_edit.setPlaceholderText("备注(可选)")
        self.label_edit.setText(e.get("label", ""))
        self.label_edit.setFixedWidth(130)
        self.label_edit.textChanged.connect(self._changed)
        lay.addWidget(self.label_edit)

        lay.addStretch(1)

        # 删除按钮
        self.del_btn = PushButton(FIF.DELETE, "")
        self.del_btn.setFixedSize(36, 32)
        self.del_btn.setToolTip("删除这条")
        self.del_btn.clicked.connect(self._remove)
        lay.addWidget(self.del_btn)

    # ---- 数据导出 ----
    def to_entry(self) -> dict:
        action_map = {0: "start", 1: "stop", 2: "restart"}
        hh = self.hour_combo.currentIndex()
        mm = self.min_combo.currentIndex()
        return {
            "enabled": self.enable_cb.isChecked(),
            "time": f"{hh:02d}:{mm:02d}",
            "action": action_map.get(self.action_combo.currentIndex(), "start"),
            "label": self.label_edit.text().strip(),
        }

    # ---- 信号 ----
    def _changed(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def _remove(self) -> None:
        if self._on_remove:
            self._on_remove(self)


class ScheduleCard(CardWidget):
    """定时调度的整张卡片(总开关 + 条目列表 + 添加按钮)。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[_ScheduleRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # 标题行:图标 + 标题 + 总开关
        head = QHBoxLayout()
        head.setSpacing(10)
        icon = IconWidget(FIF.DATE_TIME, self)
        icon.setFixedSize(20, 20)
        head.addWidget(icon)
        title = StrongBodyLabel("定时调度", self)
        head.addWidget(title)
        head.addStretch(1)
        self.master_switch = SwitchButton()
        head.addWidget(self.master_switch)
        outer.addLayout(head)

        desc = BodyLabel(
            "到点自动开始 / 停止 / 强制重启实时检测(强制定时启动 = 先停当前,等收尾后重启)。"
            "用于无人值守场景。改任意字段即时保存并生效。"
        )
        desc.setWordWrap(True)
        desc.setEnabled(False)
        outer.addWidget(desc)

        # 条目容器
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        outer.addLayout(self.rows_box)

        # 添加按钮
        self.add_btn = PushButton(FIF.ADD, "添加一条")
        self.add_btn.clicked.connect(self._add_row)
        outer.addWidget(self.add_btn)

        # ---- 加载 / 保存 ----
        from config import cfg
        self.master_switch.setChecked(bool(cfg.get("schedule_enabled")))
        self.master_switch.checkedChanged.connect(self._on_master_toggle)

        entries = cfg.get("schedule_entries")
        if not isinstance(entries, list) or not entries:
            entries = default_schedule()
        for e in entries:
            self._add_row(e, persist=False)

    # ---- 行管理 ----
    def _add_row(self, entry: dict | None = None, persist: bool = True) -> None:
        if entry is None:
            entry = {"enabled": False, "time": "08:00", "action": "start", "label": ""}
        row = _ScheduleRow(entry, on_change=self._save, on_remove=self._remove_row, parent=self)
        self._rows.append(row)
        self.rows_box.addWidget(row)
        if persist:
            self._save()

    def _remove_row(self, row: _ScheduleRow) -> None:
        try:
            self.rows_box.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
            self._rows.remove(row)
            self._save()
        except Exception:
            pass

    # ---- 总开关 ----
    def _on_master_toggle(self, on: bool) -> None:
        from config import cfg
        cfg.set("schedule_enabled", bool(on))
        try:
            import scheduler as sch
            if on:
                sch.set_callbacks(
                    on_start=self._rt_start,
                    on_stop=self._rt_stop,
                    on_restart=self._rt_restart,
                )
                sch.start_scheduler()
            else:
                sch.stop_scheduler()
        except Exception:
            pass
        self._save()

    # ---- 保存到 config + 通知调度器 ----
    def _save(self) -> None:
        from config import cfg
        entries = [r.to_entry() for r in self._rows]
        cfg.set("schedule_entries", entries)
        try:
            import scheduler as sch
            sch.reload_entries()
        except Exception:
            pass

    # ---- 调度器回调:操作实时检测页 ----
    def _realtime(self):
        try:
            from PySide6.QtWidgets import QApplication
            win = QApplication.instance().activeWindow()
            while win is not None and win.parentWidget() is not None:
                win = win.parentWidget()
            # MainWindow 上挂的 realtime
            return getattr(win, "realtime", None) if win else None
        except Exception:
            return None

    def _rt_start(self) -> None:
        rt = self._realtime()
        if rt:
            rt.schedule_start()

    def _rt_stop(self) -> None:
        rt = self._realtime()
        if rt:
            rt.schedule_stop()

    def _rt_restart(self) -> None:
        rt = self._realtime()
        if rt:
            rt.schedule_restart()
