"""
DelugeHub — Module Placeholder Base
All non-Dashboard modules use this until fully implemented.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt


class PlaceholderModule(QWidget):
    def __init__(self, icon: str, title: str, subtitle: str, color: str = "#1E6FBB"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        # Page header
        header_title = QLabel(f"{icon}  {title}")
        header_title.setObjectName("PageTitle")
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("PageSubtitle")
        layout.addWidget(header_title)
        layout.addWidget(subtitle_lbl)
        layout.addSpacing(28)

        # Coming soon card
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 60, 40, 60)
        card_layout.setSpacing(16)
        card_layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 56px;")

        msg_lbl = QLabel(f"{title} wird in einer späteren Version implementiert.\nDieses Modul ist bereits im Roadmap geplant.")
        msg_lbl.setAlignment(Qt.AlignCenter)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: #888888; font-size: 14px;")

        version_lbl = QLabel("🗺  Roadmap: v0.2 – v0.4")
        version_lbl.setAlignment(Qt.AlignCenter)
        version_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")

        card_layout.addWidget(icon_lbl)
        card_layout.addWidget(msg_lbl)
        card_layout.addWidget(version_lbl)

        layout.addWidget(card)
        layout.addStretch()
