"""
Main application window for NMR-Pore-Analyzer.

Layout
------
┌──────────────────────────────────────────────────────────────────────┐
│  [path_edit]  Browse  Export xlsx  Export Pore Dist.  积分模式        │  toolbar
├──────────────────────────────────────────────────────────────────────┤
│  Tab: [System A / B Bar Charts] [Pore Size Distribution]             │
│       PSD tab: inline Sample combo to switch displayed curve         │
├──────────────────────────────────────────────────────────────────────┤
│  Tab: [System A] [System B] [Peak Analysis]          [复制表格]       │
├──────────────────────────────────────────────────────────────────────┤
│  Status bar                                                          │
└──────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject
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
from logic.config import IntegrationMode
from logic.peak_processor import PeakResult, detect_peaks
from logic.exporter import export_batch_results
from logic.config import MORANDI_PALETTE
from ui.plot_canvas import PlotCanvas


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class AnalysisWorker(QObject):
    """Run single-column analysis in a background thread.

    Signals:
        finished: Emitted with (AnalysisResult, PeakResult) on success.
        error:    Emitted with an error message string on failure.
        progress: Emitted with an integer [0-100] during processing.
    """

    finished: Signal = Signal(object, object)
    error:    Signal = Signal(str)
    progress: Signal = Signal(int)

    def __init__(self, file_path: Path, column: Optional[str] = None) -> None:
        super().__init__()
        self._file_path = file_path
        self._column = column

    @Slot()
    def run(self) -> None:
        """Execute the full analysis pipeline."""
        try:
            self.progress.emit(20)
            analysis = analyse(self._file_path, column=self._column)
            self.progress.emit(60)
            peak_result = detect_peaks(analysis.raw.t2_ms, analysis.raw.amplitude)
            self.progress.emit(100)
            self.finished.emit(analysis, peak_result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# Map ComboBox index → IntegrationMode
_INTEGRATION_MODES: list[IntegrationMode] = [
    IntegrationMode.BIN_SUMMATION,
    IntegrationMode.LOG_TRAPEZOIDAL,
    IntegrationMode.LINEAR_TRAPEZOIDAL,
]


class BatchWorker(QObject):
    """Analyse every amplitude column in a multi-sample file.

    Signals:
        progress: Integer [0-100].
        col_done: Emitted after each column: (col_name, AnalysisResult, PeakResult).
        finished: Emitted with the list of (AnalysisResult, PeakResult) tuples.
        error:    Emitted with an error message string on failure.
    """

    progress: Signal = Signal(int)
    col_done: Signal = Signal(str, object, object)
    finished: Signal = Signal(list)
    error:    Signal = Signal(str)

    def __init__(
        self,
        file_path: Path,
        columns: list[str],
        mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
    ) -> None:
        super().__init__()
        self._file_path = file_path
        self._columns   = columns
        self._mode      = mode

    @Slot()
    def run(self) -> None:
        """Analyse all columns sequentially."""
        results: list[tuple[AnalysisResult, PeakResult]] = []
        n = len(self._columns)
        try:
            for i, col in enumerate(self._columns):
                analysis    = analyse(self._file_path, column=col, mode=self._mode)
                peak_result = detect_peaks(analysis.raw.t2_ms, analysis.raw.amplitude)
                results.append((analysis, peak_result))
                self.col_done.emit(col, analysis, peak_result)
                self.progress.emit(int((i + 1) / n * 100))
            self.finished.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Table colour constants
# ---------------------------------------------------------------------------

_SYS_A_COLOURS   = ["#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2"]
_SYS_B_COLOURS   = ["#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2"]
_HDR_MIXTURE_COL = "#5B7DB1"
_HDR_FG          = "#FFFFFF"
_ROW_ALT_BG      = "#F0F4FA"
_HIGHLIGHT_BG    = "#DDE6F5"   # light blue tint for last row (non-selected)
_HIGHLIGHT_FG    = "#1A3A6B"   # dark blue text
_FALLBACK_BG     = "#FFF3CD"   # yellow for fallback valley cells


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def _make_result_table(
    col_headers: list[str],
    col_colours: list[str],
) -> QTableWidget:
    """Create a styled result table with per-column coloured headers.

    Uses a per-section stylesheet built from col_colours so that the global
    QWidget background-color rule cannot override header cell colours.

    Args:
        col_headers: Column header labels.
        col_colours: Background colour for each header cell.

    Returns:
        Configured QTableWidget.
    """
    tbl = QTableWidget(0, len(col_headers))
    tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
    tbl.horizontalHeader().setDefaultSectionSize(130)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.horizontalHeader().resizeSection(0, 110)
    tbl.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
    tbl.horizontalHeader().setMinimumSectionSize(80)
    tbl.verticalHeader().setVisible(False)
    tbl.verticalHeader().setDefaultSectionSize(32)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setAlternatingRowColors(True)
    tbl.setShowGrid(True)
    tbl.setGridStyle(Qt.SolidLine)

    # Build per-section stylesheet: nth-section(i) selectors for each column.
    # This is the only reliable way to colour individual header cells in PySide6
    # when a global QWidget stylesheet is also present.
    section_rules = ""
    for i, colour in enumerate(col_colours):
        section_rules += (
            f"QHeaderView::section:nth-section({i}) {{"
            f" background-color: {colour}; color: {_HDR_FG}; "
            f"font-family: 'Times New Roman'; font-size: 12px; font-weight: bold;"
            f" padding: 6px; border: 1px solid #8090AA; }}"
        )

    tbl.setStyleSheet(
        "QTableWidget { font-family: 'Times New Roman'; font-size: 12px;"
        "  border: 1px solid #C0C8D8; gridline-color: #D8DEE8; }"
        "QTableWidget::item { padding: 5px 10px; }"
        "QTableWidget::item:alternate { background-color: #F2F5FA; }"
        "QTableWidget::item:selected { background-color: #2F5496; color: white; }"
        + section_rules
    )

    for i, hdr in enumerate(col_headers):
        item = QTableWidgetItem(hdr)
        item.setTextAlignment(Qt.AlignCenter)
        f = QFont("Times New Roman", 11)
        f.setBold(True)
        item.setFont(f)
        tbl.setHorizontalHeaderItem(i, item)
    return tbl


def _insert_result_row(
    tbl: QTableWidget,
    values: list[str],
    highlight: bool = False,
    fallback_cols: Optional[list[int]] = None,
) -> None:
    """Append a row to a result table.

    Args:
        tbl:           Target table widget.
        values:        Cell text for each column.
        highlight:     If True, paint the entire row with the highlight colour.
        fallback_cols: Column indices to paint with fallback (yellow) colour.
    """
    row = tbl.rowCount()
    tbl.insertRow(row)
    fallback_cols = fallback_cols or []
    for col, val in enumerate(values):
        item = QTableWidgetItem(val)
        item.setTextAlignment(Qt.AlignCenter)
        f = item.font()
        if highlight:
            # Use light tint + bold — avoids conflicting with Qt selection highlight
            item.setBackground(QColor(_HIGHLIGHT_BG))
            item.setForeground(QColor(_HIGHLIGHT_FG))
            f.setBold(True)
            item.setFont(f)
        elif col in fallback_cols:
            item.setBackground(QColor(_FALLBACK_BG))
        elif row % 2 == 1:
            item.setBackground(QColor(_ROW_ALT_BG))
        tbl.setItem(row, col, item)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("liqinglq666-NMR-Analyzer  v1.0")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        self._analysis:      Optional[AnalysisResult] = None
        self._peak_result:   Optional[PeakResult]     = None
        self._file_path:     Optional[Path]           = None
        self._thread:        Optional[QThread]        = None
        self._batch_worker:  Optional[BatchWorker]    = None
        self._amp_columns:   list[str]                = []
        self._batch_results: list[tuple[AnalysisResult, PeakResult]] = []
        self._psd_idx:       int                      = 0

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

        # ── Toolbar ───────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(46)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(4, 4, 4, 4)
        tb.setSpacing(6)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a data file…")
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
        self._btn_export.setToolTip("Export all results to a multi-sheet Excel workbook")
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
            "Bin Summation: recommended for log-spaced instrument data\n"
            "Log-domain: mathematically rigorous\n"
            "Linear ⚠: may over-estimate large pores on log-spaced axes"
        )
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tb.addWidget(self._mode_combo)

        # Warning label shown only for Linear mode
        self._warn_lbl = QLabel("⚠ Note: Linear integration may over-estimate large pores on log-spaced axes.")
        self._warn_lbl.setStyleSheet(
            "color: #B85C00; font-family:'Times New Roman'; font-size:10px;"
            "background:#FFF3CD; border:1px solid #FFBE7A; border-radius:3px; padding:2px 6px;"
        )
        self._warn_lbl.setVisible(False)
        tb.addWidget(self._warn_lbl)

        root.addWidget(toolbar)

        # ── Thin progress bar ─────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # ── Splitter: charts (top) + result tables (bottom) ───────────
        splitter = QSplitter(Qt.Vertical)

        # Chart tabs
        self._chart_tabs = QTabWidget()

        # — Bar chart tab —
        bar_wrap = QWidget()
        bar_lay  = QVBoxLayout(bar_wrap)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        self._bar_canvas = PlotCanvas(mode="bar")
        bar_lay.addWidget(self._bar_canvas)
        self._chart_tabs.addTab(bar_wrap, "System A / B Bar Charts")

        # — PSD tab with inline sample selector —
        psd_wrap = QWidget()
        psd_vlay = QVBoxLayout(psd_wrap)
        psd_vlay.setContentsMargins(4, 4, 4, 0)
        psd_vlay.setSpacing(4)

        psd_ctrl = QHBoxLayout()
        psd_ctrl.setSpacing(6)
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
        # _ALL_SAMPLES_IDX sentinel stored as attribute
        self._ALL_SAMPLES = "── All Samples ──"

        self._psd_canvas = PlotCanvas(mode="psd")
        psd_vlay.addWidget(self._psd_canvas, stretch=1)
        self._chart_tabs.addTab(psd_wrap, "Pore Size Distribution")

        splitter.addWidget(self._chart_tabs)

        # Result table area
        tbl_area = QWidget()
        tbl_vlay = QVBoxLayout(tbl_area)
        tbl_vlay.setContentsMargins(4, 4, 4, 4)
        tbl_vlay.setSpacing(4)

        # Copy button – above table tabs
        copy_bar = QHBoxLayout()
        copy_bar.addStretch()
        self._btn_copy = QPushButton("📋  复制表格")
        self._btn_copy.setObjectName("copyBtn")
        self._btn_copy.setFixedSize(120, 28)
        self._btn_copy.setToolTip("Copy current table to clipboard (tab-separated)")
        self._btn_copy.clicked.connect(self._on_copy_table)
        copy_bar.addWidget(self._btn_copy)
        tbl_vlay.addLayout(copy_bar)

        tbl_hlay = QHBoxLayout()

        self._tbl_tabs = QTabWidget()
        self._tbl_tabs.setDocumentMode(True)

        # System A
        self._tbl_a = _make_result_table(
            ["Mixture", "Gel pores", "Transition pores", "Capillary pores", "Air-voids"],
            [_HDR_MIXTURE_COL] + _SYS_A_COLOURS,
        )
        self._tbl_tabs.addTab(self._tbl_a, "System A — Physical Morphology")

        # System B
        self._tbl_b = _make_result_table(
            ["Mixture", "Harmless pores", "Less-harmful pores", "Harmful pores", "More-harmful pores"],
            [_HDR_MIXTURE_COL] + _SYS_B_COLOURS,
        )
        self._tbl_tabs.addTab(self._tbl_b, "System B — Damage Potential")

        # Peak Analysis
        _peak_hdrs = [
            "Mixture",
            "Primary T₂ (ms)", "Primary r (nm)", "Primary Area%",
            "Secondary T₂ (ms)", "Secondary r (nm)", "Secondary Area%",
            "Valley T₂ (ms)", "Valley r (nm)", "Fallback?",
        ]
        _peak_colours = (
            [_HDR_MIXTURE_COL]
            + [_SYS_A_COLOURS[0]] * 3
            + [_SYS_A_COLOURS[2]] * 3
            + [_SYS_B_COLOURS[3]] * 3
        )
        self._tbl_peak = _make_result_table(_peak_hdrs, _peak_colours)
        self._tbl_tabs.addTab(self._tbl_peak, "Peak Analysis")

        tbl_hlay.addWidget(self._tbl_tabs, stretch=1)
        tbl_vlay.addLayout(tbl_hlay)
        splitter.addWidget(tbl_area)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 480])
        root.addWidget(splitter, stretch=1)

        # Status bar
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
        for act in (act_open, None, act_quit):
            if act is None:
                file_menu.addSeparator()
            else:
                file_menu.addAction(act)

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
            QPushButton:hover   {{ background-color: {c[0]}; color: #222; }}
            QPushButton:pressed {{ background-color: #5A8DB8; }}
            QPushButton:disabled {{ background-color: #C8C8C8; color: #888; }}
            QPushButton#copyBtn {{
                background-color: #2F5496;
                font-size: 11px;
                padding: 3px 8px;
            }}
            QPushButton#copyBtn:hover {{ background-color: {c[3]}; }}
            QLineEdit {{
                background-color: white;
                border: 1px solid #C0C0C0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
            }}
            QComboBox {{
                background-color: white;
                border: 1px solid #C0C0C0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 11px;
            }}
            QTabWidget::pane {{
                border: 1px solid #D0D0D0;
                background: white;
            }}
            QTabBar::tab {{
                font-family: 'Times New Roman';
                font-size: 12px;
                padding: 6px 16px;
                background: #E0E5EF;
                border: 1px solid #C0C8D8;
                border-bottom: none;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: #2F5496;
                color: white;
                font-weight: bold;
            }}
            QTableWidget::item:selected {{
                background-color: #3A6BC4;
                color: white;
            }}
            QTabBar::tab:hover:!selected {{ background: {c[0]}; color: #222; }}
            QProgressBar {{
                background-color: #E0E0E0;
                border: none;
            }}
            QProgressBar::chunk {{ background-color: {c[3]}; }}
            QStatusBar {{
                font-family: 'Times New Roman';
                font-size: 11px;
                color: #444;
            }}
        """)

    # ------------------------------------------------------------------
    # Slots — file & analysis
    # ------------------------------------------------------------------

    @Slot()
    def _on_browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open NMR Data File", str(Path.home()),
            "Data files (*.xlsx *.xls *.csv);;All files (*)",
        )
        if not path_str:
            return

        self._file_path = Path(path_str)
        self._path_edit.setText(str(self._file_path))

        try:
            cols = get_amplitude_columns(self._file_path)
        except Exception as exc:
            QMessageBox.warning(self, "Column Detection", str(exc))
            return

        self._amp_columns = cols
        n = len(cols)
        self._statusbar.showMessage(
            f"Loaded: {self._file_path.name}  "
            f"({n} sample column{'s' if n > 1 else ''})  — analysing…"
        )

        # Auto-trigger batch analysis for all columns
        self._run_batch()

    def _current_mode(self) -> IntegrationMode:
        """Return the IntegrationMode matching the current ComboBox selection."""
        return _INTEGRATION_MODES[self._mode_combo.currentIndex()]

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        """Show warning for Linear mode and re-run analysis if data is loaded."""
        self._warn_lbl.setVisible(index == 2)
        if self._file_path is not None and self._amp_columns:
            self._run_batch()

    def _run_batch(self) -> None:
        """Start batch analysis for all amplitude columns."""
        if self._file_path is None or not self._amp_columns:
            return
        self._batch_results = []
        self._set_busy(True)

        self._thread = QThread(self)
        batch_worker = BatchWorker(
            self._file_path, list(self._amp_columns), self._current_mode()
        )
        batch_worker.moveToThread(self._thread)
        self._batch_worker = batch_worker  # prevent GC

        self._thread.started.connect(batch_worker.run)
        batch_worker.progress.connect(self._progress.setValue)
        batch_worker.col_done.connect(self._on_batch_col_done)
        batch_worker.finished.connect(self._on_batch_finished)
        batch_worker.error.connect(self._on_analysis_error)
        batch_worker.finished.connect(self._thread.quit)
        batch_worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(lambda: self._set_busy(False))
        self._thread.start()

    @Slot(str, object, object)
    def _on_batch_col_done(
        self, col: str, analysis: AnalysisResult, peak_result: PeakResult
    ) -> None:
        self._statusbar.showMessage(f"Processed: {col}")
        self._batch_results.append((analysis, peak_result))
        self._bar_canvas.plot_bar_charts(self._batch_results)
        # PSD shows the latest column while batch is in progress
        self._analysis    = analysis
        self._peak_result = peak_result
        self._psd_idx = len(self._batch_results) - 1
        self._psd_canvas.plot(
            analysis, peak_result,
            show_peaks=True, show_valley=True, show_classification=True,
        )

    @Slot(list)
    def _on_batch_finished(
        self, results: list[tuple[AnalysisResult, PeakResult]]
    ) -> None:
        self._batch_results = results
        self._bar_canvas.plot_bar_charts(results)
        self._populate_psd_combo()
        self._populate_summary_tables(results)
        self._btn_export.setEnabled(True)
        n = len(results)
        self._statusbar.showMessage(
            f"Analysis complete — {n} column{'s' if n > 1 else ''} processed."
        )

    @Slot(str)
    def _on_analysis_error(self, msg: str) -> None:
        self._set_busy(False)
        self._statusbar.showMessage("Error during analysis.")
        QMessageBox.critical(self, "Analysis Error", msg)

    # ------------------------------------------------------------------
    # PSD column selector (inside PSD tab)
    # ------------------------------------------------------------------

    def _populate_psd_combo(self) -> None:
        """Rebuild the PSD sample selector from current batch results."""
        self._psd_col_combo.blockSignals(True)
        self._psd_col_combo.clear()
        self._psd_col_combo.addItem(self._ALL_SAMPLES)  # index 0 = all
        for analysis, _ in self._batch_results:
            self._psd_col_combo.addItem(analysis.raw.sample_name)
        self._psd_col_combo.setCurrentIndex(0)  # default: show all
        self._psd_idx = -1
        self._psd_col_combo.blockSignals(False)
        self._show_all_psd()

    def _show_all_psd(self) -> None:
        """Plot all samples overlaid on the PSD canvas."""
        self._psd_canvas.plot_multi(
            self._batch_results,
            show_peaks=False, show_valley=False, show_classification=True,
        )

    @Slot(int)
    def _on_psd_col_changed(self, idx: int) -> None:
        # idx 0 = All Samples; idx k = batch_results[k-1]
        if idx == 0:
            self._psd_idx = -1
            self._show_all_psd()
            return
        real_idx = idx - 1
        if real_idx < 0 or real_idx >= len(self._batch_results):
            return
        self._psd_idx = real_idx
        analysis, peak_result = self._batch_results[real_idx]
        self._analysis    = analysis
        self._peak_result = peak_result
        self._psd_canvas.plot(
            analysis, peak_result,
            show_peaks=True, show_valley=True, show_classification=True,
        )

    # ------------------------------------------------------------------
    # Slots — export & misc
    # ------------------------------------------------------------------

    @Slot()
    def _on_export_excel(self) -> None:
        if not self._batch_results:
            QMessageBox.information(self, "No Data", "Open a file first.")
            return

        default_name = self._file_path.stem + "_results.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Results",
            str(Path.home() / default_name),
            "Excel (*.xlsx)",
        )
        if not save_path:
            return

        try:
            batch_dict = {
                an.raw.sample_name: (an, pk)
                for an, pk in self._batch_results
            }
            out = export_batch_results(Path(save_path), batch_dict)
            QMessageBox.information(
                self, "Export Complete",
                f"All {len(self._batch_results)} samples exported to:\n{out}"
            )
            self._statusbar.showMessage(f"Exported → {out.name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Error", str(exc))

    @Slot()
    def _on_save_figure(self) -> None:
        if self._analysis is None:
            QMessageBox.information(self, "No Data", "Open a file first.")
            return
        default_name = self._analysis.raw.source_path.stem + "_pore_distribution.png"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Pore Distribution Figure",
            str(Path.home() / default_name),
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if path_str:
            self._psd_canvas.save_figure(path_str)
            self._statusbar.showMessage(f"Figure saved → {Path(path_str).name}")

    @Slot()
    def _on_copy_table(self) -> None:
        """Copy the currently visible result table to the clipboard."""
        idx = self._tbl_tabs.currentIndex()
        tbl = [self._tbl_a, self._tbl_b, self._tbl_peak][idx]
        lines: list[str] = []
        headers = [
            tbl.horizontalHeaderItem(c).text()
            for c in range(tbl.columnCount())
        ]
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
            "About liqinglq666-NMR-Analyzer",
            "<b>liqinglq666-NMR-Analyzer v1.0</b><br>"
            "Fibre-reinforced concrete pore-structure analysis<br>"
            "via LF-NMR T2 relaxation data.<br><br>"
            "Dual classification: System A (physical) &amp; System B (hazard).<br>"
            "Peak detection with valley-based splitting.<br><br>"
            "2024 - Research Tool",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        """Toggle busy state: disable Browse while running, show progress bar.

        Args:
            busy: True when analysis is in progress.
        """
        self._btn_browse.setEnabled(not busy)
        self._progress.setVisible(busy)
        if busy:
            self._progress.setValue(0)

    def _populate_summary_tables(
        self,
        results: list[tuple[AnalysisResult, PeakResult]],
    ) -> None:
        """Fill System A, System B and Peak Analysis tables.

        Args:
            results: List of (AnalysisResult, PeakResult) tuples, one per sample.
        """
        self._tbl_a.setRowCount(0)
        self._tbl_b.setRowCount(0)
        self._tbl_peak.setRowCount(0)

        last_idx = len(results) - 1
        for idx, (analysis, peak_result) in enumerate(results):
            highlight = (idx == last_idx and len(results) > 1)
            name = analysis.raw.sample_name

            # System A
            sys_a = analysis.system_a
            row_a = [name] + [f"{r * 100:.2f} %" for r in sys_a.ratios]
            _insert_result_row(self._tbl_a, row_a, highlight=highlight)

            # System B
            sys_b = analysis.system_b
            row_b = [name] + [f"{r * 100:.2f} %" for r in sys_b.ratios]
            _insert_result_row(self._tbl_b, row_b, highlight=highlight)

            # Peak Analysis
            pri = peak_result.primary
            if peak_result.has_secondary and peak_result.secondary is not None:
                sec = peak_result.secondary
                val = peak_result.valley
                sec_t2  = f"{sec.t2_ms:.3f}"
                sec_r   = f"{sec.radius_nm:.1f}"
                sec_pct = f"{sec.area_ratio * 100:.2f} %"
                if val is not None:
                    v_t2     = f"{val.t2_ms:.3f}"
                    v_r      = f"{val.radius_nm:.1f}"
                    v_fb     = "Yes" if val.is_fallback else "No"
                    fb_cols  = [7, 8, 9] if (val.is_fallback and not highlight) else []
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
            _insert_result_row(
                self._tbl_peak, row_pk,
                highlight=highlight,
                fallback_cols=fb_cols,
            )
