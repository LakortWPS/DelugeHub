"""
DelugeHub — Dashboard Module
SD-Card health overview, statistics, quick actions.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from typing import Optional

from ..core.models import SDCardIndex


class _ClickableCard(QFrame):
    """A QFrame card that emits a clicked() signal on mouse press."""
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _card(object_name="Card") -> QFrame:
    f = QFrame()
    f.setObjectName(object_name)
    f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return f


def _stat_card(value: str, label: str, value_id="StatNumber",
               card_id="Card", on_click=None) -> QFrame:
    """
    Create a stat card.  If *on_click* is provided the card becomes a
    _ClickableCard (CardHover styling + pointing cursor).
    """
    if on_click is not None:
        card = _ClickableCard()
        card.setObjectName("CardHover")
        card.setCursor(Qt.PointingHandCursor)
        card.clicked.connect(on_click)
    else:
        card = _card(card_id)

    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(4)

    val_lbl = QLabel(value)
    val_lbl.setObjectName(value_id)
    val_lbl.setAlignment(Qt.AlignCenter)

    lbl = QLabel(label.upper())
    lbl.setObjectName("StatLabel")
    lbl.setAlignment(Qt.AlignCenter)

    layout.addWidget(val_lbl)
    layout.addWidget(lbl)
    return card


class DashboardModule(QWidget):
    request_scan = Signal()
    navigate_to = Signal(str)   # module name

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        # --- Header ---
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")

        subtitle = QLabel("SD-Card Übersicht und Health-Status")
        subtitle.setObjectName("PageSubtitle")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        scan_btn = QPushButton("⟳  SD-Card scannen")
        scan_btn.setToolTip("SD-Card neu einlesen")
        scan_btn.clicked.connect(self.request_scan)
        scan_btn.setFixedHeight(38)
        header.addWidget(scan_btn)

        root.addLayout(header)
        root.addSpacing(24)

        # --- Scrollable content ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(20)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(content)
        root.addWidget(scroll)

        self._render_empty()

    def _clear_content(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_empty(self):
        self._clear_content()

        card = _card("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignCenter)

        icon = QLabel("💾")
        icon.setAlignment(Qt.AlignCenter)
        icon.setObjectName("StatNumber")   # large bold styling from theme

        msg = QLabel("Keine SD-Card geladen.\nBitte wähle einen SD-Card Pfad und klicke 'Scannen'.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setObjectName("PageSubtitle")
        msg.setWordWrap(True)

        btn = QPushButton("SD-Card auswählen & scannen")
        btn.setFixedWidth(280)
        btn.clicked.connect(self.request_scan)

        lay.addWidget(icon)
        lay.addWidget(msg)
        lay.addSpacing(12)
        lay.addWidget(btn, alignment=Qt.AlignCenter)

        self._content_layout.addWidget(card)
        self._content_layout.addStretch()

    def update_index(self, index: SDCardIndex):
        self._index = index
        self._render_dashboard(index)

    def _render_dashboard(self, idx: SDCardIndex):
        self._clear_content()

        missing = idx.total_missing_refs
        unused = len(idx.unused_samples)

        # --- Section: Stats grid ---
        section_label = QLabel("ÜBERSICHT")
        section_label.setObjectName("SectionTitle")
        self._content_layout.addWidget(section_label)

        grid = QGridLayout()
        grid.setSpacing(12)

        cards = [
            _stat_card(str(len(idx.songs)),   "Songs",   "StatNumber",
                       on_click=lambda: self.navigate_to.emit("song_manager")),
            _stat_card(str(len(idx.kits)),    "Kits",    "StatNumber",
                       on_click=lambda: self.navigate_to.emit("kit_manager")),
            _stat_card(str(len(idx.synths)),  "Synths",  "StatNumber",
                       on_click=lambda: self.navigate_to.emit("synth_editor")),
            _stat_card(str(len(idx.samples)), "Samples", "StatNumber",
                       on_click=lambda: self.navigate_to.emit("sample_manager")),
        ]
        for i, c in enumerate(cards):
            grid.addWidget(c, 0, i)

        grid.addWidget(
            _stat_card(
                str(missing),
                "Fehlende Referenzen",
                "StatNumberError" if missing > 0 else "StatNumberSuccess",
                "CardError" if missing > 0 else "CardSuccess"
            ), 1, 0, 1, 2
        )
        grid.addWidget(
            _stat_card(
                f"{idx.total_sample_size_mb:.0f} MB",
                "Sample-Größe",
                "StatNumber",
                "Card"
            ), 1, 2
        )
        grid.addWidget(
            _stat_card(
                str(unused),
                "Ungenutzte Samples",
                "StatNumberWarn" if unused > 0 else "StatNumber",
                "CardWarning" if unused > 0 else "Card"
            ), 1, 3
        )

        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        self._content_layout.addWidget(grid_widget)

        # --- Section: Quick Actions ---
        qa_label = QLabel("QUICK ACTIONS")
        qa_label.setObjectName("SectionTitle")
        self._content_layout.addWidget(qa_label)

        qa_card = _card("Card")
        qa_layout = QHBoxLayout(qa_card)
        qa_layout.setContentsMargins(16, 16, 16, 16)
        qa_layout.setSpacing(12)

        def nav_btn(icon, text, module, style=""):
            btn = QPushButton(f"{icon}  {text}")
            btn.setFixedHeight(42)
            if style:
                btn.setObjectName(style)
            btn.clicked.connect(lambda: self.navigate_to.emit(module))
            return btn

        if missing > 0:
            fix_btn = nav_btn("🔍", f"{missing} Fehlende Samples reparieren", "lost_sample_finder", "DangerButton")
            qa_layout.addWidget(fix_btn)

        qa_layout.addWidget(nav_btn("📁", "Sample Manager", "sample_manager"))
        qa_layout.addWidget(nav_btn("🎹", "Synth Editor", "synth_editor"))
        qa_layout.addWidget(nav_btn("💾", "Backup erstellen", "backup_sync", "SuccessButton"))
        qa_layout.addStretch()

        self._content_layout.addWidget(qa_card)

        # --- Section: Errors / Warnings ---
        if idx.scan_errors:
            err_label = QLabel("SCAN-WARNUNGEN")
            err_label.setObjectName("SectionTitle")
            self._content_layout.addWidget(err_label)

            err_card = _card("CardWarning")
            err_layout = QVBoxLayout(err_card)
            err_layout.setContentsMargins(16, 12, 16, 12)
            err_layout.setSpacing(4)

            for e in idx.scan_errors[:10]:
                lbl = QLabel(f"⚠  {e}")
                lbl.setObjectName("WarningLabel")
                lbl.setWordWrap(True)
                err_layout.addWidget(lbl)

            if len(idx.scan_errors) > 10:
                more = QLabel(f"… und {len(idx.scan_errors) - 10} weitere Fehler.")
                more.setObjectName("WarningLabel")
                err_layout.addWidget(more)

            self._content_layout.addWidget(err_card)

        # --- SD-Card Info ---
        info_label = QLabel("SD-CARD INFO")
        info_label.setObjectName("SectionTitle")
        self._content_layout.addWidget(info_label)

        info_card = _card("Card")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(6)

        def info_row(label, value):
            row = QHBoxLayout()
            l = QLabel(label)
            l.setObjectName("PageSubtitle")
            v = QLabel(str(value))
            v.setObjectName("SDPathValue")
            row.addWidget(l)
            row.addStretch()
            row.addWidget(v)
            return row

        info_layout.addLayout(info_row("Pfad:", str(idx.root_path)))
        info_layout.addLayout(info_row("Songs:", len(idx.songs)))
        info_layout.addLayout(info_row("Kits:", len(idx.kits)))
        info_layout.addLayout(info_row("Synths:", len(idx.synths)))
        info_layout.addLayout(info_row("Samples:", len(idx.samples)))
        info_layout.addLayout(info_row("Fehlende Referenzen:", missing))
        info_layout.addLayout(info_row("Scan-Fehler:", len(idx.scan_errors)))

        self._content_layout.addWidget(info_card)
        self._content_layout.addStretch()
