"""用户配置:JSON 存于 %LOCALAPPDATA%\\HOKWorldScript\\config.json(覆盖更新 / 换机更新都保留)。

目前仅「时序抖动」。不再有「演练 / 真实输入」总开关——它们会**静默关掉游戏操作**(识别到却不按),
易被误当作脚本失灵;现在脚本一律真实操作。采集黑/白名单同样存用户目录,更新不丢。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from paths import config_path

DEFAULTS = {
    "timing_jitter": False,          # 时序/位移随机抖动(默认关闭)
    "game_path": "",                 # 《王者荣耀世界》启动器 exe 路径;留空=自动定位(注册表/开始菜单);自动找不到时手填
    # 全局行为
    "auto_start_realtime": False,    # HOKWorld 启动后是否自动开始实时检测
    "auto_exit_app": False,          # 游戏退出时是否自动退出 HOKWorld
    "auto_water_after_game": False,  # 游戏启动后自动浇水(浇水完再开始实时检测)
    "auto_water_mode": "self",       # 自动浇水模式: self=自己农场 / friends=好友农场
    "auto_water_exit": False,        # (已废弃,仅向后兼容)联动浇水完成后退出游戏和HOKWorld
    "auto_water_exit_mode": "none",  # 联动浇水完成后退出方式: none=不退出 / game_only=仅退出游戏 / all=退出游戏和HOKWorld
    "minimize_after_game_start": False,  # 游戏启动后最小化HOKWorld窗口
    # 实时触发
    "auto_login": False,             # 游戏启动后自动登录(点击登录/进入游戏按钮)
    # 月卡
    "monthly_card_check": False,     # 是否检查并关闭月卡弹窗
    "monthly_card_hour": 0,          # 月卡弹窗预期小时(默认 0=北京时间0点)
    "monthly_card_window_mins": 30,  # 在该时间前后多少分钟内检查月卡
    # 退出时杀游戏进程的路径
    "game_exe_name": "NGR-Win64-Shipping.exe",  # 游戏进程名(用于 taskkill),因人而异可自行修改
    # 定时调度
    "schedule_enabled": False,        # 定时调度总开关
    "schedule_entries": None,         # 条目 list;None 时由 scheduler 自动填默认 3 格
}


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else config_path()
        self._d = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            return
        if isinstance(raw, dict):
            for k in DEFAULTS:
                if k in raw:
                    self._d[k] = raw[k]

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, key: str):
        return self._d.get(key, DEFAULTS.get(key))

    def set(self, key: str, value, save: bool = True) -> None:
        self._d[key] = value
        if save:
            self.save()

    def timing_jitter(self) -> bool:
        return bool(self._d.get("timing_jitter"))

    def water_exit_mode(self) -> str:
        """解析联动浇水完成后的退出方式(统一入口,三处调用点共用)。

        优先级规则(修复 AUTO-MAS 启动后脚本被关闭的 bug):
          1. 新字段 auto_water_exit_mode 显式设为非 "none" → 直接用新字段
             (用户明确选择了 game_only/all,不应被旧字段覆盖)
          2. 新字段为 "none" 或缺失 → 才回退到旧字段 auto_water_exit:
             - auto_water_exit=True  → "all"(旧行为,向后兼容)
             - auto_water_exit=False → "none"

        返回值: "none" / "game_only" / "all"
        """
        new_mode = str(self._d.get("auto_water_exit_mode") or "none").strip().lower()
        if new_mode not in ("none", "game_only", "all"):
            new_mode = "none"
        if new_mode != "none":
            return new_mode
        # 新字段没明确意图 → 才考虑旧字段(向后兼容)
        if bool(self._d.get("auto_water_exit")):
            return "all"
        return "none"


# 进程内单例:UI 改设置后 save();各任务线程启动时读取一次。
cfg = Config()
