"""
Configuration manager for NMR-Pore-Analyzer.

All physical thresholds, conversion factors, aliases and styling constants are
centralised here. Modify this file to recalibrate the analysis without touching
algorithmic code.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


APP_NAME: Final[str] = "NMR-Pore-Analyzer"
APP_VERSION: Final[str] = "2.1.0"
ORGANIZATION_NAME: Final[str] = "Research Lab"


class IntegrationMode(Enum):
    """Integration method used for pore fraction calculation.

    Attributes:
        BIN_SUMMATION: Direct amplitude summation. Recommended for log-spaced
            NMR inversion output where each amplitude point already encodes a
            discrete T2-bin contribution.
        LOG_TRAPEZOIDAL: Trapezoidal integration over the log10(T2) axis after
            clipping/interpolating class boundaries.
        LINEAR_TRAPEZOIDAL: Standard trapezoidal integration over the raw T2
            axis after clipping/interpolating class boundaries. Correct only
            when the spectrum is sampled on a linear T2 axis.
    """

    BIN_SUMMATION = "bin"
    LOG_TRAPEZOIDAL = "log_trap"
    LINEAR_TRAPEZOIDAL = "linear_trap"


# ---------------------------------------------------------------------------
# T2-to-radius conversion
# Anchor: T2 = 4.2 ms  <->  r = 100 nm
# r (nm) = RADIUS_FACTOR x T2 (ms)
# ---------------------------------------------------------------------------
RADIUS_FACTOR: Final[float] = 100.0 / 4.2  # approx. 23.81 nm/ms


# ---------------------------------------------------------------------------
# Pore classification thresholds  (T2 in ms)
# ---------------------------------------------------------------------------

#: System A - Physical classification
SYSTEM_A: Final[dict[str, tuple[float, float]]] = {
    "Gel": (0.0, 0.42),
    "Transition": (0.42, 4.2),
    "Capillary": (4.2, 41.7),
    "Air-voids": (41.7, float("inf")),
}

#: System B - Hazard / damage classification
SYSTEM_B: Final[dict[str, tuple[float, float]]] = {
    "Harmless": (0.0, 0.83),
    "Less-harmful": (0.83, 2.08),
    "Harmful": (2.08, 8.33),
    "More-harmful": (8.33, float("inf")),
}


def classification_boundaries_ms() -> list[float]:
    """Return all unique finite class boundaries in T2 milliseconds."""
    boundaries = {
        edge
        for system in (SYSTEM_A, SYSTEM_B)
        for lo_hi in system.values()
        for edge in lo_hi
        if 0.0 < edge < float("inf")
    }
    return sorted(boundaries)


# ---------------------------------------------------------------------------
# Peak detection windows  (T2 in ms)
# ---------------------------------------------------------------------------
# Primary peak:    [0, 10) ms
# Secondary peak:  (10, 1000] ms
PEAK_PRIMARY_WINDOW: Final[tuple[float, float]] = (0.0, 10.0)
PEAK_SECONDARY_WINDOW: Final[tuple[float, float]] = (10.0, 1000.0)

#: Fallback valley position when no strict local minimum exists between peaks
VALLEY_FALLBACK_MS: Final[float] = 10.0


# ---------------------------------------------------------------------------
# Plot / export styling
# ---------------------------------------------------------------------------
MORANDI_PALETTE: Final[list[str]] = [
    "#8ECFC9",  # teal
    "#FFBE7A",  # amber
    "#FA7F6F",  # coral
    "#82B0D2",  # steel-blue
]

PLOT_FONT_FAMILY: Final[str] = "Times New Roman"
EXPORT_DPI: Final[int] = 600
FIGURE_SIZE: Final[tuple[float, float]] = (8.0, 5.0)


# ---------------------------------------------------------------------------
# Data ingestion
# ---------------------------------------------------------------------------

#: Candidate column names recognised as the T2 time axis (case-insensitive).
#: These are normalised before matching, so variants like ``T2 (ms)`` and
#: ``T₂(ms)`` are also covered.
TIME_COLUMN_ALIASES: Final[list[str]] = [
    "time",
    "t2",
    "t_2",
    "t2(ms)",
    "t2/ms",
    "time(ms)",
    "ms",
    "relaxation time",
    "relaxation time(ms)",
    "t₂",
    "t₂(ms)",
    "弛豫时间",
    "弛豫时间/ms",
    "横向弛豫时间",
    "t2弛豫时间",
]

#: Candidate column names recognised as the amplitude/signal axis
#: (case-insensitive).
AMPLITUDE_COLUMN_ALIASES: Final[list[str]] = [
    "amplitude",
    "amp",
    "intensity",
    "signal",
    "a",
    "dv/dr",
    "incremental",
    "incremental porosity",
    "signal amplitude",
    "幅值",
    "信号幅值",
    "信号强度",
    "强度",
    "孔隙度",
    "增量孔隙度",
    "分量孔隙度",
]
