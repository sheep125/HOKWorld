"""可滚动页面基类 -- 子类把控件加到 self.vbox(置于垂直滚动视图中)。

- 内容未超出视口 → 不显示滚动条,滚轮也不滚
- 内容超出可视范围 → 自动出现细滚动条,悬停/按住拖动时滚动条变粗
- 窗口放大到能容纳 → 滚动条自动隐藏
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import SingleDirectionScrollArea


class ScrollInterface(QWidget):
    """可滚动页面基类:子类把控件加到 self.vbox(置于垂直滚动视图中)。"""

    def __init__(self, object_name: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = SingleDirectionScrollArea(self, orient=Qt.Vertical)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.enableTransparentBackground()
        self.view = QWidget(self.scroll)
        self.view.setObjectName("scrollView")
        self.view.setStyleSheet("#scrollView{background:transparent;}")
        self.scroll.setWidget(self.view)
        outer.addWidget(self.scroll)
        self.vbox = QVBoxLayout(self.view)
