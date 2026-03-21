"""
DelugeHub — Theme System
Dark and Light QSS stylesheets.
"""

DARK = """
/* === Global === */
QWidget {
    background-color: #1A1A2E;
    color: #E0E0E0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #1A1A2E; }

/* === Sidebar === */
#Sidebar {
    background-color: #16213E;
    border-right: 1px solid #0F3460;
    min-width: 220px;
    max-width: 220px;
}
#SidebarCollapsed {
    background-color: #16213E;
    border-right: 1px solid #0F3460;
    min-width: 52px;
    max-width: 52px;
}
#AppTitle { color: #1E6FBB; font-size: 18px; font-weight: bold; padding: 20px 16px 8px 16px; }
#AppSubtitle { color: #888888; font-size: 10px; padding: 0px 16px 20px 16px; }

/* === Nav Buttons === */
QPushButton#NavButton {
    background-color: transparent; color: #AAAAAA;
    border: none; border-radius: 8px; padding: 10px 16px;
    text-align: left; font-size: 13px;
}
QPushButton#NavButton:hover { background-color: #0F3460; color: #E0E0E0; }
QPushButton#NavButton[active="true"] { background-color: #1E6FBB; color: #FFFFFF; font-weight: bold; }

/* Collapsed sidebar: icon-only nav button */
QPushButton#NavButtonCollapsed {
    background-color: transparent; color: #AAAAAA;
    border: none; border-radius: 8px;
    padding: 10px 0px; text-align: center;
    font-size: 16px; min-width: 36px; max-width: 36px;
}
QPushButton#NavButtonCollapsed:hover { background-color: #0F3460; color: #E0E0E0; }
QPushButton#NavButtonCollapsed[active="true"] { background-color: #1E6FBB; color: #FFFFFF; }

/* Sidebar collapse toggle */
QPushButton#CollapseButton {
    background-color: transparent; color: #555577;
    border: none; border-radius: 4px; padding: 4px; font-size: 14px;
}
QPushButton#CollapseButton:hover { background-color: #0F3460; color: #AAAAAA; }

/* === Top Bar === */
#TopBar {
    background-color: #16213E;
    border-bottom: 1px solid #0F3460;
    min-height: 52px; max-height: 52px;
}
#SDPathLabel { color: #888888; font-size: 12px; padding: 0 8px; }
#SDPathValue { color: #E0E0E0; font-size: 12px; font-weight: bold; }

/* === Status Bar === */
#StatusBar {
    background-color: #0F3460;
    min-height: 28px; max-height: 28px;
    border-top: 1px solid #1E6FBB;
}
#StatusLabel { color: #AAAAAA; font-size: 11px; padding: 0 12px; }

/* === Scan Overlay === */
#ScanOverlay { background-color: rgba(26, 26, 46, 210); }
#ScanOverlayCard { background-color: #16213E; border: 1px solid #1E6FBB; border-radius: 12px; }
#ScanOverlayLabel { color: #E0E0E0; font-size: 15px; font-weight: bold; }

/* === Content Area === */
#ContentArea { background-color: #1A1A2E; }

/* === Cards === */
QFrame#Card { background-color: #16213E; border: 1px solid #0F3460; border-radius: 10px; padding: 4px; }

/* Clickable card: shows hover feedback */
QFrame#CardHover {
    background-color: #16213E;
    border: 1px solid #0F3460;
    border-radius: 10px;
    padding: 4px;
}
QFrame#CardHover:hover { background-color: #1A2847; border: 1px solid #1E6FBB; }

QFrame#CardAccent { background-color: #16213E; border: 1px solid #1E6FBB; border-radius: 10px; padding: 4px; }
QFrame#CardWarning { background-color: #16213E; border: 1px solid #E67E22; border-radius: 10px; }
QFrame#CardError { background-color: #16213E; border: 1px solid #C0392B; border-radius: 10px; }
QFrame#CardSuccess { background-color: #16213E; border: 1px solid #2ECC71; border-radius: 10px; }

/* === Stat Labels === */
#StatNumber { font-size: 32px; font-weight: bold; color: #1E6FBB; }
#StatNumberWarn { font-size: 32px; font-weight: bold; color: #E67E22; }
#StatNumberError { font-size: 32px; font-weight: bold; color: #C0392B; }
#StatNumberSuccess { font-size: 32px; font-weight: bold; color: #2ECC71; }
#StatLabel { font-size: 11px; color: #888888; letter-spacing: 1px; }

/* === Buttons === */
QPushButton {
    background-color: #1E6FBB; color: #FFFFFF;
    border: none; border-radius: 6px;
    padding: 8px 18px; font-size: 13px; font-weight: bold;
}
QPushButton:hover { background-color: #2980C9; }
QPushButton:pressed { background-color: #1A5C9E; }
QPushButton:focus { outline: none; }
QPushButton:disabled { background-color: #333355; color: #666666; }
QPushButton#SecondaryButton { background-color: #0F3460; color: #AAAAAA; border: 1px solid #1E3A6E; }
QPushButton#SecondaryButton:hover { background-color: #1E3A6E; color: #FFFFFF; }
QPushButton#DangerButton { background-color: #C0392B; }
QPushButton#DangerButton:hover { background-color: #E74C3C; }
QPushButton#SuccessButton { background-color: #27AE60; }
QPushButton#SuccessButton:hover { background-color: #2ECC71; }
QPushButton#IconButton { background-color: transparent; color: #AAAAAA; border: none; border-radius: 4px; padding: 4px 8px; font-size: 16px; }
QPushButton#IconButton:hover { background-color: #0F3460; color: #FFFFFF; }

/* === Tables === */
QTableWidget {
    background-color: #16213E; alternate-background-color: #1A2540;
    border: 1px solid #0F3460; border-radius: 6px;
    gridline-color: #0F3460; selection-background-color: #1E6FBB; color: #E0E0E0;
}
QTableWidget::item { padding: 6px 10px; border: none; }
QTableWidget::item:selected { background-color: #1E6FBB; color: #FFFFFF; }
QHeaderView::section {
    background-color: #0F3460; color: #AAAAAA;
    padding: 8px 10px; border: none; border-right: 1px solid #16213E;
    font-weight: bold; font-size: 12px;
}

/* === Input === */
QLineEdit {
    background-color: #0F3460; color: #E0E0E0;
    border: 1px solid #1E3A6E; border-radius: 6px; padding: 7px 12px; font-size: 13px;
}
QLineEdit:focus { border: 1px solid #1E6FBB; }
QLineEdit::placeholder { color: #555577; }

/* === ComboBox === */
QComboBox { background-color: #0F3460; color: #E0E0E0; border: 1px solid #1E3A6E; border-radius: 6px; padding: 6px 12px; }
QComboBox::drop-down { border: none; padding-right: 8px; }
QComboBox QAbstractItemView { background-color: #16213E; border: 1px solid #1E6FBB; selection-background-color: #1E6FBB; color: #E0E0E0; }

/* === Progress Bar === */
QProgressBar { background-color: #0F3460; border: none; border-radius: 4px; height: 8px; color: transparent; }
QProgressBar::chunk { background-color: #1E6FBB; border-radius: 4px; }

/* === Scroll === */
QScrollBar:vertical { background: #16213E; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #0F3460; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #1E6FBB; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #16213E; height: 8px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #0F3460; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #1E6FBB; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* === Labels === */
QLabel { background-color: transparent; }
QLabel#PageTitle { font-size: 22px; font-weight: bold; color: #FFFFFF; }
QLabel#PageSubtitle { font-size: 12px; color: #666688; }
QLabel#SectionTitle { font-size: 11px; font-weight: bold; color: #555577; letter-spacing: 1px; }
QLabel#ErrorLabel { color: #E74C3C; font-size: 12px; }
QLabel#SuccessLabel { color: #2ECC71; font-size: 12px; }
QLabel#WarningLabel { color: #E67E22; font-size: 12px; }

/* === Tooltips === */
QToolTip { background-color: #0F3460; color: #E0E0E0; border: 1px solid #1E6FBB; border-radius: 4px; padding: 4px 8px; font-size: 12px; }

/* === Splitter (6px, highlights on hover) === */
QSplitter::handle { background-color: #0F3460; }
QSplitter::handle:horizontal { width: 6px; background-color: #0F3460; }
QSplitter::handle:horizontal:hover { background-color: #1E6FBB; }
QSplitter::handle:vertical { height: 6px; background-color: #0F3460; }
QSplitter::handle:vertical:hover { background-color: #1E6FBB; }

/* === TreeWidget === */
QTreeWidget { background-color: #16213E; border: 1px solid #0F3460; border-radius: 6px; color: #E0E0E0; alternate-background-color: #1A2540; }
QTreeWidget::item:hover { background-color: #0F3460; }
QTreeWidget::item:selected { background-color: #1E6FBB; color: #FFFFFF; }
QTreeWidget::branch { background-color: #16213E; }

/* === GroupBox (Synth Editor param groups — theme-controlled, no inline styles) === */
QGroupBox {
    font-weight: bold; font-size: 11px; color: #1E6FBB;
    border: 1px solid #0F3460; border-radius: 6px;
    margin-top: 10px; padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; color: #1E6FBB; padding: 0 4px; }

/* === Slider === */
QSlider::groove:horizontal { background: #0F3460; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #1E6FBB; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #2980C9; }
QSlider::sub-page:horizontal { background: #1E6FBB; border-radius: 2px; }

/* === Message Box === */
QMessageBox { background-color: #16213E; color: #E0E0E0; }
QMessageBox QPushButton { min-width: 80px; }

/* === CheckBox === */
QCheckBox { color: #E0E0E0; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 2px solid #0F3460; background-color: #16213E; }
QCheckBox::indicator:checked { background-color: #1E6FBB; border: 2px solid #1E6FBB; }
QCheckBox::indicator:hover { border: 2px solid #1E6FBB; }

/* === Tab Widget === */
QTabWidget::pane { border: 1px solid #0F3460; border-radius: 6px; background-color: #16213E; }
QTabBar::tab { background-color: #1A1A2E; color: #888888; border: 1px solid #0F3460; border-bottom: none; padding: 8px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background-color: #16213E; color: #FFFFFF; border-bottom: 2px solid #1E6FBB; }
QTabBar::tab:hover:!selected { background-color: #0F3460; color: #E0E0E0; }

/* === Toast Notifications === */
#ToastSuccess { background-color: #1A3A2A; border: 1px solid #2ECC71; border-radius: 8px; }
#ToastError   { background-color: #3A1A1A; border: 1px solid #E74C3C; border-radius: 8px; }
#ToastInfo    { background-color: #16213E; border: 1px solid #1E6FBB; border-radius: 8px; }
#ToastWarning { background-color: #3A2A10; border: 1px solid #E67E22; border-radius: 8px; }
#ToastLabel   { color: #E0E0E0; font-size: 13px; padding: 4px 10px; }

/* === Synth Editor — param row labels === */
QLabel#SynthTitle  { font-weight: bold; font-size: 15px; color: #FFFFFF; }
QLabel#ParamLabel  { font-size: 11px; color: #AAAAAA; }
QLabel#ParamValue  { font-size: 11px; color: #1E6FBB; font-weight: bold; }
"""

LIGHT = """
/* === Global === */
QWidget { background-color: #F5F7FA; color: #1A1A2E; font-family: "Segoe UI", Arial, sans-serif; font-size: 13px; }
QMainWindow { background-color: #F5F7FA; }

/* === Sidebar === */
#Sidebar { background-color: #FFFFFF; border-right: 1px solid #DDDDEE; min-width: 220px; max-width: 220px; }
#SidebarCollapsed { background-color: #FFFFFF; border-right: 1px solid #DDDDEE; min-width: 52px; max-width: 52px; }
#AppTitle { color: #1E6FBB; font-size: 18px; font-weight: bold; padding: 20px 16px 8px 16px; }
#AppSubtitle { color: #AAAAAA; font-size: 10px; padding: 0px 16px 20px 16px; }

/* === Nav Buttons === */
QPushButton#NavButton { background-color: transparent; color: #666666; border: none; border-radius: 8px; padding: 10px 16px; text-align: left; font-size: 13px; }
QPushButton#NavButton:hover { background-color: #EAF2FB; color: #1E6FBB; }
QPushButton#NavButton[active="true"] { background-color: #1E6FBB; color: #FFFFFF; font-weight: bold; }
QPushButton#NavButtonCollapsed { background-color: transparent; color: #888888; border: none; border-radius: 8px; padding: 10px 0px; text-align: center; font-size: 16px; min-width: 36px; max-width: 36px; }
QPushButton#NavButtonCollapsed:hover { background-color: #EAF2FB; color: #1E6FBB; }
QPushButton#NavButtonCollapsed[active="true"] { background-color: #1E6FBB; color: #FFFFFF; }
QPushButton#CollapseButton { background-color: transparent; color: #BBBBCC; border: none; border-radius: 4px; padding: 4px; font-size: 14px; }
QPushButton#CollapseButton:hover { background-color: #EAF2FB; color: #1E6FBB; }

/* === Top Bar === */
#TopBar { background-color: #FFFFFF; border-bottom: 1px solid #DDDDEE; min-height: 52px; max-height: 52px; }
#SDPathLabel { color: #AAAAAA; font-size: 12px; padding: 0 8px; }
#SDPathValue { color: #1A1A2E; font-size: 12px; font-weight: bold; }

/* === Status Bar === */
#StatusBar { background-color: #EAF2FB; min-height: 28px; max-height: 28px; border-top: 1px solid #BBCCEE; }
#StatusLabel { color: #888888; font-size: 11px; padding: 0 12px; }

/* === Scan Overlay === */
#ScanOverlay { background-color: rgba(245, 247, 250, 210); }
#ScanOverlayCard { background-color: #FFFFFF; border: 1px solid #1E6FBB; border-radius: 12px; }
#ScanOverlayLabel { color: #1A1A2E; font-size: 15px; font-weight: bold; }

/* === Content Area === */
#ContentArea { background-color: #F5F7FA; }

/* === Cards === */
QFrame#Card { background-color: #FFFFFF; border: 1px solid #DDDDEE; border-radius: 10px; }
QFrame#CardHover { background-color: #FFFFFF; border: 1px solid #DDDDEE; border-radius: 10px; }
QFrame#CardHover:hover { background-color: #F0F6FF; border: 1px solid #1E6FBB; }
QFrame#CardAccent { background-color: #FFFFFF; border: 1px solid #1E6FBB; border-radius: 10px; }
QFrame#CardWarning { background-color: #FFFFFF; border: 1px solid #E67E22; border-radius: 10px; }
QFrame#CardError { background-color: #FFFFFF; border: 1px solid #C0392B; border-radius: 10px; }
QFrame#CardSuccess { background-color: #FFFFFF; border: 1px solid #2ECC71; border-radius: 10px; }

/* === Stat Labels === */
#StatNumber { font-size: 32px; font-weight: bold; color: #1E6FBB; }
#StatNumberWarn { font-size: 32px; font-weight: bold; color: #E67E22; }
#StatNumberError { font-size: 32px; font-weight: bold; color: #C0392B; }
#StatNumberSuccess { font-size: 32px; font-weight: bold; color: #27AE60; }
#StatLabel { font-size: 11px; color: #AAAAAA; letter-spacing: 1px; }

/* === Buttons === */
QPushButton { background-color: #1E6FBB; color: #FFFFFF; border: none; border-radius: 6px; padding: 8px 18px; font-weight: bold; font-size: 13px; }
QPushButton:hover { background-color: #2980C9; }
QPushButton:pressed { background-color: #1A5C9E; }
QPushButton:focus { outline: none; }
QPushButton:disabled { background-color: #CCCCDD; color: #AAAAAA; }
QPushButton#SecondaryButton { background-color: #F0F0F5; color: #444444; border: 1px solid #CCCCDD; }
QPushButton#SecondaryButton:hover { background-color: #E0E0EE; color: #1A1A2E; }
QPushButton#DangerButton { background-color: #C0392B; color: #FFF; }
QPushButton#DangerButton:hover { background-color: #E74C3C; }
QPushButton#SuccessButton { background-color: #27AE60; color: #FFF; }
QPushButton#SuccessButton:hover { background-color: #2ECC71; }
QPushButton#IconButton { background-color: transparent; color: #888888; border: none; border-radius: 4px; padding: 4px 8px; font-size: 16px; }
QPushButton#IconButton:hover { background-color: #EAF2FB; color: #1E6FBB; }

/* === Tables === */
QTableWidget { background-color: #FFFFFF; alternate-background-color: #F5F7FA; border: 1px solid #DDDDEE; border-radius: 6px; gridline-color: #EEEEEE; selection-background-color: #1E6FBB; color: #1A1A2E; }
QTableWidget::item { padding: 6px 10px; }
QTableWidget::item:selected { background-color: #1E6FBB; color: #FFFFFF; }
QHeaderView::section { background-color: #F0F0F8; color: #555555; padding: 8px 10px; border: none; border-right: 1px solid #EEEEEE; font-weight: bold; font-size: 12px; }

/* === Input === */
QLineEdit { background-color: #FFFFFF; color: #1A1A2E; border: 1px solid #CCCCDD; border-radius: 6px; padding: 7px 12px; }
QLineEdit:focus { border: 1px solid #1E6FBB; }
QLineEdit::placeholder { color: #AAAAAA; }

/* === ComboBox === */
QComboBox { background-color: #FFFFFF; color: #1A1A2E; border: 1px solid #CCCCDD; border-radius: 6px; padding: 6px 12px; }
QComboBox::drop-down { border: none; padding-right: 8px; }
QComboBox QAbstractItemView { background-color: #FFFFFF; border: 1px solid #1E6FBB; selection-background-color: #1E6FBB; color: #1A1A2E; }

/* === Progress Bar === */
QProgressBar { background-color: #E0E0EE; border: none; border-radius: 4px; height: 8px; color: transparent; }
QProgressBar::chunk { background-color: #1E6FBB; border-radius: 4px; }

/* === Scroll === */
QScrollBar:vertical { background: #F0F0F8; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #CCCCDD; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #1E6FBB; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #F0F0F8; height: 8px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #CCCCDD; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #1E6FBB; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* === Labels === */
QLabel { background-color: transparent; }
QLabel#PageTitle { font-size: 22px; font-weight: bold; color: #1A1A2E; }
QLabel#PageSubtitle { font-size: 12px; color: #AAAAAA; }
QLabel#SectionTitle { font-size: 11px; font-weight: bold; color: #8888AA; letter-spacing: 1px; }
QLabel#ErrorLabel { color: #C0392B; font-size: 12px; }
QLabel#SuccessLabel { color: #27AE60; font-size: 12px; }
QLabel#WarningLabel { color: #E67E22; font-size: 12px; }

/* === Tooltips === */
QToolTip { background-color: #FFFFFF; color: #1A1A2E; border: 1px solid #1E6FBB; border-radius: 4px; padding: 4px 8px; }

/* === Splitter === */
QSplitter::handle { background-color: #DDDDEE; }
QSplitter::handle:horizontal { width: 6px; background-color: #DDDDEE; }
QSplitter::handle:horizontal:hover { background-color: #1E6FBB; }
QSplitter::handle:vertical { height: 6px; background-color: #DDDDEE; }
QSplitter::handle:vertical:hover { background-color: #1E6FBB; }

/* === TreeWidget === */
QTreeWidget { background-color: #FFFFFF; border: 1px solid #DDDDEE; border-radius: 6px; color: #1A1A2E; }
QTreeWidget::item:hover { background-color: #EAF2FB; }
QTreeWidget::item:selected { background-color: #1E6FBB; color: #FFF; }
QTreeWidget::branch { background-color: #FFFFFF; }

/* === GroupBox === */
QGroupBox { font-weight: bold; font-size: 11px; color: #1E6FBB; border: 1px solid #CCCCDD; border-radius: 6px; margin-top: 10px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; color: #1E6FBB; padding: 0 4px; }

/* === Slider === */
QSlider::groove:horizontal { background: #DDDDEE; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #1E6FBB; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #2980C9; }
QSlider::sub-page:horizontal { background: #1E6FBB; border-radius: 2px; }

/* === Message Box === */
QMessageBox { background-color: #FFFFFF; color: #1A1A2E; }
QMessageBox QPushButton { min-width: 80px; }

/* === CheckBox === */
QCheckBox { color: #1A1A2E; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 2px solid #CCCCDD; background-color: #FFFFFF; }
QCheckBox::indicator:checked { background-color: #1E6FBB; border: 2px solid #1E6FBB; }
QCheckBox::indicator:hover { border: 2px solid #1E6FBB; }

/* === Tab Widget === */
QTabWidget::pane { border: 1px solid #DDDDEE; border-radius: 6px; background-color: #FFFFFF; }
QTabBar::tab { background-color: #F0F0F8; color: #888888; border: 1px solid #DDDDEE; border-bottom: none; padding: 8px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background-color: #FFFFFF; color: #1A1A2E; border-bottom: 2px solid #1E6FBB; }
QTabBar::tab:hover:!selected { background-color: #EAF2FB; color: #1E6FBB; }

/* === Toast Notifications === */
#ToastSuccess { background-color: #E8F8F0; border: 1px solid #27AE60; border-radius: 8px; }
#ToastError   { background-color: #FDEDEC; border: 1px solid #C0392B; border-radius: 8px; }
#ToastInfo    { background-color: #EAF2FB; border: 1px solid #1E6FBB; border-radius: 8px; }
#ToastWarning { background-color: #FEF9E7; border: 1px solid #E67E22; border-radius: 8px; }
#ToastLabel   { color: #1A1A2E; font-size: 13px; padding: 4px 10px; }

/* === Synth Editor — param row labels === */
QLabel#SynthTitle  { font-weight: bold; font-size: 15px; color: #1A1A2E; }
QLabel#ParamLabel  { font-size: 11px; color: #888888; }
QLabel#ParamValue  { font-size: 11px; color: #1E6FBB; font-weight: bold; }
"""


def get_theme(name: str) -> str:
    return DARK if name == "dark" else LIGHT
