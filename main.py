"""
NMR-Pore-Analyzer v2.0 — Application entry point.

Usage
-----
    python main.py
"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.main_window import MainWindow


def _exception_hook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: object,
) -> None:
    """Global uncaught-exception handler.

    Displays a critical dialog so the user sees the error rather than
    a silent crash, then falls back to the default hook.
    """
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
    # High-DPI rendering
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NMR-Pore-Analyzer")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("Research Lab")

    sys.excepthook = _exception_hook

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
