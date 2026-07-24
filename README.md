# HOKWorld — 《王者荣耀世界》黑盒视觉自动化

靠屏幕画面识别 + 标准键鼠模拟实现自动化，纯视觉方案（不读写内存、不注入、不改封包、不碰游戏文件）。仅供学习研究，使用风险自负，请遵守游戏用户协议。

## 功能一览

| 功能 | 说明 |
|------|------|
| **自动钓鱼** | 抛竿 → 上钩 → 拉杆 → 收线 → 结算，大鱼 QTE（A/D 连点 + 离散按钮），记录鱼按 F 收背包 |
| **剧情跳过** | 实时读屏，识别剧情画面自动跳过/推进，回到游戏立刻收手 |
| **跑图自动采集** | 经过材料/宝箱弹「F + 名称」提示就按 F，按图标区分别采 |
| **自动启动游戏** | 定位启动器 exe → 拉起 → 过公告 → 点开始游戏，全自动 |
| **自农场浇水** | 进居所 → 传送农田 → 自动浇水，支持多块田轮浇 |
| **月卡检测** | 游戏启动后常驻并行检测，OCR 识别月卡/奖励弹窗并点击关闭 |
| **定时调度** | AUTO-MAS 集成，指定时间自动启动游戏 + 跑完一整套流程 |

> 运行中 **F12** 全局急停。

## 下载使用

到 [Releases](https://github.com/sheep125/HOKWorld/releases) 下载最新版（当前 `v0.4.2`），解压后双击 `HOKWorld.exe` 即可。

- 需以**管理员身份**运行（游戏是提权进程，发键鼠得用管理员权限）
- 游戏以窗口或无边框窗口运行，保持前台不被遮挡（全靠截屏认画面）
- Windows 10 / 11（x64）

## 从源码运行

```bash
git clone https://github.com/sheep125/HOKWorld.git
cd HOKWorld
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

启动时会弹 UAC 提权，点「是」。

## 配置与名单

配置、日志、采集黑/白名单都存在程序目录下的 `data\`：

| 文件 | 用途 |
|------|------|
| `config.json` | 所有开关与设置（钓鱼次数、月卡检测、自动浇水、定时调度等） |
| `blacklist.txt` | 采集碰撞名单（手型图标但不该采的交互） |
| `whitelist.txt` | 采集白名单（强制采的名字） |
| `logs\` | 运行日志 |

`data\` 不随版本更新覆盖，升级后你的设置和名单都保留。卸载时才会清掉。

## 自动钓鱼

站在钓鱼点位上，确认处于钓鱼状态且落点为蓝色，设置循环次数后点「开始」：

- 完整流程：抛竿 → 等上钩 → 拉杆 → 收线 → 结算 → 续钓
- 大鱼触发 QTE：快速连点 A/D，以及离散按钮 A/S/W/D
- 认出「个人记录」界面就按 F 收进背包
- 到等级上限或连续空抛太多次会自动停机
- 结束打印简短统计

<img width="2661" height="1615" alt="钓鱼界面" src="https://github.com/user-attachments/assets/0066e26a-b099-4a0b-8770-2e051ff32af9" />

## 剧情跳过（实时检测）

左侧「实时检测」点「开始」后实时读屏：

- **可跳过剧情**：ESC 调出确认框，平滑移动光标点「跳过」
- **对话推进 / 空白处继续 / 黑屏过场**：原地点击
- **居中交互框（宝箱等）或已在游戏世界（右下 HUD 在）**：不动

<img width="2655" height="1620" alt="剧情跳过" src="https://github.com/user-attachments/assets/855cd9d5-e4c9-441e-97bb-0d663205aad9" />

## 跑图自动采集

「实时检测」里的「经过材料自动采集（F）」默认开启，和剧情跳过一起跑：

- **按图标分类**：F 键帽确认有提示 → 看键帽右侧图标——手型（采集）/ 重现图标就采，NPC / 商店 / 制作 / 对话 / 组队等不动
- **只读一次名字**：提示刚出现那一帧读一次，同一提示不重复读（跟手）
- **黑名单（碰撞名单）**：图标是采集手型却不该采的（渡石、语印、捕获、启动滑索、松开滑索、启动冲云翼等）已内置，遇到自动跳过；误采了到「设置 · 采集碰撞名单」加一行
- **白名单（强制采）**：写进去的名字识别到一定采（优先级最高，能盖过黑名单）
- 内置名单随版本更新自动生效；你增删的存程序 `data\`，更新不丢

## 目录结构

```
app.py                Fluent 控制台（PySide6 + qfluentwidgets，含安全设置页、自动提权）
version.py            版本与应用信息
paths.py              资源 / 本机数据路径（数据在程序目录下的 data\）
config.py             配置（时序抖动；名单与配置都存程序目录 data\）
winenv.py             Windows 与游戏窗口工具（提权 / 隐藏控制台 / DPI / 窗口枚举）
applog.py             统一日志（logs\hokworld.log）
runtime_guard.py      运行保护（日志 / 原子写入 / 安全键鼠 / 任务互斥）
capture.py            无黄框无闪烁屏幕捕获（GDI BitBlt）+ 后台截图（PrintWindow）
ocr_utils.py          OCR 与图像 ROI 公共工具（norm1920 / crop / ocr_text 等）
launcher.py           自动启动游戏（exe 定位 → 拉起 → 过公告 → 点开始游戏）
monthly_card.py       月卡 / 奖励弹窗常驻 OCR 检测与关闭
scheduler.py          定时调度（AUTO-MAS 集成）
task_log.py           任务日志
rebuild_exe.bat       PyInstaller 一键打包脚本
requirements.txt      依赖
assets/               界面 / 应用图标
fishing/              钓鱼模块（识别 + 状态机 + 模板库）
  matcher.py            钓鱼识别（模板 + 字形 IoU + HoughCircles + OCR）
  fisher.py             钓鱼状态机（发真实键鼠）
  template_bank.py      命名模板 + 逐特征预处理
  templates/raw/*       识别模板（从真实客户端帧裁切，必需，勿删）
story/                剧情模块
  recognizer.py         剧情识别（OCR 控制条 + HUD 边缘密度 + 黑屏比例）
  skipper.py            剧情跳过状态机
gather/               采集模块
  recognizer.py         采集识别（F 键帽 + 图标分类 + 文字查名单）
  picker.py             采集引擎（边沿触发按 F）
  blacklist.txt         黑名单模板（首次运行复制到 data\）
  whitelist.txt         白名单模板
water/                浇水模块
  recognizer.py         浇水视觉识别（居所/农田/浇水按钮 OCR）
  self_farm.py          自农场浇水状态机
  login_bot.py          自动登录
  waterer.py            好友浇水
  keys.py               按键映射
ui/                   界面（实时检测 / 设置 / 定时调度 / 钓鱼 / 浇水等页面）
workers/              后台线程（base / launch / water / monthly_card / fish / gather / story）
```

## 几点提醒

- 模板从 1920 宽的真实客户端帧裁切，运行时每帧先归一化到 1920 宽再匹配。分辨率、画质、HUD 差太多时阈值可能要重标定（改 `fishing/matcher.py` 里的阈值和 ROI）。适用于 1080p / 1440p / 2160p 等 16:9 显示器。
- 只在游戏前台时动作，切走会自动暂停。
- 截图用 GDI BitBlt（SRCCOPY，无 CAPTUREBLT），无黄框、无光标闪烁。
