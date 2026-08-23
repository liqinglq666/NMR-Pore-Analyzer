"""
Encapsulated Matplotlib canvas for NMR pore-size distribution plotting.

Provides two plot modes:
- ``psd``: pore-size distribution and cumulative curve.
- ``bar``: stacked System A / System B classification bars.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from logic.analyzer import AnalysisResult
from logic.config import (
    EXPORT_DPI,
    FIGURE_SIZE,
    MORANDI_PALETTE,
    PLOT_FONT_FAMILY,
    RADIUS_FACTOR,
    classification_boundaries_ms,
)
from logic.peak_processor import PeakResult


class PlotCanvas(QWidget):
    """Self-contained Matplotlib canvas with navigation toolbar."""

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
    # Bar charts
    # ------------------------------------------------------------------
    def plot_bar_charts(self, results: list) -> None:
        """Render dual stacked-bar charts for batch results."""
        self._fig.clear()
        if not results:
            self._canvas.draw()
            return

        analyses = [item[0] if isinstance(item, (list, tuple)) else item for item in results]
        sample_names = [a.raw.sample_name for a in analyses]
        n = len(sample_names)
        x = np.arange(n)
        colors = MORANDI_PALETTE

        a_fracs = np.array([a.system_a.ratios * 100.0 for a in analyses]).T
        b_fracs = np.array([a.system_b.ratios * 100.0 for a in analyses]).T
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
            for frac_row, label, color in zip(fracs, labels, colors):
                ax.bar(
                    x,
                    frac_row,
                    bar_width,
                    bottom=bottoms,
                    color=color,
                    label=label,
                    edgecolor="white",
                    linewidth=0.5,
                )
                for xi, (bot, val) in enumerate(zip(bottoms, frac_row)):
                    if val >= 8:
                        ax.text(
                            xi,
                            bot + val / 2,
                            f"{val:.1f}%",
                            ha="center",
                            va="center",
                            fontsize=7,
                            fontfamily=PLOT_FONT_FAMILY,
                            color="white",
                        )
                bottoms += frac_row

            ax.set_ylabel("Proportion (%)", fontfamily=PLOT_FONT_FAMILY, fontsize=10)
            ax.set_ylim(0, 110)
            ax.set_title(title, fontfamily=PLOT_FONT_FAMILY, fontsize=11, pad=6)
            ax.legend(loc="upper right", fontsize=8, prop={"family": PLOT_FONT_FAMILY}, framealpha=0.85)
            self._format_ticks(ax)

        for ax in (ax_a, ax_b):
            ax.set_xticks(x)
            ax.set_xticklabels(sample_names, rotation=30, ha="right", fontfamily=PLOT_FONT_FAMILY, fontsize=9)

        self._fig.tight_layout()
        self._canvas.draw()

    # ------------------------------------------------------------------
    # Single PSD
    # ------------------------------------------------------------------
    def plot(
        self,
        analysis: AnalysisResult,
        peak_result: PeakResult,
        *,
        show_peaks: bool = True,
        show_valley: bool = True,
        show_classification: bool = True,
    ) -> None:
        """Render one pore distribution curve with cumulative ratio."""
        self._fig.clear()
        ax_left: Axes = self._fig.add_subplot(111)
        ax_right: Axes = ax_left.twinx()

        r = analysis.radius_nm
        amp = analysis.raw.amplitude
        cum = analysis.cumulative
        colors = MORANDI_PALETTE

        ax_left.plot(r, amp, color=colors[0], linewidth=1.8, label="Incremental signal", zorder=3)
        ax_left.fill_between(r, amp, alpha=0.25, color=colors[0])
        ax_right.plot(
            r,
            cum,
            color=colors[1],
            linewidth=1.6,
            linestyle="--",
            marker="o",
            markersize=2.5,
            label="Cumulative ratio",
            zorder=3,
        )

        if show_peaks:
            self._draw_peak_annotations(ax_left, peak_result, colors, show_valley)

        if show_classification:
            self._draw_classification_boundaries(ax_left)

        self._format_psd_axes(ax_left, ax_right)
        ax_left.set_title(
            f"NMR T2 Pore-Size Distribution — {analysis.raw.sample_name}",
            fontfamily=PLOT_FONT_FAMILY,
            fontsize=13,
            pad=10,
        )

        lines_l, labels_l = ax_left.get_legend_handles_labels()
        lines_r, labels_r = ax_right.get_legend_handles_labels()
        ax_left.legend(
            lines_l + lines_r,
            labels_l + labels_r,
            loc="upper left",
            fontsize=8,
            prop={"family": PLOT_FONT_FAMILY},
            framealpha=0.85,
        )

        self._fig.tight_layout()
        self._canvas.draw()

    # ------------------------------------------------------------------
    # Multi PSD
    # ------------------------------------------------------------------
    def plot_multi(
        self,
        results: list,
        *,
        show_peaks: bool = False,
        show_valley: bool = False,
        show_classification: bool = True,
    ) -> None:
        """Overlay all samples' incremental and cumulative curves."""
        self._fig.clear()
        if not results:
            self._canvas.draw()
            return

        ax_left: Axes = self._fig.add_subplot(111)
        ax_right: Axes = ax_left.twinx()
        colors = [
            "#8ECFC9", "#FFBE7A", "#FA7F6F", "#82B0D2",
            "#A8D8B9", "#F0A58F", "#B8A4CC", "#F5C87A",
        ]
        linestyles = ["-", "--", "-.", ":"]

        for i, item in enumerate(results):
            an = item[0] if isinstance(item, (list, tuple)) else item
            color = colors[i % len(colors)]
            ls = linestyles[i % len(linestyles)]
            ax_left.plot(
                an.radius_nm,
                an.raw.amplitude,
                color=color,
                linewidth=1.6,
                linestyle=ls,
                label=an.raw.sample_name,
                zorder=3,
            )
            ax_right.plot(
                an.radius_nm,
                an.cumulative,
                color=color,
                linewidth=1.2,
                linestyle=ls,
                marker="",
                alpha=0.7,
                zorder=2,
            )

        if show_classification:
            self._draw_classification_boundaries(ax_left)

        self._format_psd_axes(ax_left, ax_right)
        ax_left.set_title(
            "NMR T2 Pore-Size Distribution — All Samples",
            fontfamily=PLOT_FONT_FAMILY,
            fontsize=13,
            pad=10,
        )
        ax_left.legend(loc="upper left", fontsize=8, prop={"family": PLOT_FONT_FAMILY}, framealpha=0.85)

        self._fig.tight_layout()
        self._canvas.draw()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _draw_peak_annotations(
        self,
        ax_left: Axes,
        peak_result: PeakResult,
        colors: list[str],
        show_valley: bool,
    ) -> None:
        pk = peak_result
        pri_r = pk.primary.radius_nm
        ax_left.axvline(pri_r, color=colors[2], linewidth=1.2, linestyle=":", label=f"Primary peak  T2={pk.primary.t2_ms:.2f} ms")
        ax_left.annotate(
            f"P1\n{pk.primary.t2_ms:.2f} ms",
            xy=(pri_r, pk.primary.amplitude),
            xytext=(pri_r * 1.3, pk.primary.amplitude * 0.9),
            fontsize=7,
            fontfamily=PLOT_FONT_FAMILY,
            color=colors[2],
            arrowprops=dict(arrowstyle="->", color=colors[2], lw=0.8),
        )

        if pk.has_secondary and pk.secondary is not None:
            sec_r = pk.secondary.radius_nm
            ax_left.axvline(sec_r, color=colors[3], linewidth=1.2, linestyle=":", label=f"Secondary peak  T2={pk.secondary.t2_ms:.2f} ms")
            ax_left.annotate(
                f"P2\n{pk.secondary.t2_ms:.2f} ms",
                xy=(sec_r, pk.secondary.amplitude),
                xytext=(sec_r * 0.6, pk.secondary.amplitude * 0.9),
                fontsize=7,
                fontfamily=PLOT_FONT_FAMILY,
                color=colors[3],
                arrowprops=dict(arrowstyle="->", color=colors[3], lw=0.8),
            )

            if show_valley and pk.valley is not None:
                v_r = pk.valley.radius_nm
                label = "Valley (fallback)" if pk.valley.is_fallback else f"Valley  T2={pk.valley.t2_ms:.2f} ms"
                ax_left.axvline(v_r, color="gray", linewidth=1.0, linestyle="-.", alpha=0.7, label=label)

    def _draw_classification_boundaries(self, ax_left: Axes) -> None:
        for ms in classification_boundaries_ms():
            ax_left.axvline(
                RADIUS_FACTOR * ms,
                color="silver",
                linewidth=0.7,
                linestyle="--",
                alpha=0.55,
                zorder=1,
            )

    def _format_psd_axes(self, ax_left: Axes, ax_right: Axes) -> None:
        colors = MORANDI_PALETTE
        ax_left.set_xscale("log")
        ax_left.set_xlabel("Pore Radius $r$ (nm)", fontfamily=PLOT_FONT_FAMILY, fontsize=12)
        ax_left.set_ylabel("Incremental Signal (a.u.)", fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=colors[0])
        ax_right.set_ylabel("Cumulative Porosity Ratio", fontfamily=PLOT_FONT_FAMILY, fontsize=12, color=colors[1])
        ax_right.set_ylim(0, 1.05)
        self._format_ticks(ax_left)
        self._format_ticks(ax_right)

    def _format_ticks(self, ax: Axes) -> None:
        for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
            tick_label.set_fontfamily(PLOT_FONT_FAMILY)
            tick_label.set_fontsize(10)

    def clear(self) -> None:
        """Clear the figure and redraw an empty canvas."""
        self._fig.clear()
        self._canvas.draw()

    def save_figure(self, path: str) -> None:
        """Export the current figure to a file."""
        self._fig.savefig(path, dpi=EXPORT_DPI, bbox_inches="tight")
