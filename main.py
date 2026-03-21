"""
DelugeHub — Entry Point
"""
import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.main_window import MainWindow
from app.modules.settings_module import APP_VERSION

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
    # AA_UseHighDpiPixmaps is enabled by default in PySide6 6.x and deprecated
    # — no need to set it manually.

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
