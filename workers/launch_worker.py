"""LaunchWorker — 自动启动游戏线程。"""
from __future__ import annotations

from PySide6.QtCore import Signal

from runtime_guard import dev_log, release_known_keys
from workers.base import BaseBotWorker


class LaunchWorker(BaseBotWorker):
    """自动启动游戏线程(热重载 launcher;**不**重载 fishing.matcher,保住 OCR 单例不被重置)。"""
    sig_done_ok = Signal(bool)        # 是否成功进入游戏(已点「开始游戏」)

    def __init__(self) -> None:
        super().__init__()

    def run(self) -> None:
        import importlib
        from task_log import task_started, task_ok, task_failed, task_error, task_connected, task_info
        task_started("启动游戏")
        try:
            import winenv
            import capture
            import launcher
            for m in (winenv, capture, launcher):
                try:
                    importlib.reload(m)
                except Exception:
                    pass
            from launcher import GameLauncher
        except Exception as exc:
            dev_log("加载 launcher 失败,跳过自动启动", exc)
            self.sig_log.emit(f"自动启动模块加载失败,已跳过(不影响实时检测):{type(exc).__name__}")
            task_error(exc, stage="launcher_load")
            task_failed(f"启动器加载失败 {type(exc).__name__}")
            self.sig_done.emit()
            self.sig_done_ok.emit(False)
            return
        self.bot = GameLauncher(log=self._log)
        ok = False
        try:
            ok = bool(self.bot.run())
        except Exception as exc:
            dev_log("自动启动游戏线程异常", exc)
            release_known_keys(self.sig_log.emit)
            self._log_error(exc)
            self.sig_log.emit("自动启动出错,已跳过(不影响实时检测)")
            task_error(exc, stage="launcher_run")
            task_connected(False, f"启动异常 {type(exc).__name__}")
            task_failed(repr(exc))
        if ok:
            task_connected(True, "游戏已启动")
            task_ok("启动游戏")
            task_info("游戏启动成功,即将进入任务阶段")
        else:
            task_failed("启动游戏未完成")
        self.sig_done.emit()
        self.sig_done_ok.emit(ok)

    def _log(self, msg: str) -> None:
        dev_log(f"[launcher] {msg}")
        self.sig_log.emit(msg)
