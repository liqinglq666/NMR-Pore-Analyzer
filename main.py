"""
NMR-Pore-Analyzer — Application entry point.

Usage
-----
    python main.py
"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from logic.config import APP_NAME, APP_VERSION, ORGANIZATION_NAME
from ui.main_window import MainWindow


def _exception_hook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: object,
) -> None:
    """Global uncaught-exception handler."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(msg, file=sys.stderr)
    dlg = QMessageBox()
    dlg.setWindowTitle("Unexpected Error")
    dlg.setIcon(QMessageBox.Critical)
    dlg.setText("An unexpected error occurred.\nSee details below.")
    dlg.setDetailedText(msg)
    dlg.exec()
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> None:
    """Bootstrap and run the Qt application."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)

    sys.excepthook = _exception_hook

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
