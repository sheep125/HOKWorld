"""名单编辑弹窗 -- 编辑 .txt 文件(一行一个,# 注释)。白名单 / 碰撞名单共用。"""
from __future__ import annotations

from qfluentwidgets import (
    CaptionLabel, MessageBoxBase, SubtitleLabel, TextEdit,
)


class ListEditDialog(MessageBoxBase):
    """点开才出现的名单编辑弹窗(编辑一个 .txt:一行一个,# 注释)。白名单/碰撞名单共用。"""

    def __init__(self, file, title, tip, placeholder, parent=None) -> None:
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        cap = CaptionLabel(tip, self)
        cap.setWordWrap(True)
        self.edit = TextEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFixedSize(460, 300)
        try:
            self.edit.setPlainText(file.read_text(encoding="utf-8"))
        except Exception:
            pass
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(cap)
        self.viewLayout.addWidget(self.edit)
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(520)

    def text(self) -> str:
        return self.edit.toPlainText()
