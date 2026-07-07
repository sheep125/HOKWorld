"""WaterWorker — 自动浇水任务线程(支持自农场/好友农场)。"""
from __future__ import annotations
import time as _time
from workers.base import BaseBotWorker


class WaterWorker(BaseBotWorker):

    def __init__(self, mode: str = "friends", exit_after: bool = False) -> None:
        super().__init__()
        self._mode = mode
        # exit_after 兼容老接口:True → "all",False → 读 config 的 auto_water_exit_mode
        if exit_after:
            self._exit_mode = "all"
        else:
            try:
                from config import cfg
                # 向后兼容:旧的 auto_water_exit=True 优先(已开的用户不丢功能)
                legacy = bool(cfg.get("auto_water_exit"))
                self._exit_mode = "all" if legacy else str(cfg.get("auto_water_exit_mode") or "none")
            except Exception:
                self._exit_mode = "none"

    def run(self) -> None:
        import importlib, winenv, water.keys, water.recognizer, water.waterer, water.self_farm
        for m in (winenv, water.keys, water.recognizer, water.waterer, water.self_farm):
            try: importlib.reload(m)
            except Exception: pass

        if self._mode == "self":
            self._run_self_farm()
        else:
            self._run_friends()

    def _run_self_farm(self) -> None:
        from task_log import task_started, task_ok, task_failed, task_error, task_connected
        t0 = _time.time()
        task_started("浇水", mode="self", source="居所封面")
        task_connected(True, "游戏连接检查")
        self.sig_log.emit("[浇水] 自农场(居所封面)")
        from water.self_farm import SelfFarmWaterBot
        self.bot = SelfFarmWaterBot(log=self.sig_log.emit)
        try:
            ok = self.bot.run()
            dur = int(_time.time() - t0)
            self.sig_log.emit(f"[浇水] {'完成' if ok else '未完成'}")
            if ok:
                task_ok("浇水", mode="self", duration=f"{dur}s")
                if self._exit_mode in ("game_only", "all"):
                    self._exit_game_and_app(exit_app=self._exit_mode == "all")
            else:
                task_failed("浇水未完成", mode="self", duration=f"{dur}s")
        except Exception as exc:
            self._log_error(exc)
            task_error(exc, stage="self_farm_run")
            task_connected(False, f"异常 {type(exc).__name__}")
            task_failed(repr(exc), mode="self")
        self.sig_done.emit()

    def _run_friends(self) -> None:
        from task_log import task_started, task_ok, task_failed, task_error, task_connected
        t0 = _time.time()
        friends = self._cfg_list("water_friends")
        if not friends:
            self.sig_log.emit("[浇水] 好友模式未配置名单,请在 data/config.json 的 water_friends 段添加好友名")
            task_failed("好友名单未配置", mode="friends")
            self.sig_done.emit()
            return
        fields = self._cfg_int("water_fields_per_friend", 3)
        task_started("浇水", mode="friends", friends=len(friends), fields_per_friend=fields)
        task_connected(True, "游戏连接检查")
        self.sig_log.emit(f"[浇水] 好友模式,好友数 {len(friends)},每好友 {fields} 块田")
        from water.waterer import WaterBot
        self.bot = WaterBot(log=self.sig_log.emit, friends=friends, fields_per_friend=fields)
        try:
            ok = self.bot.run()
            dur = int(_time.time() - t0)
            self.sig_log.emit(f"[浇水] {'完成' if ok else '未完成'}")
            if ok:
                task_ok("浇水", mode="friends", duration=f"{dur}s")
                if self._exit_mode in ("game_only", "all"):
                    self._exit_game_and_app(exit_app=self._exit_mode == "all")
            else:
                task_failed("浇水未完成", mode="friends", duration=f"{dur}s")
        except Exception as exc:
            self._log_error(exc)
            task_error(exc, stage="friends_run")
            task_connected(False, f"异常 {type(exc).__name__}")
            task_failed(repr(exc), mode="friends")
        self.sig_done.emit()

    def _exit_game_and_app(self, exit_app: bool = True) -> None:
        """退出游戏进程;exit_app=True 时连 HOKWorld 一起退出。

        exit_app=False(仅退出游戏)用于用户希望浇水后 HOKWorld 继续运行的场景:
        不杀自己进程,只 taskkill 游戏;HOKWorld 保留在桌面/任务栏供下次手动操作。
        """
        import os, subprocess, time
        from config import cfg
        from task_log import task_info
        action = "退出游戏和 App" if exit_app else "仅退出游戏"
        task_info(f"任务完成,{action}")
        self.sig_log.emit(f"[浇水] 任务完成,{action}")
        # 1. 杀游戏进程(从 config.json 读取进程名)
        game_exe = cfg.get("game_exe_name") or "NGR-Win64-Shipping.exe"
        # 也尝试启动器进程
        for name in (str(game_exe), "KingLauncher.exe", "王者荣耀世界.exe"):
            try: subprocess.run(["taskkill","/f","/im",name], check=False, capture_output=True)
            except Exception: pass
        if not exit_app:
            # 仅退出游戏 → 不动自己,直接返回,Worker 正常走完 sig_done 流程
            self.sig_log.emit("[浇水] 游戏已退出,HOKWorld 保持运行")
            return
        time.sleep(3.0)
        # 2. 退出 HOKWorld
        task_info("正在退出 HOKWorld")
        self.sig_log.emit("[浇水] 正在退出 HOKWorld")
        os._exit(0)

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            from config import cfg; v = cfg.get(key)
            return int(v) if isinstance(v, int) and v > 0 else default
        except Exception: return default

    def _cfg_list(self, key: str) -> list[str]:
        try:
            from config import cfg; v = cfg.get(key)
            if isinstance(v, list): return [str(x).strip() for x in v if str(x).strip()]
        except Exception: pass
        return []
