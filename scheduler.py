"""定时调度器 — 后台轮询触发时间,通过 Qt 信号通知主线程执行操作。

设计要点:
  1. 调度器跑在 QThread 里,只负责"到点发信号",不直接碰 UI/Worker
  2. 主线程收到信号后,执行对应的操作(start_realtime / stop_realtime / 强制重启)
  3. 触发规则:
     - "强制重启" = 先 stop 当前实时检测 → 等 stop 完成(由 stop_callback 同步返回)→ 再 start
     - 每条任务带 enabled / time("HH:MM") / action(start|stop|restart)
     - 同一时间多点触发时,先执行 stop 类,再执行 start 类,避免冲突
  4. 调度器只在每分钟 0 秒附近检查一次,平时 sleep,占用极低
"""
from __future__ import annotations

import threading
import time
import datetime as _dt
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


# ---- 数据模型 ----
VALID_ACTIONS = ("start", "stop", "restart")


def default_schedule() -> list[dict]:
    """3 个默认空格子,用户填时间和动作即可启用。"""
    return [
        {"enabled": False, "time": "08:00", "action": "start",   "label": "早上启动"},
        {"enabled": False, "time": "12:00", "action": "restart", "label": "中午强制重启"},
        {"enabled": False, "time": "23:30", "action": "stop",    "label": "晚上停止"},
    ]


def normalize_entry(d: dict) -> dict:
    """规范化一条调度项,补缺字段、校验值。"""
    if not isinstance(d, dict):
        d = {}
    enabled = bool(d.get("enabled", False))
    t = str(d.get("time", "08:00")).strip()
    # 校验 HH:MM
    try:
        _hh, _mm = t.split(":")
        hh, mm = int(_hh), int(_mm)
        assert 0 <= hh <= 23 and 0 <= mm <= 59
        t = f"{hh:02d}:{mm:02d}"
    except Exception:
        t = "08:00"
    action = str(d.get("action", "start")).lower()
    if action not in VALID_ACTIONS:
        action = "start"
    label = str(d.get("label", "")).strip()
    return {"enabled": enabled, "time": t, "action": action, "label": label}


# ---- 调度器线程 ----
class SchedulerWorker(QThread):
    """后台轮询:每 30 秒检查一次,匹配到点就 emit triggered。

    Signals:
        triggered(str action, str label) — action ∈ start|stop|restart
    """
    triggered = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        self._stop_flag = threading.Event()
        self._last_fired: str = ""        # "HH:MM" 最近一次触发的时间,防同一分钟重复触发

    def set_entries(self, entries: list[dict]) -> None:
        """主线程调用:更新调度表。"""
        norm = [normalize_entry(e) for e in (entries or [])]
        with self._lock:
            self._entries = norm

    def stop(self) -> None:
        self._stop_flag.set()

    def run(self) -> None:
        while not self._stop_flag.is_set():
            try:
                now = _dt.datetime.now()
                cur = f"{now.hour:02d}:{now.minute:02d}"
                if cur != self._last_fired:
                    with self._lock:
                        snapshot = list(self._entries)
                    fired: list[tuple[str, str]] = []
                    for e in snapshot:
                        if e["enabled"] and e["time"] == cur:
                            fired.append((e["action"], e["label"] or e["action"]))
                    if fired:
                        # 同一分钟内:先 stop / restart,再 start,避免任务互斥冲突
                        fired.sort(key=lambda x: 0 if x[0] in ("stop", "restart") else 1)
                        for action, label in fired:
                            self.triggered.emit(action, label)
                        self._last_fired = cur
            except Exception:
                pass
            # 30 秒滚一次,既省 CPU,又保证不会错过任何一分钟
            self._stop_flag.wait(30.0)


# ---- 全局单例管理 ----
# 由 app.py 在 main() 里 start_scheduler() / stop_scheduler()
_scheduler: SchedulerWorker | None = None
_on_start: Callable[[], None] | None = None      # 由 realtime 页注入
_on_stop: Callable[[], None] | None = None       # 由 realtime 页注入
_on_restart: Callable[[], None] | None = None    # 由 realtime 页注入


def set_callbacks(on_start: Callable[[], None] | None = None,
                  on_stop: Callable[[], None] | None = None,
                  on_restart: Callable[[], None] | None = None) -> None:
    """注入操作回调。任意一项为 None 表示不更新。"""
    global _on_start, _on_stop, _on_restart
    if on_start is not None:
        _on_start = on_start
    if on_stop is not None:
        _on_stop = on_stop
    if on_restart is not None:
        _on_restart = on_restart


def start_scheduler() -> None:
    """启动全局调度器,从 config 读条目。"""
    global _scheduler
    if _scheduler is not None and _scheduler.isRunning():
        return
    from config import cfg
    entries = cfg.get("schedule_entries")
    if not isinstance(entries, list):
        entries = default_schedule()
    _scheduler = SchedulerWorker()
    _scheduler.set_entries(entries)
    _scheduler.triggered.connect(_dispatch)
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.stop()
            _scheduler.wait(1500)
        except Exception:
            pass
        _scheduler = None


def reload_entries() -> None:
    """设置页改了调度表后调用,实时生效,无需重启。"""
    global _scheduler
    if _scheduler is None:
        start_scheduler()
        return
    from config import cfg
    entries = cfg.get("schedule_entries")
    if not isinstance(entries, list):
        entries = default_schedule()
    _scheduler.set_entries(entries)


def _dispatch(action: str, label: str) -> None:
    """Qt 信号回调:跑在主线程。"""
    try:
        if action == "start" and _on_start:
            _on_start()
        elif action == "stop" and _on_stop:
            _on_stop()
        elif action == "restart" and _on_restart:
            _on_restart()
    except Exception:
        pass
