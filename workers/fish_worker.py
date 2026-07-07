"""FishWorker — 钓鱼任务线程。"""
from __future__ import annotations

from workers.base import BaseBotWorker


class FishWorker(BaseBotWorker):
    """自动钓鱼线程(热重载 fishing 代码)。"""

    def __init__(self, count: int, exit_after: bool) -> None:
        super().__init__()
        self._count = count
        self._exit_after = exit_after

    def run(self) -> None:
        self._hot_reload()
        import winenv
        import fishing.matcher
        import fishing.fisher
        for m in (winenv, fishing.matcher, fishing.fisher):
            try:
                import importlib
                importlib.reload(m)
            except Exception:
                pass
        from fishing.fisher import FishingBot
        self.bot = FishingBot(log=self.sig_log.emit, on_count=self.sig_count.emit)
        try:
            self.bot.run(self._count, self._exit_after)
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
