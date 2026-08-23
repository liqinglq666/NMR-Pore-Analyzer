"""Safety wrapper for the Qt main window.

This module keeps ``ui.main_window`` reusable while fixing QThread lifecycle
cleanup in the application entry point. It avoids dangling deleted-QObject
references when users re-run analysis after changing the integration mode.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import QMessageBox

from ui.main_window import BatchWorker, MainWindow as _BaseMainWindow


class MainWindow(_BaseMainWindow):
    """MainWindow with robust worker-thread cleanup."""

    def _thread_running(self) -> bool:
        if self._thread is None:
            return False
        try:
            return bool(self._thread.isRunning())
        except RuntimeError:
            self._thread = None
            self._batch_worker = None
            return False

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        self._set_busy(False)
        self._thread = None
        self._batch_worker = None

    def _run_batch(self) -> None:
        if self._file_path is None or not self._amp_columns:
            return

        if self._thread_running():
            QMessageBox.information(self, "Busy", "Analysis is still running.")
            return

        self._batch_results = []
        self._analysis = None
        self._peak_result = None
        self._btn_export.setEnabled(False)
        self._populate_summary_tables([])
        self._bar_canvas.clear()
        self._psd_canvas.clear()
        self._set_busy(True)

        thread = QThread(self)
        worker = BatchWorker(self._file_path, list(self._amp_columns), self._current_mode())
        worker.moveToThread(thread)
        self._thread = thread
        self._batch_worker = worker

        thread.started.connect(worker.run)
        worker.progress.connect(self._progress.setValue)
        worker.col_done.connect(self._on_batch_col_done)
        worker.finished.connect(self._on_batch_finished)
        worker.error.connect(self._on_analysis_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._on_worker_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()
