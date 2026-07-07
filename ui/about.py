"""关于页面。"""
from __future__ import annotations

from qfluentwidgets import BodyLabel, CaptionLabel, HyperlinkButton, TitleLabel

from ui.scroll_interface import ScrollInterface
from version import APP_DISPLAY, GITHUB_OWNER, GITHUB_REPO, __version__

APP_VERSION = f"v{__version__}"


class AboutInterface(ScrollInterface):
    def __init__(self) -> None:
        super().__init__("aboutInterface")
        lo = self.vbox
        lo.setContentsMargins(28, 22, 28, 22)
        lo.addWidget(TitleLabel("关于"))
        lo.addWidget(BodyLabel(f"{APP_DISPLAY}  ·  {APP_VERSION}"))
        lo.addWidget(BodyLabel("HOKWorld — 《王者荣耀世界》黑盒视觉自动化"))
        lo.addWidget(CaptionLabel("仅黑盒视觉 + 标准键鼠;不读内存/不注入/不改封包。"))
        lo.addWidget(CaptionLabel("配置 / 日志 / 采集名单存在程序目录下的 data\\(随程序、不进 Windows 用户目录)。"))
        lo.addWidget(HyperlinkButton(
            f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}", "项目主页 / 反馈问题"))
        lo.addStretch(1)
