"""设置页面(简洁卡片版):采集白名单/碰撞名单、时序抖动、运行状态。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PushSettingCard,
    SettingCard, SwitchSettingCard, TitleLabel,
)
from qfluentwidgets import ComboBox

from ui.list_edit_dialog import ListEditDialog
from ui.scroll_interface import ScrollInterface
from winenv import is_admin, relaunch_as_admin


class SettingsInterface(ScrollInterface):
    """设置(简洁卡片版):采集白名单(强制采)/ 碰撞名单(跳过)点开才编辑;时序抖动;运行状态。
    名单编辑的是「用户数据目录」里的文件(随更新/换机保留),不是安装目录的模板。
    """

    def __init__(self) -> None:
        super().__init__("settingsInterface")

        root = self.vbox
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)
        root.addWidget(TitleLabel("设置"))

        # 采集白名单 —— 强制采(优先级最高);点开才编辑
        self.whitelist_card = PushSettingCard(
            "编辑名单", FIF.ADD, "采集白名单(强制采)",
            "写在这里的识别到就一定采(盖过碰撞名单);也能强制采图标不是手型的东西")
        self.whitelist_card.clicked.connect(self._edit_whitelist)
        root.addWidget(self.whitelist_card)

        # 采集碰撞名单 —— 跳过;点开才编辑
        self.blacklist_card = PushSettingCard(
            "编辑名单", FIF.BROOM, "采集碰撞名单(跳过)",
            "不想自动采的(如渡石/滑索/冲云翼),点开编辑;采集时会跳过名单里的提示")
        self.blacklist_card.clicked.connect(self._edit_blacklist)
        root.addWidget(self.blacklist_card)

        # 全局行为 — 自动启动/退出
        from config import cfg
        self.auto_start_card = SwitchSettingCard(
            FIF.GAME, "启动程序后自动开始实时检测",
            "打开 HOKWorld 后自动开始实时检测(自动启动游戏+剧情跳过+采集)")
        self.auto_start_card.setChecked(bool(cfg.get("auto_start_realtime")))
        self.auto_start_card.checkedChanged.connect(lambda on: cfg.set("auto_start_realtime", bool(on)))
        root.addWidget(self.auto_start_card)

        # 开机自启(写注册表 HKCU\...\Run)
        self.autostart_card = SwitchSettingCard(
            FIF.SEND, "开机自启 HOKWorld",
            "Windows 登录后自动启动 HOKWorld(配合「启动后自动开始实时检测」实现全自动无人值守)")
        self.autostart_card.setChecked(self._is_autostart_on())
        self.autostart_card.checkedChanged.connect(self._on_autostart_toggle)
        root.addWidget(self.autostart_card)

        self.auto_exit_card = SwitchSettingCard(
            FIF.POWER_BUTTON, "游戏退出时自动退出应用",
            "检测到游戏关闭后自动退出 HOKWorld")
        self.auto_exit_card.setChecked(bool(cfg.get("auto_exit_app")))
        self.auto_exit_card.checkedChanged.connect(lambda on: cfg.set("auto_exit_app", bool(on)))
        root.addWidget(self.auto_exit_card)

        # 联动浇水(游戏启动后→浇水→实时检测)
        self.auto_water_card = SwitchSettingCard(
            FIF.CAFE, "游戏启动后自动浇水",
            "实时检测页「游戏启动后自动浇水」开关的默认值;"
            "开机自动开始实时检测时,游戏启动后会先浇水再检测")
        self.auto_water_card.setChecked(bool(cfg.get("auto_water_after_game")))
        self.auto_water_card.checkedChanged.connect(lambda on: cfg.set("auto_water_after_game", bool(on)))
        root.addWidget(self.auto_water_card)

        # 联动浇水完成后的退出方式(供 AUTO-MAS 等外部脚本调度)
        # 统一走 cfg.water_exit_mode() 解析(避免老字段覆盖新字段的优先级冲突)
        from config import cfg
        _cur_exit_mode = cfg.water_exit_mode()
        self.water_exit_card = SettingCard(
            FIF.POWER_BUTTON, "联动浇水完成后",
            "浇水完成后的动作:不退出(继续实时检测) / 仅退出游戏(保留HOKWorld) / 退出游戏和HOKWorld(供调度)",
            self)
        self.water_exit_combo = ComboBox(self.water_exit_card)
        self.water_exit_combo.addItems(["不退出(继续实时检测)", "仅退出游戏", "退出游戏和HOKWorld"])
        _map = {"none": 0, "game_only": 1, "all": 2}
        _rmap = {0: "none", 1: "game_only", 2: "all"}
        self.water_exit_combo.setCurrentIndex(_map.get(_cur_exit_mode, 0))
        self.water_exit_combo.setFixedWidth(220)
        self.water_exit_combo.currentIndexChanged.connect(
            lambda i: cfg.set("auto_water_exit_mode", _rmap.get(i, "none")))
        self.water_exit_card.hBoxLayout.addWidget(self.water_exit_combo, 0, Qt.AlignRight)
        self.water_exit_card.hBoxLayout.addSpacing(16)
        root.addWidget(self.water_exit_card)

        # 游戏启动后最小化 HOKWorld 窗口
        self.minimize_card = SwitchSettingCard(
            FIF.BACK_TO_WINDOW, "游戏启动后最小化",
            "游戏启动成功后自动最小化 HOKWorld 到任务栏,"
            "把前台让给游戏(适合无人值守/被外部调度时)")
        self.minimize_card.setChecked(bool(cfg.get("minimize_after_game_start")))
        self.minimize_card.checkedChanged.connect(lambda on: cfg.set("minimize_after_game_start", bool(on)))
        root.addWidget(self.minimize_card)

        # 月卡检测(OCR 常驻模式,不依赖时间窗口)
        self.monthly_card = SwitchSettingCard(
            FIF.DATE_TIME, "月卡检测",
            "游戏启动后常驻并行检测,OCR识别月卡/奖励弹窗并点击关闭(不依赖ESC,一日仅触发一次)")
        self.monthly_card.setChecked(bool(cfg.get("monthly_card_check")))
        self.monthly_card.checkedChanged.connect(lambda on: cfg.set("monthly_card_check", bool(on)))
        root.addWidget(self.monthly_card)

        # 游戏启动器路径(留空=自动定位;手动选择更稳)
        self.game_path_card = PushSettingCard(
            "选择…", FIF.GAME, "游戏启动器路径",
            self._game_path_display())
        self.game_path_card.clicked.connect(self._pick_game_exe)
        root.addWidget(self.game_path_card)

        # 时序抖动 —— 开关
        from config import cfg
        self.jitter_card = SwitchSettingCard(
            FIF.ROBOT, "时序抖动", "光标移动时添加细微随机手颤,更拟人(默认关闭)")
        self.jitter_card.setChecked(bool(cfg.get("timing_jitter")))
        self.jitter_card.checkedChanged.connect(lambda on: cfg.set("timing_jitter", bool(on)))
        root.addWidget(self.jitter_card)

        # 定时调度 —— 嵌入式卡片(总开关 + 条目列表)
        root.addWidget(TitleLabel("定时调度"))
        from ui.schedule_card import ScheduleCard
        self.schedule_card = ScheduleCard(self)
        root.addWidget(self.schedule_card)

        # 运行状态 —— 管理员 + 急停;非管理员时右侧给「以管理员重启」
        if is_admin():
            self.status_card = SettingCard(
                FIF.UPDATE, "运行状态", "管理员运行:是 · 可向游戏发送键鼠 · 急停热键 F12")
        else:
            self.status_card = PushSettingCard(
                "以管理员重启", FIF.UPDATE, "运行状态",
                "管理员运行:否 · 合成键鼠会被拦截(识别到却按不动) · 急停热键 F12")
            self.status_card.clicked.connect(self._relaunch_admin)
        root.addWidget(self.status_card)

        root.addStretch(1)

    # ---- 名单编辑(点开;编辑的是用户数据目录里的文件)----
    def _edit_whitelist(self) -> None:
        from gather.recognizer import whitelist_file
        self._edit_list(
            whitelist_file(), "采集白名单(强制采)",
            "写「一定要采的」——一行一个,识别到就一定采(优先级最高,能盖过碰撞名单;# 开头是说明)。",
            "一行一个,例如:\n某稀有材料\n某宝箱", "白名单")

    def _edit_blacklist(self) -> None:
        from gather.recognizer import blacklist_file
        self._edit_list(
            blacklist_file(), "采集碰撞名单(跳过)",
            "填「额外想跳过的」——一行一个(渡石/滑索/冲云翼等已内置);提示里出现这些字就跳过。",
            "一行一个,例如:\n某不想采的交互", "碰撞名单")

    def _edit_list(self, file, title, tip, placeholder, label) -> None:
        dlg = ListEditDialog(file, title, tip, placeholder, self.window())
        if not dlg.exec():
            return
        text = dlg.text()
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding="utf-8")
        except Exception as e:
            InfoBar.error("保存失败", str(e), duration=4000,
                          position=InfoBarPosition.TOP, parent=self)
            return
        n = len([ln for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")])
        InfoBar.success("已保存", f"{label}已写入({n} 条),下次「开始」采集时生效。",
                        duration=3000, position=InfoBarPosition.TOP, parent=self)

    # ---- 游戏启动器路径 ----
    def _game_path_display(self) -> str:
        """返回设置卡片上显示的当前路径文案。"""
        from config import cfg
        p = cfg.get("game_path")
        if p:
            # 路径可能很长 → 只显示文件名 + 父目录
            import os
            name = os.path.basename(p)
            parent = os.path.basename(os.path.dirname(p))
            return f"当前: {parent}\\{name}  (留空=自动定位)"
        return "留空=自动定位(注册表/开始菜单);点击「选择」手动指定启动器 exe"

    def _pick_game_exe(self) -> None:
        """弹文件选择对话框,让用户选 王者荣耀世界.exe 启动器。"""
        from PySide6.QtWidgets import QFileDialog
        from config import cfg

        # 默认打开当前路径的父目录(或 C:\Game)
        cur = cfg.get("game_path") or ""
        start_dir = ""
        if cur:
            import os
            start_dir = os.path.dirname(cur)
        if not start_dir or not os.path.isdir(start_dir):
            start_dir = r"C:\Game"

        path, _ = QFileDialog.getOpenFileName(
            self, "选择《王者荣耀世界》启动器", start_dir,
            "可执行文件 (*.exe);;所有文件 (*.*)")
        if not path:
            return

        cfg.set("game_path", path)
        # 更新卡片显示
        self.game_path_card.setContent(self._game_path_display())
        InfoBar.success("已保存", f"启动器路径已设置:{path}", duration=3000,
                        position=InfoBarPosition.TOP, parent=self)

    def _relaunch_admin(self) -> None:
        try:
            relaunch_as_admin()
        except Exception as e:
            InfoBar.error("无法提权重启", str(e), duration=4000,
                          position=InfoBarPosition.TOP, parent=self)

    # ---- 开机自启 ----
    def _is_autostart_on(self) -> bool:
        try:
            from winenv import is_autostart_enabled
            return is_autostart_enabled()
        except Exception:
            return False

    def _on_autostart_toggle(self, on: bool) -> None:
        try:
            from winenv import enable_autostart, disable_autostart
            if on:
                ok = enable_autostart()
                msg = "已写入注册表,下次开机自动启动" if ok else "写入失败,请检查权限"
                level = InfoBar.success if ok else InfoBar.error
            else:
                ok = disable_autostart()
                msg = "已从注册表移除,不再开机自启" if ok else "移除失败,请手动删除注册表项"
                level = InfoBar.success if ok else InfoBar.warning
            level("开机自启", msg, duration=3000,
                  position=InfoBarPosition.TOP, parent=self)
            # 同步开关显示状态(操作失败时回退)
            if not ok:
                self.autostart_card.setChecked(not on)
        except Exception as e:
            InfoBar.error("开机自启", f"操作失败:{e}", duration=4000,
                          position=InfoBarPosition.TOP, parent=self)
            self.autostart_card.setChecked(not on)
