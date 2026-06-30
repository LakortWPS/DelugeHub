"""
DelugeHub — Entry Point
"""
import sys
import ctypes
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from app.main_window import MainWindow
from app.modules.settings_module import APP_VERSION

# Windows: AppUserModelID setzen damit Taskleiste + Fenster-Icon korrekt sind
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DelugeHub.App")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DelugeHub")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("DelugeHub")

    # Icon aus eingebettetem Modul laden — kein Dateipfad, funktioniert in
    # Dev und PyInstaller-Build gleichermassen
    from app._icon_data import ICON_BYTES
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QPixmap
    _pixmap = QPixmap()
    _pixmap.loadFromData(QByteArray(ICON_BYTES))
    if not _pixmap.isNull():
        app.setWindowIcon(QIcon(_pixmap))
    # AA_UseHighDpiPixmaps is enabled by default in PySide6 6.x and deprecated
    # — no need to set it manually.

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
