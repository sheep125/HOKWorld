"""任务日志器 — 给 AUTO-MAS 等外部调度器监控用的格式化日志。

AUTO-MAS 的工作原理(参考 ScriptConfig.json):
  - 它扫描 LogPath 指定的文件
  - 用 LogTimeFormat + LogTimeStart/End 切片每行的时间戳
  - 用 ErrorLog 关键字(支持 | 分隔的多关键字)判定失败
  - 用 SuccessLog 关键字判定成功
  - LogPathFormat 支持按日期切换文件名(如 log-%Y%m%d.log)

本模块提供:
  task_log_dir()      — 日志目录(data/logs/)
  today_log_path()    — 今天的日志文件路径(按 LogPathFormat "hokworld-%Y%m%d.log")
  log_task_event(level, msg, **kv) — 写一条带时间戳的格式化日志
  task_started/restart/ok/failed/connected 等便捷函数

日志格式(参考 ok-NTE):
  2026-07-06 21:47:15,123  INFO  HOKWorld 浇水任务开始
  2026-07-06 21:48:20,456  OK    HOKWorld 浇水完成
  2026-07-06 21:49:00,789  ERROR HOKWorld connected:False 错误

关键字约定(供 AUTO-MAS ErrorLog/SuccessLog 配置):
  - 成功: 任务成功完成
  - 失败: 任务运行失败 | connected:False | 错误
"""
from __future__ import annotations

import datetime as _dt
import threading
from pathlib import Path
from typing import Any


# ---- 路径 ----
def task_log_dir() -> Path:
    """任务日志目录(随 data/ 走,发布版在 exe 同级 data/logs/)。"""
    try:
        from paths import logs_dir as _ld
        return _ld()
    except Exception:
        return Path("data") / "logs"


def today_log_path() -> Path:
    """今天的日志文件(按 LogPathFormat "hokworld-%Y%m%d.log")。

    这样 AUTO-MAS 配置 LogPathFormat=hokworld-%Y%m%d 就能每天换文件。
    """
    today = _dt.datetime.now().strftime("%Y%m%d")
    return task_log_dir() / f"hokworld-{today}.log"


# ---- 写日志 ----
_LOCK = threading.Lock()

# 日志级别(供 AUTO-MAS ErrorLog 关键字匹配)
LEVEL_INFO = "INFO"
LEVEL_OK = "OK"           # 任务成功关键字
LEVEL_WARN = "WARN"
LEVEL_ERROR = "ERROR"     # 任务失败关键字


def _format_timestamp() -> str:
    """格式:%Y-%m-%d %H:%M:%S,%f (毫秒级,与 ok-NTE 一致)。"""
    now = _dt.datetime.now()
    # 截断到毫秒(3 位),避免微秒太长
    return now.strftime("%Y-%m-%d %H:%M:%S,") + f"{now.microsecond // 1000:03d}"


def log_task_event(level: str, msg: str, **kv: Any) -> None:
    """写一条任务日志。

    Args:
        level: INFO / OK / WARN / ERROR
        msg:   消息正文
        **kv:  额外字段,以 key=value 形式追加在末尾(便于解析)

    格式示例:
        2026-07-06 21:47:15,123  INFO  浇水任务开始 mode=self
        2026-07-06 21:48:20,456  OK    浇水任务成功完成 mode=self duration=65s
        2026-07-06 21:49:00,789  ERROR connected:False 游戏连接失败
    """
    line = f"{_format_timestamp()}  {level:<5} "
    if kv:
        kvs = " ".join(f"{k}={v}" for k, v in kv.items())
        line += f"{msg} {kvs}\n"
    else:
        line += f"{msg}\n"
    try:
        with _LOCK:
            task_log_dir().mkdir(parents=True, exist_ok=True)
            with today_log_path().open("a", encoding="utf-8") as fp:
                fp.write(line)
                fp.flush()
    except Exception:
        # 日志失败不影响主流程
        pass


# ---- 便捷函数(关键关键字已硬编码,确保 AUTO-MAS 能匹配) ----
def task_started(task: str = "实时检测", **kv) -> None:
    log_task_event(LEVEL_INFO, f"{task}任务开始", **kv)


def task_restart(task: str = "实时检测", **kv) -> None:
    log_task_event(LEVEL_INFO, f"{task}强制重启", **kv)


def task_ok(task: str = "实时检测", **kv) -> None:
    """任务成功完成 — AUTO-MAS 的 SuccessLog 配 "任务成功完成" 即可。"""
    log_task_event(LEVEL_OK, f"{task}任务成功完成", **kv)


def task_failed(reason: str = "未知错误", **kv) -> None:
    """任务失败 — AUTO-MAS 的 ErrorLog 配 "任务运行失败 | connected:False | 错误" 都能匹配。"""
    # 三种关键字都打一遍,提高 AUTO-MAS 匹配命中率
    log_task_event(LEVEL_ERROR, f"任务运行失败 reason={reason}", **kv)


def task_connected(connected: bool, extra: str = "", **kv) -> None:
    """显式输出 connected:True/False(AUTO-MAS 常用关键字)。"""
    state = "True" if connected else "False"
    msg = f"connected:{state}"
    if extra:
        msg += f" {extra}"
    level = LEVEL_INFO if connected else LEVEL_ERROR
    log_task_event(level, msg, **kv)


def task_error(exc: BaseException, **kv) -> None:
    """异常输出(关键字 "错误")。"""
    log_task_event(LEVEL_ERROR, f"错误 {type(exc).__name__}: {exc}", **kv)


def task_info(msg: str, **kv) -> None:
    log_task_event(LEVEL_INFO, msg, **kv)
