"""
Main application window for NMR-Pore-Analyzer.

The UI keeps the original desktop workflow:
open .xlsx/.xls/.csv -> analyse every amplitude column -> plot -> export Excel.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic.analyzer import AnalysisResult, analyse, get_amplitude_columns
from logic.config import APP_NAME, APP_VERSION, IntegrationMode, MORANDI_PALETTE
from logic.exporter import export_batch_results
from logic.peak_processor import PeakResult, detect_peaks
from ui.plot_canvas import PlotCanvas


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

_INTEGRATION_MODES: list[IntegrationMode] = [
    IntegrationMode.BIN_SUMMATION,
    IntegrationMode.LOG_TRAPEZOIDAL,
    IntegrationMode.LINEAR_TRAPEZOIDAL,
]


class BatchWorker(QObject):
    """Analyse every amplitude column in a multi-sample file."""

    progress: Signal = Signal(int)
    col_done: Signal = Signal(str, object, object)
    finished: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(
        self,
        file_path: Path,
        columns: list[str],
        mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
    ) -> None:
        super().__init__()
        self._file_path = file_path
        self._columns = columns
        self._mode = mode

    @Slot()
    def run(self) -> None:
        results: list[tuple[AnalysisResult, PeakResult]] = []
        n = len(self._columns)
        try:
            if n == 0:
                raise ValueError("No amplitude columns to analyse.")
            for i, col in enumerate(self._columns):
                analysis = analyse(self._file_path, column=col, mode=self._mode)
                peak_result = detect_peaks(analysis.raw.t2_ms, analysis.raw.amplitude)
                results.append((analysis, peak_result))
                self.col_done.emit(col, analysis, peak_result)
                self.progress.emit(int((i + 1) / n * 100))
            self.finished.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Table constants/helpers
# ---------------------------------------------------------------------------

_SYS_A_COLOURS = ["#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2"]
_SYS_B_COLOURS = ["#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2"]
_HDR_MIXTURE_COL = "#5B7DB1"
_HDR_FG = "#FFFFFF"
_ROW_ALT_BG = "#F0F4FA"
_HIGHLIGHT_BG = "#DDE6F5"
_HIGHLIGHT_FG = "#1A3A6B"
_FALLBACK_BG = "#FFF3CD"


def _make_result_table(col_headers: list[str]) -> QTableWidget:
    tbl = QTableWidget(0, len(col_headers))
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
    tbl.horizontalHeader().setMinimumSectionSize(90)
    tbl.verticalHeader().setVisible(False)
    tbl.verticalHeader().setDefaultSectionSize(32)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setAlternatingRowColors(True)
    tbl.setShowGrid(True)
    tbl.setGridStyle(Qt.SolidLine)
    tbl.setStyleSheet(
        "QTableWidget { font-family: 'Times New Roman'; font-size: 12px; "
        "border: 1px solid #C0C8D8; gridline-color: #D8DEE8; }"
        "QTableWidget::item { padding: 5px 10px; }"
        "QTableWidget::item:selected { background-color: #2F5496; color: white; }"
        "QHeaderView::section { background-color: #5B7DB1; color: white; "
        "font-family: 'Times New Roman'; font-size: 12px; font-weight: bold; "
        "padding: 6px; border: 1px solid #8090AA; }"
    )
    for i, hdr in enumerate(col_headers):
        item = QTableWidgetItem(hdr)
        item.setTextAlignment(Qt.AlignCenter)
        font = QFont("Times New Roman", 11)
        font.setBold(True)
        item.setFont(font)
        tbl.setHorizontalHeaderItem(i, item)
    return tbl


def _insert_result_row(
    tbl: QTableWidget,
    values: list[str],
    *,
    highlight: bool = False,
    fallback_cols: list[int] | None = None,
) -> None:
    row = tbl.rowCount()
    tbl.insertRow(row)
    fallback_cols = fallback_cols or []
    for col, val in enumerate(values):
        item = QTableWidgetItem(val)
        item.setTextAlignment(Qt.AlignCenter)
        font = item.font()
        if highlight:
            item.setBackground(QColor(_HIGHLIGHT_BG))
            item.setForeground(QColor(_HIGHLIGHT_FG))
            font.setBold(True)
            item.setFont(font)
        elif col in fallback_cols:
            item.setBackground(QColor(_FALLBACK_BG))
        elif row % 2 == 1:
            item.setBackground(QColor(_ROW_ALT_BG))
        tbl.setItem(row, col, item)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        self._analysis: AnalysisResult | None = None
        self._peak_result: PeakResult | None = None
        self._file_path: Path | None = None
        self._thread: QThread | None = None
        self._batch_worker: BatchWorker | None = None
        self._amp_columns: list[str] = []
        self._batch_results: list[tuple[AnalysisResult, PeakResult]] = []
        self._psd_idx: int = 0
        self._ALL_SAMPLES = "── All Samples ──"

        self._build_ui()
        self._build_menu()
        self._apply_stylesheet()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        toolbar = QWidget()
        toolbar.setFixedHeight(46)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(4, 4, 4, 4)
        tb.setSpacing(6)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a data file...")
        self._path_edit.setReadOnly(True)
        self._path_edit.setFixedHeight(32)
        tb.addWidget(self._path_edit, stretch=1)

        self._btn_browse = QPushButton("📁  Browse")
        self._btn_browse.setFixedHeight(32)
        self._btn_browse.setToolTip("Open NMR data file (.xlsx / .xls / .csv)")
        self._btn_browse.clicked.connect(self._on_browse)
        tb.addWidget(self._btn_browse)

        self._btn_export = QPushButton("💾  Export xlsx")
        self._btn_export.setFixedHeight(32)
        self._btn_export.setEnabled(False)
        self._btn_export.setToolTip("Export all results to a four-sheet Excel workbook")
        self._btn_export.clicked.connect(self._on_export_excel)
        tb.addWidget(self._btn_export)

        mode_lbl = QLabel("积分:")
        mode_lbl.setStyleSheet("font-family:'Times New Roman'; font-size:11px; color:#444;")
        tb.addWidget(mode_lbl)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Bin Summation  (Recommended)")
        self._mode_combo.addItem("Log-domain Integration")
        self._mode_combo.addItem("Linear Integration  ⚠")
        self._mode_combo.setFixedHeight(32)
        self._mode_combo.setMinimumWidth(220)
        self._mode_combo.setToolTip(
            "Bin Summation: recommended for instrument inversion spectra\n"
            "Log-domain: integrates after boundary interpolation\n"
            "Linear ⚠: only for linearly sampled T2 axes"
        )
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tb.addWidget(self._mode_combo)

        self._warn_lbl = QLabel("⚠ Linear integration is only valid for linearly sampled T2 axes.")
        self._warn_lbl.setStyleSheet(
            "color: #B85C00; font-family:'Times New Roman'; font-size:10px;"
            "background:#FFF3CD; border:1px solid #FFBE7A; border-radius:3px; padding:2px 6px;"
        )
        self._warn_lbl.setVisible(False)
        tb.addWidget(self._warn_lbl)
        root.addWidget(toolbar)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        splitter = QSplitter(Qt.Vertical)

        self._chart_tabs = QTabWidget()
        bar_wrap = QWidget()
        bar_lay = QVBoxLayout(bar_wrap)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        self._bar_canvas = PlotCanvas(mode="bar")
        bar_lay.addWidget(self._bar_canvas)
        self._chart_tabs.addTab(bar_wrap, "System A / B Bar Charts")

        psd_wrap = QWidget()
        psd_vlay = QVBoxLayout(psd_wrap)
        psd_vlay.setContentsMargins(4, 4, 4, 0)
        psd_vlay.setSpacing(4)
        psd_ctrl = QHBoxLayout()
        psd_lbl = QLabel("Sample:")
        psd_lbl.setStyleSheet("font-family:'Times New Roman'; font-size:11px;")
        psd_ctrl.addWidget(psd_lbl)
        self._psd_col_combo = QComboBox()
        self._psd_col_combo.setFixedHeight(28)
        self._psd_col_combo.setMinimumWidth(180)
        self._psd_col_combo.currentIndexChanged.connect(self._on_psd_col_changed)
        psd_ctrl.addWidget(self._psd_col_combo)
        psd_ctrl.addStretch()
        psd_vlay.addLayout(psd_ctrl)
        self._psd_canvas = PlotCanvas(mode="psd")
        psd_vlay.addWidget(self._psd_canvas, stretch=1)
        self._chart_tabs.addTab(psd_wrap, "Pore Size Distribution")
        splitter.addWidget(self._chart_tabs)

        tbl_area = QWidget()
        tbl_vlay = QVBoxLayout(tbl_area)
        tbl_vlay.setContentsMargins(4, 4, 4, 4)
        tbl_vlay.setSpacing(4)

        copy_bar = QHBoxLayout()
        copy_bar.addStretch()
        self._btn_copy = QPushButton("📋  复制表格")
        self._btn_copy.setObjectName("copyBtn")
        self._btn_copy.setFixedSize(120, 28)
        self._btn_copy.setToolTip("Copy current table to clipboard")
        self._btn_copy.clicked.connect(self._on_copy_table)
        copy_bar.addWidget(self._btn_copy)
        tbl_vlay.addLayout(copy_bar)

        self._tbl_tabs = QTabWidget()
        self._tbl_tabs.setDocumentMode(True)
        self._tbl_a = _make_result_table(
            ["Mixture", "Gel pores", "Transition pores", "Capillary pores", "Air-voids"]
        )
        self._tbl_tabs.addTab(self._tbl_a, "System A — Physical Morphology")
        self._tbl_b = _make_result_table(
            ["Mixture", "Harmless pores", "Less-harmful pores", "Harmful pores", "More-harmful pores"]
        )
        self._tbl_tabs.addTab(self._tbl_b, "System B — Damage Potential")
        self._tbl_peak = _make_result_table([
            "Mixture",
            "Primary T2 (ms)", "Primary r (nm)", "Primary Area%",
            "Secondary T2 (ms)", "Secondary r (nm)", "Secondary Area%",
            "Valley T2 (ms)", "Valley r (nm)", "Fallback?",
        ])
        self._tbl_tabs.addTab(self._tbl_peak, "Peak Analysis")
        tbl_vlay.addWidget(self._tbl_tabs, stretch=1)
        splitter.addWidget(tbl_area)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 480])
        root.addWidget(splitter, stretch=1)

        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready.")

    def _build_menu(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        act_open = QAction("&Open...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_browse)
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

        exp_menu = mb.addMenu("&Export")
        act_xlsx = QAction("Export to &Excel...", self)
        act_xlsx.setShortcut("Ctrl+E")
        act_xlsx.triggered.connect(self._on_export_excel)
        act_png = QAction("Save &Figure...", self)
        act_png.setShortcut("Ctrl+S")
        act_png.triggered.connect(self._on_save_figure)
        exp_menu.addAction(act_xlsx)
        exp_menu.addAction(act_png)

        help_menu = mb.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _apply_stylesheet(self) -> None:
        c = MORANDI_PALETTE
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: #F0F2F5;
                font-family: 'Times New Roman';
            }}
            QPushButton {{
                background-color: {c[3]};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-family: 'Times New Roman';
            }}
            QPushButton:hover {{ background-color: {c[0]}; color: #222; }}
            QPushButton:pressed {{ background-color: #5A8DB8; }}
            QPushButton:disabled {{ background-color: #C8C8C8; color: #888; }}
            QPushButton#copyBtn {{ background-color: #2F5496; font-size: 11px; padding: 3px 8px; }}
            QPushButton#copyBtn:hover {{ background-color: {c[3]}; }}
            QLineEdit, QComboBox {{
                background-color: white;
                border: 1px solid #C0C0C0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 11px;
            }}
            QTabWidget::pane {{ border: 1px solid #D0D0D0; background: white; }}
            QTabBar::tab {{
                font-family: 'Times New Roman';
                font-size: 12px;
                padding: 6px 16px;
                background: #E0E5EF;
                border: 1px solid #C0C8D8;
                border-bottom: none;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{ background: #2F5496; color: white; font-weight: bold; }}
            QTabBar::tab:hover:!selected {{ background: {c[0]}; color: #222; }}
            QProgressBar {{ background-color: #E0E0E0; border: none; }}
            QProgressBar::chunk {{ background-color: {c[3]}; }}
            QStatusBar {{ font-family: 'Times New Roman'; font-size: 11px; color: #444; }}
        """)

    # ------------------------------------------------------------------
    # Slots - file & analysis
    # ------------------------------------------------------------------
    @Slot()
    def _on_browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open NMR Data File",
            str(Path.home()),
            "Data files (*.xlsx *.xls *.csv);;All files (*)",
        )
        if not path_str:
            return

        self._file_path = Path(path_str)
        self._path_edit.setText(str(self._file_path))
        try:
            cols = get_amplitude_columns(self._file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Column Detection", str(exc))
            return

        self._amp_columns = cols
        n = len(cols)
        self._statusbar.showMessage(
            f"Loaded: {self._file_path.name} ({n} sample column{'s' if n > 1 else ''}) — analysing..."
        )
        self._run_batch()

    def _current_mode(self) -> IntegrationMode:
        return _INTEGRATION_MODES[self._mode_combo.currentIndex()]

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        self._warn_lbl.setVisible(index == 2)
        if self._file_path is not None and self._amp_columns:
            self._run_batch()

    def _run_batch(self) -> None:
        if self._file_path is None or not self._amp_columns:
            return

        if self._thread is not None and self._thread.isRunning():
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

        self._thread = QThread(self)
        worker = BatchWorker(self._file_path, list(self._amp_columns), self._current_mode())
        worker.moveToThread(self._thread)
        self._batch_worker = worker

        self._thread.started.connect(worker.run)
        worker.progress.connect(self._progress.setValue)
        worker.col_done.connect(self._on_batch_col_done)
        worker.finished.connect(self._on_batch_finished)
        worker.error.connect(self._on_analysis_error)
        worker.finished.connect(self._thread.quit)
        worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(lambda: self._set_busy(False))
        self._thread.start()

    @Slot(str, object, object)
    def _on_batch_col_done(self, col: str, analysis: AnalysisResult, peak_result: PeakResult) -> None:
        self._statusbar.showMessage(f"Processed: {col}")
        self._batch_results.append((analysis, peak_result))
        self._bar_canvas.plot_bar_charts(self._batch_results)
        self._analysis = analysis
        self._peak_result = peak_result
        self._psd_idx = len(self._batch_results) - 1
        self._psd_canvas.plot(
            analysis,
            peak_result,
            show_peaks=True,
            show_valley=True,
            show_classification=True,
        )

    @Slot(list)
    def _on_batch_finished(self, results: list[tuple[AnalysisResult, PeakResult]]) -> None:
        self._batch_results = results
        self._bar_canvas.plot_bar_charts(results)
        self._populate_psd_combo()
        self._populate_summary_tables(results)
        self._btn_export.setEnabled(True)
        n = len(results)
        self._statusbar.showMessage(f"Analysis complete — {n} column{'s' if n > 1 else ''} processed.")

    @Slot(str)
    def _on_analysis_error(self, msg: str) -> None:
        self._set_busy(False)
        self._statusbar.showMessage("Error during analysis.")
        QMessageBox.critical(self, "Analysis Error", msg)

    # ------------------------------------------------------------------
    # PSD selector
    # ------------------------------------------------------------------
    def _populate_psd_combo(self) -> None:
        self._psd_col_combo.blockSignals(True)
        self._psd_col_combo.clear()
        self._psd_col_combo.addItem(self._ALL_SAMPLES)
        for analysis, _ in self._batch_results:
            self._psd_col_combo.addItem(analysis.raw.sample_name)
        self._psd_col_combo.setCurrentIndex(0)
        self._psd_idx = -1
        self._psd_col_combo.blockSignals(False)
        self._show_all_psd()

    def _show_all_psd(self) -> None:
        self._psd_canvas.plot_multi(
            self._batch_results,
            show_peaks=False,
            show_valley=False,
            show_classification=True,
        )

    @Slot(int)
    def _on_psd_col_changed(self, idx: int) -> None:
        if idx == 0:
            self._psd_idx = -1
            self._show_all_psd()
            return
        real_idx = idx - 1
        if real_idx < 0 or real_idx >= len(self._batch_results):
            return
        self._psd_idx = real_idx
        analysis, peak_result = self._batch_results[real_idx]
        self._analysis = analysis
        self._peak_result = peak_result
        self._psd_canvas.plot(
            analysis,
            peak_result,
            show_peaks=True,
            show_valley=True,
            show_classification=True,
        )

    # ------------------------------------------------------------------
    # Export & misc
    # ------------------------------------------------------------------
    @Slot()
    def _on_export_excel(self) -> None:
        if not self._batch_results:
            QMessageBox.information(self, "No Data", "Open a file first.")
            return
        default_name = f"{self._file_path.stem}_results.xlsx" if self._file_path else "nmr_results.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Results",
            str(Path.home() / default_name),
            "Excel (*.xlsx)",
        )
        if not save_path:
            return
        try:
            batch_dict = {an.raw.sample_name: (an, pk) for an, pk in self._batch_results}
            out = export_batch_results(Path(save_path), batch_dict)
            QMessageBox.information(
                self,
                "Export Complete",
                f"All {len(self._batch_results)} samples exported to:\n{out}",
            )
            self._statusbar.showMessage(f"Exported → {out.name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Error", str(exc))

    @Slot()
    def _on_save_figure(self) -> None:
        if self._analysis is None:
            QMessageBox.information(self, "No Data", "Open a file first.")
            return
        default_name = f"{self._analysis.raw.source_path.stem}_pore_distribution.png"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pore Distribution Figure",
            str(Path.home() / default_name),
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if path_str:
            self._psd_canvas.save_figure(path_str)
            self._statusbar.showMessage(f"Figure saved → {Path(path_str).name}")

    @Slot()
    def _on_copy_table(self) -> None:
        idx = self._tbl_tabs.currentIndex()
        tbl = [self._tbl_a, self._tbl_b, self._tbl_peak][idx]
        lines: list[str] = []
        headers = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
        lines.append("\t".join(headers))
        for r in range(tbl.rowCount()):
            row_vals = []
            for c in range(tbl.columnCount()):
                item = tbl.item(r, c)
                row_vals.append(item.text() if item else "")
            lines.append("\t".join(row_vals))
        QApplication.clipboard().setText("\n".join(lines))
        self._statusbar.showMessage("Table copied to clipboard.")

    @Slot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME} v{APP_VERSION}</b><br>"
            "LF-NMR T2 pore-structure analysis tool.<br><br>"
            "Dual classification: System A (physical) &amp; System B (damage potential).<br>"
            "Strict peak detection with valley-based splitting and fallback flag.<br><br>"
            "For academic research use.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._btn_browse.setEnabled(not busy)
        self._mode_combo.setEnabled(not busy)
        self._btn_export.setEnabled((not busy) and bool(self._batch_results))
        self._progress.setVisible(busy)
        if busy:
            self._progress.setValue(0)

    def _populate_summary_tables(self, results: list[tuple[AnalysisResult, PeakResult]]) -> None:
        self._tbl_a.setRowCount(0)
        self._tbl_b.setRowCount(0)
        self._tbl_peak.setRowCount(0)

        last_idx = len(results) - 1
        for idx, (analysis, peak_result) in enumerate(results):
            highlight = idx == last_idx and len(results) > 1
            name = analysis.raw.sample_name

            row_a = [name] + [f"{r * 100:.2f} %" for r in analysis.system_a.ratios]
            _insert_result_row(self._tbl_a, row_a, highlight=highlight)

            row_b = [name] + [f"{r * 100:.2f} %" for r in analysis.system_b.ratios]
            _insert_result_row(self._tbl_b, row_b, highlight=highlight)

            pri = peak_result.primary
            if peak_result.has_secondary and peak_result.secondary is not None:
                sec = peak_result.secondary
                val = peak_result.valley
                sec_t2 = f"{sec.t2_ms:.3f}"
                sec_r = f"{sec.radius_nm:.1f}"
                sec_pct = f"{sec.area_ratio * 100:.2f} %"
                if val is not None:
                    v_t2 = f"{val.t2_ms:.3f}"
                    v_r = f"{val.radius_nm:.1f}"
                    v_fb = "Yes" if val.is_fallback else "No"
                    fb_cols = [7, 8, 9] if (val.is_fallback and not highlight) else []
                else:
                    v_t2 = v_r = v_fb = "—"
                    fb_cols = []
            else:
                sec_t2 = sec_r = sec_pct = "—"
                v_t2 = v_r = v_fb = "—"
                fb_cols = []

            row_pk = [
                name,
                f"{pri.t2_ms:.3f}", f"{pri.radius_nm:.1f}", f"{pri.area_ratio * 100:.2f} %",
                sec_t2, sec_r, sec_pct,
                v_t2, v_r, v_fb,
            ]
            _insert_result_row(self._tbl_peak, row_pk, highlight=highlight, fallback_cols=fb_cols)
