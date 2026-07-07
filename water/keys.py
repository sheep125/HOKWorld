"""浇水模块 — 键位配置。所有键位从 config.json 读取,未配置则使用默认值。

默认键位参考常见 PC 游戏布局(菜单=ESC, 交互=F, 确认=Enter, 前进=W)。
在实际游戏中对照确认后填入 config.json 的 "water_keys" 段即可。
"""
from __future__ import annotations

# 虚拟键码(VK)默认映射 —— 对照游戏实际键位修改
# 参考: https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
DEFAULT_WATER_KEYS: dict[str, int] = {
    # 菜单
    "menu":         0x1B,   # ESC — 打开/关闭菜单
    # 居所页 Tab 切换
    "tab_next":     0x45,   # E   — 下一个 Tab(居所: 管理)
    "tab_prev":     0x51,   # Q   — 上一个 Tab(居所: 总览)
    # 移动
    "forward":      0x57,   # W   — 向前移动
    # 铲除(杂草时右下角图标)
    "remove_weed":  0x51,   # Q   — 铲除
    # 列表滚动(好友浇水用)
    "scroll_down":  0x28,   # Down Arrow
    "scroll_up":    0x26,   # Up Arrow
    # 保留旧字段兼容,但自农场浇水已不用这些
    "interact":     0x46,   # F
    "confirm":      0x0D,   # Enter
    "cancel":       0x1B,   # ESC
    "water":        0x46,   # F
}


def load_water_keys() -> dict[str, int]:
    """从 config.json 读取 water_keys,缺失项用默认值。

    config.json 中格式:
      {
        "water_keys": {
          "menu": 27,
          "interact": 70,
          ...
        }
      }
    """
    try:
        from config import cfg
        user = cfg.get("water_keys") or {}
    except Exception:
        user = {}
    if not isinstance(user, dict):
        user = {}
    merged = dict(DEFAULT_WATER_KEYS)
    for k, v in user.items():
        if k in merged and isinstance(v, int):
            merged[k] = v
    return merged
