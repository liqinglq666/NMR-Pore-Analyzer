"""
Configuration manager for NMR-Pore-Analyzer.

All physical thresholds, conversion factors, and styling constants are
centralised here. Modify this file to recalibrate the analysis without
touching any algorithmic code.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class IntegrationMode(Enum):
    """Integration method used for pore fraction calculation.

    Attributes:
        BIN_SUMMATION: Direct amplitude summation. Recommended for log-spaced
            NMR inversion output (e.g. Suzhou Niumag instruments) where each
            amplitude point already encodes the ΔT₂ bin weight.
        LOG_TRAPEZOIDAL: Trapezoidal integration over the log₁₀(T₂) axis,
            i.e. ∫ A · d(log₁₀ T₂).  Mathematically rigorous for log-spaced
            data and consistent with area-under-curve on a log-axis plot.
        LINEAR_TRAPEZOIDAL: Standard ∫ A dT₂ trapezoidal integration on the
            raw (linear) T₂ axis.  Correct only when data are equally spaced
            on a linear axis; tends to over-weight large-pore bins on
            log-spaced data.
    """

    BIN_SUMMATION      = "bin"
    LOG_TRAPEZOIDAL    = "log_trap"
    LINEAR_TRAPEZOIDAL = "linear_trap"

# ---------------------------------------------------------------------------
# T₂-to-radius conversion
# Anchor: T₂ = 4.2 ms  ↔  r = 100 nm
# r (nm) = RADIUS_FACTOR × T₂ (ms)
# ---------------------------------------------------------------------------
RADIUS_FACTOR: Final[float] = 100.0 / 4.2   # ≈ 23.81 nm/ms


# ---------------------------------------------------------------------------
# Pore classification thresholds  (T₂ in ms)
# ---------------------------------------------------------------------------

#: System A – Physical classification
SYSTEM_A: Final[dict[str, tuple[float, float]]] = {
    "Gel":        (0.0,    0.42),
    "Transition": (0.42,   4.2),
    "Capillary":  (4.2,   41.7),
    "Air-voids":  (41.7, float("inf")),
}

#: System B – Hazard / Damage classification
SYSTEM_B: Final[dict[str, tuple[float, float]]] = {
    "Harmless":     (0.0,    0.83),
    "Less-harmful": (0.83,   2.08),
    "Harmful":      (2.08,  8.33),
    "More-harmful": (8.33, float("inf")),
}


# ---------------------------------------------------------------------------
# Peak detection windows  (T₂ in ms)
# ---------------------------------------------------------------------------
PEAK_PRIMARY_WINDOW:   Final[tuple[float, float]] = (0.0,    10.0)
PEAK_SECONDARY_WINDOW: Final[tuple[float, float]] = (10.0, 1000.0)

#: Fallback valley position when no true local minimum exists between peaks
VALLEY_FALLBACK_MS: Final[float] = 10.0


# ---------------------------------------------------------------------------
# Plot / export styling
# ---------------------------------------------------------------------------
MORANDI_PALETTE: Final[list[str]] = [
    "#8ECFC9",   # teal
    "#FFBE7A",   # amber
    "#FA7F6F",   # coral
    "#82B0D2",   # steel-blue
]

PLOT_FONT_FAMILY: Final[str]  = "Times New Roman"
EXPORT_DPI:       Final[int]  = 600
FIGURE_SIZE:      Final[tuple[float, float]] = (8.0, 5.0)


# ---------------------------------------------------------------------------
# Data ingestion
# ---------------------------------------------------------------------------

#: Candidate column names recognised as the T₂ time axis (case-insensitive)
TIME_COLUMN_ALIASES: Final[list[str]] = [
    "time", "t2", "t_2", "t2(ms)", "time(ms)", "ms", "relaxation time",
]

#: Candidate column names recognised as the amplitude axis (case-insensitive)
AMPLITUDE_COLUMN_ALIASES: Final[list[str]] = [
    "amplitude", "amp", "intensity", "signal", "a", "dv/dr", "incremental",
]
