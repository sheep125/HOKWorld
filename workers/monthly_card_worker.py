"""MonthlyCardWorker — 月卡弹窗检测 Worker。

独立 QThread,可在实时检测阶段并行运行。
"""
from __future__ import annotations

from workers.base import BaseBotWorker


class MonthlyCardWorker(BaseBotWorker):
    """月卡弹窗检测线程。"""

    def __init__(self) -> None:
        super().__init__()

    def run(self) -> None:
        import importlib
        import monthly_card
        try:
            importlib.reload(monthly_card)
        except Exception:
            pass
        from monthly_card import MonthlyCardHandler
        self.bot = MonthlyCardHandler(log=self.sig_log.emit)
        try:
            self.bot.run()
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
