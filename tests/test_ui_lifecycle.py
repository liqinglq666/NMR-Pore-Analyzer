from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ui.main_window import MainWindow


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    yield win
    if win._thread_running():
        win._thread.quit()
        win._thread.wait(10000)
    app.processEvents()
    win.close()


def _wait_for_analysis(window: MainWindow) -> None:
    deadline = time.monotonic() + 10
    while window._thread is not None and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert window._thread is None, "Worker thread did not finish."


def test_repeated_analysis_releases_thread(window: MainWindow, tmp_path: Path) -> None:
    data_path = tmp_path / "sample.csv"
    pd.DataFrame({
        "T2(ms)": [0.1, 0.2, 1.0, 5.0, 20.0, 80.0],
        "Amplitude": [1.0, 4.0, 2.0, 1.0, 0.5, 0.2],
    }).to_csv(data_path, index=False)

    window._file_path = data_path
    window._amp_columns = ["Amplitude"]
    window._run_batch()
    _wait_for_analysis(window)
    assert len(window._batch_results) == 1
    assert window._batch_worker is None
    assert window._btn_export.isEnabled()

    window._mode_combo.setCurrentIndex(1)
    _wait_for_analysis(window)
    assert len(window._batch_results) == 1
    assert window._batch_worker is None
    assert window._btn_export.isEnabled()


def test_invalid_file_does_not_replace_loaded_file(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    previous = tmp_path / "previous.csv"
    window._file_path = previous
    window._amp_columns = ["Amplitude"]
    window._path_edit.setText(str(previous))
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "missing.csv"), ""),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)

    window._on_browse()

    assert window._file_path == previous
    assert window._amp_columns == ["Amplitude"]
    assert window._path_edit.text() == str(previous)


def test_failed_run_drops_partial_results(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window._batch_results = [(object(), object())]
    window._analysis = object()
    window._peak_result = object()
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)

    window._on_analysis_error("Invalid input")

    assert not window._batch_results
    assert window._analysis is None
    assert window._peak_result is None
    assert not window._btn_export.isEnabled()


def test_close_is_blocked_while_worker_runs(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = QCloseEvent()
    with monkeypatch.context() as patch:
        patch.setattr(window, "_thread_running", lambda: True)
        patch.setattr(QMessageBox, "information", lambda *args: None)
        window.closeEvent(event)
    assert not event.isAccepted()


def test_file_and_export_menus_are_blocked_while_busy(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_dialog(*args, **kwargs):
        pytest.fail("File dialog must not open while analysis is running.")

    with monkeypatch.context() as patch:
        patch.setattr(window, "_analysis_busy", lambda: True)
        patch.setattr(QFileDialog, "getOpenFileName", unexpected_dialog)
        patch.setattr(QFileDialog, "getSaveFileName", unexpected_dialog)
        patch.setattr(QMessageBox, "information", lambda *args: None)

        window._on_browse()
        window._on_export_excel()
        window._on_save_figure()
