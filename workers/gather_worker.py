"""GatherWorker — 自动采集任务线程。"""
from __future__ import annotations

from workers.base import BaseBotWorker


class GatherWorker(BaseBotWorker):
    """实时自动采集线程(热重载 gather 代码)。"""

    def run(self) -> None:
        import importlib
        import winenv
        import capture
        import gather.recognizer
        import gather.picker
        for m in (winenv, capture, gather.recognizer, gather.picker):
            try:
                importlib.reload(m)
            except Exception:
                pass
        from gather.picker import GatherPicker
        self.bot = GatherPicker(log=self.sig_log.emit, on_count=self.sig_count.emit)
        try:
            self.bot.run()
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
