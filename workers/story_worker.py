"""StoryWorker — 剧情跳过任务线程。"""
from __future__ import annotations

from workers.base import BaseBotWorker


class StoryWorker(BaseBotWorker):
    """实时剧情跳过线程(热重载 story 代码)。"""

    def __init__(self, nudge: bool) -> None:
        super().__init__()
        self._nudge = nudge

    def run(self) -> None:
        import importlib
        import winenv
        import capture
        import story.recognizer
        import story.skipper
        for m in (winenv, capture, story.recognizer, story.skipper):
            try:
                importlib.reload(m)
            except Exception:
                pass
        from story.skipper import StorySkipper
        self.bot = StorySkipper(log=self.sig_log.emit, on_count=self.sig_count.emit)
        try:
            self.bot.run(nudge=self._nudge)
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
