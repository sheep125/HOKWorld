"""HOKWorld 控制台 — Fluent 界面。默认以管理员启动(发真实输入需要),全局 F12 急停。"""
from __future__ import annotations

import sys

# pythonw.exe(无控制台)下 sys.stdout/stderr 为 None,import 期打印(如 qfluentwidgets 横幅)会崩 → 兜个哑流
if sys.stdout is None or sys.stderr is None:
    import os
    _null = open(os.devnull, "w")
    sys.stdout = sys.stdout or _null
    sys.stderr = sys.stderr or _null

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qfluentwidgets import (
    FluentIcon as FIF, FluentWindow, NavigationItemPosition, setTheme, setThemeColor, Theme,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import cfg                                # noqa: E402
from paths import resource_path                        # noqa: E402
from runtime_guard import registry, release_known_keys  # noqa: E402
from version import APP_DISPLAY, __version__           # noqa: E402
from winenv import center_window, hide_console, is_admin, relaunch_as_admin, set_app_id  # noqa: E402

APP_VERSION = f"v{__version__}"

try:
    from pynput import keyboard
except Exception:
    keyboard = None

ASSETS = resource_path("assets")


def _nav_icon(name, fallback):
    """assets/ 下有同名 png 就用,否则回退内置图标。"""
    p = ASSETS / name
    return QIcon(str(p)) if p.exists() else fallback


# ---- Interfaces (lazy imports inside) ----
from ui.about import AboutInterface              # noqa: E402
from ui.fishing import FishingInterface          # noqa: E402
from ui.realtime import RealtimeInterface        # noqa: E402
from ui.settings import SettingsInterface        # noqa: E402
from ui.watering import WateringInterface        # noqa: E402


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"HOKWorld  {APP_VERSION}  ·  王者荣耀世界")
        self.setWindowIcon(_nav_icon("app.png", QIcon()))
        try:
            self.titleBar.iconLabel.hide()
        except Exception:
            pass
        self.resize(1180, 720)

        self.realtime = RealtimeInterface()
        self.fishing = FishingInterface()
        self.watering = WateringInterface()
        self.settings = SettingsInterface()
        self.about = AboutInterface()
        self.addSubInterface(self.realtime, _nav_icon("realtime.png", FIF.VIDEO), "实时检测")
        self.addSubInterface(self.fishing, _nav_icon("task.png", FIF.GAME), "独立任务")
        self.addSubInterface(self.watering, _nav_icon("water.png", FIF.CAFE), "浇水")
        self.addSubInterface(self.settings, FIF.SETTING, "设置", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.about, FIF.INFO, "关于", NavigationItemPosition.BOTTOM)

        self.navigationInterface.setExpandWidth(170)
        self.navigationInterface.setMinimumExpandWidth(0)
        self.navigationInterface.setCollapsible(True)
        self.navigationInterface.setMenuButtonVisible(True)
        self.navigationInterface.setReturnButtonVisible(False)
        try:
            self.navigationInterface.expand(useAni=False)
        except Exception:
            pass

        self._hotkey = None
        if keyboard is not None:
            self._hotkey = keyboard.Listener(on_press=self._on_key)
            self._hotkey.start()

    def _on_key(self, key) -> None:
        try:
            if key == keyboard.Key.f12:
                registry.stop_all("F12 急停")
                self.fishing.emergency_stop()
                self.realtime.emergency_stop()
                self.watering.emergency_stop()
        except Exception:
            pass


def build_window() -> MainWindow:
    setTheme(Theme.LIGHT)
    setThemeColor("#2dd4a8")
    return MainWindow()


def main() -> int:
    hide_console()
    if not is_admin():
        relaunch_as_admin()
        return 0
    set_app_id()
    # 程序启动日志(AUTO-MAS 可监控)
    try:
        from task_log import task_info, task_connected
        from version import __version__
        task_info(f"HOKWorld v{__version__} 启动")
        task_connected(True, "HOKWorld 已启动")
    except Exception:
        pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(_nav_icon("app.png", QIcon()))
    win = build_window()
    center_window(win)
    win.show()

    # 启动后自动开始实时检测
    if bool(cfg.get("auto_start_realtime")):
        from PySide6.QtCore import QTimer
        def _auto_realtime():
            from runtime_guard import dev_log
            try:
                win.realtime._start()
            except Exception as exc:
                dev_log("auto_start_realtime 失败", exc)
        QTimer.singleShot(5000, _auto_realtime)

    # 启动定时调度器(若总开关已开)
    if bool(cfg.get("schedule_enabled")):
        try:
            import scheduler as sch
            sch.set_callbacks(
                on_start=win.realtime.schedule_start,
                on_stop=win.realtime.schedule_stop,
                on_restart=win.realtime.schedule_restart,
            )
            sch.start_scheduler()
        except Exception as exc:
            from runtime_guard import dev_log
            dev_log("start_scheduler 失败", exc)

    # 游戏退出时自动退出应用
    if bool(cfg.get("auto_exit_app")):
        from PySide6.QtCore import QTimer
        def _check_game():
            from winenv import find_game_hwnd
            import psutil
            hwnd = find_game_hwnd()
            if not hwnd:
                try:
                    for p in psutil.process_iter(['name']):
                        if p.info['name'] and p.info['name'].startswith('KingLauncher'):
                            return  # 启动器还在,游戏可能重启
                except Exception:
                    pass
                app.quit()
        auto_exit_timer = QTimer()
        auto_exit_timer.timeout.connect(_check_game)
        auto_exit_timer.start(10000)  # 每10秒检查一次

    # 程序退出时记录日志(AUTO-MAS 监控进程消失可结合本条判断)
    try:
        from task_log import task_info
        app.aboutToQuit.connect(lambda: task_info("HOKWorld 准备退出"))
    except Exception:
        pass

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
