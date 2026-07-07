"""LoginWorker — 自动登录游戏任务线程。"""
from __future__ import annotations

from workers.base import BaseBotWorker


class LoginWorker(BaseBotWorker):
    """自动登录线程。"""

    def run(self) -> None:
        import importlib
        import water.login_bot
        import winenv
        for m in (water.login_bot, winenv):
            try:
                importlib.reload(m)
            except Exception:
                pass

        from config import cfg
        check = bool(cfg.get("monthly_card_check"))
        hour = int(cfg.get("monthly_card_hour"))
        window = int(cfg.get("monthly_card_window_mins"))

        from water.login_bot import LoginBot
        self.bot = LoginBot(
            log=self.sig_log.emit,
            check_monthly=check,
            monthly_hour=hour,
            monthly_window_mins=window,
        )
        try:
            ok = self.bot.run()
            self.sig_log.emit(f"[自动登录] {'完成' if ok else '未完成'}")
        except Exception as exc:
            self._log_error(exc)
        self.sig_done.emit()
