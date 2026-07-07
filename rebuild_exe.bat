@echo off
REM 不切 chcp —— 文件本身用 GBK 保存,与 Windows cmd 默认代码页(936)匹配
setlocal enabledelayedexpansion

set DEV_DIR=%~dp0
set RELEASE_DIR=C:\GameSc\HOKWorldScript
set DIST=%DEV_DIR%dist\HOKWorld

echo.
echo  ============================================
echo   HOKWorld 一键发布: 研发 -^> exe
echo  ============================================
echo.
echo   研发目录: %DEV_DIR%
echo   发布目录: %RELEASE_DIR%
echo.

REM -- 1. 确认 PyInstaller --
echo [1/4] 检查 PyInstaller...
call "%DEV_DIR%.venv\Scripts\python.exe" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo       未安装,正在安装 PyInstaller...
    call "%DEV_DIR%.venv\Scripts\pip.exe" install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败!
        pause
        exit /b 1
    )
) else (
    echo       PyInstaller 已就绪
)

REM -- 2. 打包前自检 --
echo [2/4] 语法自检...
call "%DEV_DIR%.venv\Scripts\python.exe" -c "import py_compile;[py_compile.compile(f, doraise=True) for f in ['app.py','config.py','scheduler.py','task_log.py','runtime_guard.py','paths.py','version.py','winenv.py','ui/realtime.py','ui/settings.py','ui/schedule_card.py','workers/water_worker.py','workers/launch_worker.py','workers/monthly_card_worker.py','water/self_farm.py','water/recognizer.py','monthly_card.py']]" 2^>^&1
if errorlevel 1 (
    echo [错误] 自检失败,有语法错误,已中止打包
    pause
    exit /b 1
)
echo       自检通过

REM -- 3. 构建 exe --
echo [3/4] 构建 exe(约 30-90 秒)...
rmdir /s /q "%DEV_DIR%dist" 2>nul
rmdir /s /q "%DEV_DIR%build" 2>nul

call "%DEV_DIR%.venv\Scripts\python.exe" -m PyInstaller ^
    --onedir ^
    --name HOKWorld ^
    --noconsole ^
    --clean ^
    --add-data "assets;assets" ^
    --collect-all qfluentwidgets ^
    --collect-all rapidocr_onnxruntime ^
    --collect-all onnxruntime ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtWebEngineQuick ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQuickWidgets ^
    --exclude-module PySide6.QtQuick3D ^
    --exclude-module PySide6.QtQuickControls2 ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.QtMultimediaWidgets ^
    --exclude-module PySide6.QtDesigner ^
    --exclude-module PySide6.QtHelp ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.Qt3DRender ^
    --exclude-module PySide6.QtDataVisualization ^
    --exclude-module PySide6.QtLocation ^
    --exclude-module PySide6.QtPositioning ^
    --exclude-module PySide6.QtSensors ^
    --exclude-module PySide6.QtSerialPort ^
    --exclude-module PySide6.QtSql ^
    --exclude-module PySide6.QtTest ^
    --exclude-module PySide6.QtPrintSupport ^
    --exclude-module PySide6.QtBluetooth ^
    --exclude-module PySide6.QtNetworkAuth ^
    --exclude-module PySide6.QtWebChannel ^
    --exclude-module PySide6.QtWebSockets ^
    --exclude-module tkinter ^
    --exclude-module curses ^
    --exclude-module pytest ^
    --distpath "%DEV_DIR%dist" ^
    "%DEV_DIR%app.py"

if not exist "%DIST%\HOKWorld.exe" (
    echo.
    echo [错误] 构建失败!请把上方 PyInstaller 的错误信息反馈给开发者
    pause
    exit /b 1
)
echo       构建完成

REM -- 4. 备份旧版 + 部署 --
echo [4/4] 备份并部署...
if exist "%RELEASE_DIR%\HOKWorld.exe" (
    set BACKUP=%RELEASE_DIR%.bak_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    set BACKUP=!BACKUP: =0!
    mkdir "!BACKUP!" 2>nul
    xcopy "%RELEASE_DIR%" "!BACKUP!" /E /I /Q /Y >nul 2>&1
    echo       旧版备份到 !BACKUP!

    REM 只保留最近 2 份备份
    set CLEANED=0
    for /f "skip=2 tokens=*" %%B in ('dir /b /a:d /o-n "%RELEASE_DIR%.bak_*" 2^>nul') do (
        set /a CLEANED+=1
        rmdir /s /q "%RELEASE_DIR%.bak_%%B" 2>nul
    )
    if !CLEANED! gtr 0 (
        echo       已清理 !CLEANED! 份旧备份,仅保留最近 2 份
    )
)

REM 关掉可能正在运行的 exe
taskkill /f /im HOKWorld.exe >nul 2>&1

REM 删除旧的 _internal(保留 data/ 和卸载程序)
for %%f in ("%RELEASE_DIR%\HOKWorld.exe" "%RELEASE_DIR%\HOKWorld.exe.bak") do (
    if exist %%f del /q %%f >nul 2>&1
)
if exist "%RELEASE_DIR%\_internal" rmdir /s /q "%RELEASE_DIR%\_internal"
if exist "%RELEASE_DIR%\assets" rmdir /s /q "%RELEASE_DIR%\assets"

REM 复制新版本
xcopy "%DIST%\_internal" "%RELEASE_DIR%\_internal" /E /I /Q /Y >nul
copy /y "%DIST%\HOKWorld.exe" "%RELEASE_DIR%\HOKWorld.exe" >nul

echo.
echo  ============================================
echo   发布完成!
echo   双击运行: %RELEASE_DIR%\HOKWorld.exe
echo  ============================================
echo.
echo   data/ 目录未覆盖(研发与发布共享配置)
echo   日志位置: %RELEASE_DIR%\data\logs\hokworld-YYYYMMDD.log
echo   配置位置: %RELEASE_DIR%\data\config.json
echo.
pause
endlocal
