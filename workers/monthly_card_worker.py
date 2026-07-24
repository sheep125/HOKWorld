"""MonthlyCardWorker — 月卡弹窗检测 Worker。

独立 QThread,可在实时检测/浇水阶段并行运行。
弹窗关闭后通过 sig_popup_closed 信号通知外部(用于联动重启浇水等)。
"""
from __future__ import annotations

from PySide6.QtCore import Signal

from workers.base import BaseBotWorker


class MonthlyCardWorker(BaseBotWorker):
    """月卡弹窗检测线程。"""

    sig_popup_closed = Signal()  # 弹窗被成功关闭时发射(用于联动)

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

        # 将 Qt 信号封装为回调,传给 Handler
        def _on_closed():
            try:
                self.sig_popup_closed.emit()
            except Exception:
                pass

        self.bot = MonthlyCardHandler(
            log=self.sig_log.emit,
            on_popup_closed=_on_closed,
        )
        try:
            self.bot.run()
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
