r"""dev_launcher.py -- 研发环境启动器。

研发-发布绑定说明:
  - data/ 目录: 已通过 Junction 指向发布版 data/
    -> 研发和发布版共享同一份 config.json、日志、采集名单
  - 运行时: 使用研发 .venv 中的 Python 3.12 + 依赖
  - 源码: 研发目录中的最新 .py 文件
  - 发布: 修改代码后用 PyInstaller 打包即更新 HOKWorld.exe

用法:
    .venv\Scripts\python.exe dev_launcher.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 研发源码优先
sys.path.insert(0, str(HERE))

# 开启开发模式(调试帧/截图写入 data/)
os.environ["HOKWORLD_DEV"] = "1"

from app import main
raise SystemExit(main())
