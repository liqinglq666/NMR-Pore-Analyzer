"""
Encapsulated Matplotlib canvas for NMR pore-size distribution plotting.

Provides a dual-Y-axis scientific figure:
  - Left  Y : Differential amplitude (bar/line).
  - Right Y : Cumulative porosity ratio (line + markers).
  - X-axis  : Pore radius (nm) in Log₁₀ scale.

The canvas is a QWidget subclass and can be embedded directly in any
PySide6 layout.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from logic.config import (
    EXPORT_DPI,
    FIGURE_SIZE,
    MORANDI_PALETTE,
    PLOT_FONT_FAMILY,
    RADIUS_FACTOR,
    classification_boundaries_ms,
)
from logic.analyzer import AnalysisResult
from logic.peak_processor import PeakResult


# ---------------------------------------------------------------------------
# Canvas widget
# ---------------------------------------------------------------------------

class PlotCanvas(QWidget):
    """Self-contained Matplotlib canvas with navigation toolbar.

    Args:
        parent: Optional parent QWidget.
        mode: Canvas mode, either ``"psd"`` (pore-size distribution, default)
              or ``"bar"`` (stacked bar charts for batch results).
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        mode: str = "psd",
    ) -> None:
        super().__init__(parent)
        self._mode = mode

        self._fig = Figure(figsize=FIGURE_SIZE, dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._toolbar = NavToolbar(self._canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

    # ------------------------------------------------------------------
    # Public drawing API
    # ------------------------------------------------------------------

    def plot_bar_charts(self, results: list) -> None:
        """Render dual stacked-bar charts (System A & System B) for batch results.

        Each bar represents one sample.  The two sub-plots share the X-axis
        (sample names) and are stacked vertically inside the same figure.

        Args:
            results: List of ``(AnalysisResult, PeakResult)`` tuples returned
                     by the batch analyser.  May also be a flat list of
                     ``AnalysisResult`` objects — the method handles both.
        """
        self._fig.clear()

        if not results:
            self._canvas.draw()
            return

        # ---- Unpack ---------------------------------------------------------
        analyses = []
        for item in results:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                analyses.append(item[0])
            else:
                analyses.append(item)

        sample_names = [a.raw.sample_name for a in analyses]
        n = len(sample_names)
        x = np.arange(n)
        c = MORANDI_PALETTE  # 4 colours for 4 pore classes

        # ---- Build fraction arrays from ClassificationResult ---------------
        # system_a.ratios / system_b.ratios → shape (n_categories,)
        # We collect per-sample rows then transpose to (n_categories, n_samples)

        def _ratios_to_pct(cr) -> np.ndarray:
            """Convert normalised ClassificationResult ratios to percentages."""
            return cr.ratios * 100.0

        a_fracs = np.array([_ratios_to_pct(a.system_a) for a in analyses]).T  # (4, n)
        b_fracs = np.array([_ratios_to_pct(a.system_b) for a in analyses]).T

        # Labels come directly from ClassificationResult to stay in sync
        sys_a_labels = analyses[0].system_a.labels
        sys_b_labels = analyses[0].system_b.labels

        bar_width = max(0.35, min(0.6, 0.6 / max(n / 6, 1)))

        ax_a = self._fig.add_subplot(121)
        ax_b = self._fig.add_subplot(122)

        for ax, fracs, labels, title in (
            (ax_a, a_fracs, sys_a_labels, "System A — Physical Morphology"),
            (ax_b, b_fracs, sys_b_labels, "System B — Damage Potential"),
        ):
            bottoms = np.zeros(n)
            for i, (frac_row, label, color) in enumerate(
                zip(fracs, labels, c)
            ):
                ax.bar(
                    x, frac_row, bar_width,
                    bottom=bottoms,
                    color=color, label=label,
                    edgecolor="white", linewidth=0.5,
                )
                # Annotate segments > 8 %
                for xi, (bot, val) in enumerate(zip(bottoms, frac_row)):
                    if val >= 8:
                        ax.text(
                            xi, bot + val / 2,
                            f"{val:.1f}%",
                            ha="center", va="center",
                            fontsize=7, fontfamily=PLOT_FONT_FAMILY,
                            color="white",
                        )
                bottoms += frac_row

            ax.set_ylabel("Proportion (%)", fontfamily=PLOT_FONT_FAMILY, fontsize=10)
            ax.set_ylim(0, 110)
            ax.set_title(title, fontfamily=PLOT_FONT_FAMILY, fontsize=11, pad=6)
            ax.legend(
                loc="upper right", fontsize=8,
                prop={"family": PLOT_FONT_FAMILY},
                framealpha=0.85,
            )
            for tick_lbl in ax.get_yticklabels():
                tick_lbl.set_fontfamily(PLOT_FONT_FAMILY)
                tick_lbl.set_fontsize(9)

        for ax in (ax_a, ax_b):
            ax.set_xticks(x)
            ax.set_xticklabels(
                sample_names, rotation=30, ha="right",
                fontfamily=PLOT_FONT_FAMILY, fontsize=9,
            )

        self._fig.tight_layout()
        self._canvas.draw()

    def plot(
        self,
        analysis: AnalysisResult,
        peak_result: PeakResult,
        *,
        show_peaks: bool = True,
        show_valley: bool = True,
        show_classification: bool = True,
    ) -> None:
        """Render the dual-Y-axis pore distribution figure.

        Args:
            analysis: Full analysis result.
            peak_result: Peak detection result.
            show_peaks: Annotate peak positions with vertical markers.
            show_valley: Annotate valley position.
            show_classification: Draw vertical classification boundary lines.
        """
        self._fig.clear()
        ax_left: Axes  = self._fig.add_subplot(111)
        ax_right: Axes = ax_left.twinx()

        r   = analysis.radius_nm
        amp = analysis.raw.amplitude
        cum = analysis.cumulative

        c = MORANDI_PALETTE

        # --- Differential distribution (left Y) ---
        ax_left.plot(
            r, amp,
            color=c[0], linewidth=1.8, label="Differential distribution",
            zorder=3,
        )
        ax_left.fill_between(r, amp, alpha=0.25, color=c[0])

        # --- Cumulative ratio (right Y) ---
        ax_right.plot(
            r, cum,
            color=c[1], linewidth=1.6,
            linestyle="--", marker="o", markersize=2.5,
            label="Cumulative ratio", zorder=3,
        )

        # --- Peak and valley annotations ---
        if show_peaks:
            pk = peak_result
            pri_r = pk.primary.radius_nm
            ax_left.axvline(
                pri_r, color=c[2], linewidth=1.2, linestyle=":",
                label=f"Primary peak  T₂={pk.primary.t2_ms:.2f} ms",
            )
            ax_left.annotate(
                f"P1\n{pk.primary.t2_ms:.2f} ms",
                xy=(pri_r, pk.primary.amplitude),
                xytext=(pri_r * 1.3, pk.primary.amplitude * 0.9),
                fontsize=7, fontfamily=PLOT_FONT_FAMILY, color=c[2],
                arrowprops=dict(arrowstyle="->", color=c[2], lw=0.8),
            )
            if pk.has_secondary and pk.secondary is not None:
                sec_r = pk.secondary.radius_nm
                ax_left.axvline(
                    sec_r, color=c[3], linewidth=1.2, linestyle=":",
                    label=f"Secondary peak  T₂={pk.secondary.t2_ms:.2f} ms",
                )
                ax_left.annotate(
                    f"P2\n{pk.secondary.t2_ms:.2f} ms",
                    xy=(sec_r, pk.secondary.amplitude),
                    xytext=(sec_r * 0.6, pk.secondary.amplitude * 0.9),
                    fontsize=7, fontfamily=PLOT_FONT_FAMILY, color=c[3],
                    arrowprops=dict(arrowstyle="->", color=c[3], lw=0.8),
                )

                if show_valley and pk.valley is not None:
                    v_r = pk.valley.radius_nm
                    lbl = ("Valley (fallback)" if pk.valley.is_fallback
                           else f"Valley  T₂={pk.valley.t2_ms:.2f} ms")
                    ax_left.axvline(
                        v_r, color="gray", linewidth=1.0,
                        linestyle="-.", alpha=0.7, label=lbl,
                    )

        # --- Classification boundaries ---
        if show_classification:
            for ms in classification_boundaries_ms():
                ax_left.axvline(
                    RADIUS_FACTOR * ms,
                    color="silver", linewidth=0.7, linestyle="--",
                    alpha=0.55, zorder=1,
                )

        # --- Axes formatting ---
        ax_left.set_xscale("log")
        ax_left.set_xlabel(
            "Pore Radius $r$ (nm)",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12,
        )
        ax_left.set_ylabel(
            "Differential Porosity (a.u.)",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=c[0],
        )
        ax_right.set_ylabel(
            "Cumulative Porosity Ratio",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=c[1],
        )
        ax_right.set_ylim(0, 1.05)

        for ax in (ax_left, ax_right):
            for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
                tick_label.set_fontfamily(PLOT_FONT_FAMILY)
                tick_label.set_fontsize(10)

        # --- Title ---
        ax_left.set_title(
            f"NMR T₂ Pore-Size Distribution — {analysis.raw.sample_name}",
            fontfamily=PLOT_FONT_FAMILY, fontsize=13, pad=10,
        )

        # --- Combined legend ---
        lines_l, labels_l = ax_left.get_legend_handles_labels()
        lines_r, labels_r = ax_right.get_legend_handles_labels()
        ax_left.legend(
            lines_l + lines_r, labels_l + labels_r,
            loc="upper left", fontsize=8,
            prop={"family": PLOT_FONT_FAMILY},
            framealpha=0.85,
        )

        self._fig.tight_layout()
        self._canvas.draw()

    def plot_multi(
        self,
        results: list,
        *,
        show_peaks: bool = False,
        show_valley: bool = False,
        show_classification: bool = True,
    ) -> None:
        """Overlay all samples' differential + cumulative curves on one figure.

        Args:
            results: List of (AnalysisResult, PeakResult) tuples.
            show_peaks: Annotate peak positions (not recommended when overlaying).
            show_valley: Annotate valley positions.
            show_classification: Draw System A/B boundary lines.
        """
        self._fig.clear()
        if not results:
            self._canvas.draw()
            return

        ax_left: Axes  = self._fig.add_subplot(111)
        ax_right: Axes = ax_left.twinx()

        c = MORANDI_PALETTE
        # Use a slightly expanded colour cycle for many samples
        _MULTI_COLORS = [
            "#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2",
            "#A8D8B9", "#F0A58F", "#B8A4CC", "#F5C87A",
        ]
        _LINESTYLES = ["-", "--", "-.", ":"]

        for i, item in enumerate(results):
            an = item[0] if isinstance(item, (list, tuple)) else item
            col = _MULTI_COLORS[i % len(_MULTI_COLORS)]
            ls  = _LINESTYLES[i % len(_LINESTYLES)]
            r   = an.radius_nm
            amp = an.raw.amplitude
            cum = an.cumulative
            name = an.raw.sample_name

            ax_left.plot(
                r, amp,
                color=col, linewidth=1.6,
                linestyle=ls, label=name,
                zorder=3,
            )
            ax_right.plot(
                r, cum,
                color=col, linewidth=1.2,
                linestyle=ls, marker="", alpha=0.7,
                zorder=2,
            )

        # Classification boundaries
        if show_classification:
            for ms in classification_boundaries_ms():
                ax_left.axvline(
                    RADIUS_FACTOR * ms,
                    color="silver", linewidth=0.7,
                    linestyle="--", alpha=0.55, zorder=1,
                )

        ax_left.set_xscale("log")
        ax_left.set_xlabel(
            "Pore Radius $r$ (nm)",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12,
        )
        ax_left.set_ylabel(
            "Differential Porosity (a.u.)",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=c[0],
        )
        ax_right.set_ylabel(
            "Cumulative Porosity Ratio",
            fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=c[1],
        )
        ax_right.set_ylim(0, 1.05)

        for ax in (ax_left, ax_right):
            for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
                tick_label.set_fontfamily(PLOT_FONT_FAMILY)
                tick_label.set_fontsize(10)

        ax_left.set_title(
            "NMR T₂ Pore-Size Distribution — All Samples",
            fontfamily=PLOT_FONT_FAMILY, fontsize=13, pad=10,
        )
        ax_left.legend(
            loc="upper left", fontsize=8,
            prop={"family": PLOT_FONT_FAMILY},
            framealpha=0.85,
        )

        self._fig.tight_layout()
        self._canvas.draw()

    def clear(self) -> None:
        """Clear the figure and redraw an empty canvas."""
        self._fig.clear()
        self._canvas.draw()

    def save_figure(self, path: str) -> None:
        """Export the current figure to a file.

        Args:
            path: Destination file path.  Format inferred from extension.
        """
        self._fig.savefig(path, dpi=EXPORT_DPI, bbox_inches="tight")
