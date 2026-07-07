"""BaseBotWorker — 消除重复:所有 bot Worker 共用的 stop / pause / done / log 模式。

子类只需:
  1. __init__ 里设置 self.bot = None
  2. 实现 run()，内部创建 bot、调用 bot.run()、emit sig_log/sig_count/sig_done
  3. run() 开头 importlib.reload 相关模块实现热重载
  4. 异常由基类自动 logging

不需要为每个 bot 再写一套 stop() / set_paused() / 线程清理。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class BaseBotWorker(QThread):
    """所有 bot worker 的抽象基类:

    Signals:
      sig_log(str)   — 日志消息,由 UI 显示
      sig_count(int) — 计数更新(钓鱼计数 / 采集计数 等)
      sig_done()     — 任务完成

    生命周期:
      start() → run() → sig_done.emit() → 调用方 wait(1500) → worker = None
    """
    sig_log = Signal(str)
    sig_count = Signal(int)
    sig_done = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.bot = None

    # ---- 控制接口 ----
    def stop(self) -> None:
        """停止当前 bot(由外部调用:停止按钮 / F12 急停)"""
        if self.bot:
            self.bot.stop()

    def set_paused(self, on: bool) -> None:
        """暂停 / 恢复(由外部调用:暂停按钮)"""
        if self.bot and hasattr(self.bot, "set_paused"):
            self.bot.set_paused(on)

    # ---- 辅助方法 ----
    def _log_error(self, exc: BaseException) -> None:
        """统一的异常日志格式"""
        self.sig_log.emit(f"[错误] {type(exc).__name__}: {exc}")

    def _hot_reload(self, *modules) -> None:
        """热重载指定模块:改逻辑后点开始即生效,无需重启控制台"""
        import importlib
        for m in modules:
            try:
                importlib.reload(m)
            except Exception:
                pass
