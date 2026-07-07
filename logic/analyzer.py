"""
Core computational engine for NMR pore-structure analysis.

Responsibilities
----------------
- Robust ingestion of .xlsx / .csv files with fuzzy column matching.
- Data cleaning and validation (remove NaN, negatives, monotonicity check).
- T₂-to-radius conversion.
- Bin-summation integration for both classification systems.
- Cumulative porosity computation.

All heavy operations are pure functions returning immutable results so they
can be safely called from a QThread without shared-state issues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from logic.config import (
    AMPLITUDE_COLUMN_ALIASES,
    IntegrationMode,
    RADIUS_FACTOR,
    SYSTEM_A,
    SYSTEM_B,
    TIME_COLUMN_ALIASES,
)


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawData:
    """Validated, cleaned NMR measurement vectors.

    Attributes:
        t2_ms: T₂ relaxation times in milliseconds (ascending).
        amplitude: Differential amplitude values (same length as t2_ms).
        source_path: Original file path for traceability.
        sample_name: Derived from the file stem.
    """
    t2_ms: np.ndarray
    amplitude: np.ndarray
    source_path: Path
    sample_name: str


@dataclass(frozen=True)
class ClassificationResult:
    """Bin-summation results for one classification system.

    Attributes:
        system_name: "A" or "B".
        labels: Category names in threshold order.
        counts: Number of bins in each category.
        sums: Sum of amplitudes in each category.
        ratios: Fractional porosity for each category (sums / total).
    """
    system_name: str
    labels: list[str]
    counts: np.ndarray
    sums: np.ndarray
    ratios: np.ndarray


@dataclass(frozen=True)
class AnalysisResult:
    """Complete analysis output for one sample.

    Attributes:
        raw: Cleaned source data.
        radius_nm: Pore radius in nanometres (same length as raw.t2_ms).
        cumulative: Normalised cumulative porosity [0, 1].
        system_a: Classification by physical pore type.
        system_b: Classification by hazard level.
        total_amplitude: Scalar sum of all amplitude bins.
    """
    raw: RawData
    radius_nm: np.ndarray
    cumulative: np.ndarray
    system_a: ClassificationResult
    system_b: ClassificationResult
    total_amplitude: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_col(name: str) -> str:
    """Strip whitespace, punctuation and lower-case a column header."""
    return re.sub(r"[\s\W_]+", "", name).lower()


def _fuzzy_find_column(
    df: pd.DataFrame,
    aliases: list[str],
    label: str,
) -> str:
    """Return the first DataFrame column that matches any alias.

    Args:
        df: Input DataFrame.
        aliases: Candidate normalised names.
        label: Human-readable description used in error messages.

    Returns:
        Matched column name (original casing).

    Raises:
        ValueError: If no matching column is found.
    """
    normalised = {_normalise_col(c): c for c in df.columns}
    for alias in aliases:
        key = _normalise_col(alias)
        if key in normalised:
            return normalised[key]
    available = list(df.columns)
    raise ValueError(
        f"Cannot locate '{label}' column.\n"
        f"Tried aliases: {aliases}\n"
        f"Available columns: {available}"
    )


def _integrate_segment(
    t2_seg: np.ndarray,
    amp_seg: np.ndarray,
    mode: IntegrationMode,
) -> float:
    """Compute the integrated area for one T₂ segment.

    Args:
        t2_seg:  T₂ values for the segment (must have ≥1 point).
        amp_seg: Corresponding amplitude values.
        mode:    Integration method.

    Returns:
        Scalar area value (units depend on mode).
    """
    if len(t2_seg) == 0:
        return 0.0
    if mode is IntegrationMode.BIN_SUMMATION:
        return float(amp_seg.sum())
    # Choose trapezoid function compatible with installed NumPy version
    try:
        trapezoid = np.trapezoid  # NumPy >= 2.0
    except AttributeError:
        trapezoid = np.trapz      # NumPy < 2.0
    if mode is IntegrationMode.LOG_TRAPEZOIDAL:
        return float(trapezoid(amp_seg, np.log10(t2_seg)))
    # LINEAR_TRAPEZOIDAL
    return float(trapezoid(amp_seg, t2_seg))


def _bin_summation(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    thresholds: dict[str, tuple[float, float]],
    system_name: str,
    mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
) -> ClassificationResult:
    """Compute pore-fraction distribution for one classification system.

    The integration method is controlled by *mode*:

    * ``BIN_SUMMATION``      — direct amplitude sum (default, recommended for
      log-spaced NMR inversion data where ΔT₂ weighting is implicit).
    * ``LOG_TRAPEZOIDAL``    — ∫ A · d(log₁₀ T₂), mathematically rigorous on
      a logarithmic axis.
    * ``LINEAR_TRAPEZOIDAL`` — standard ∫ A dT₂, suitable only for linearly
      spaced data.

    Args:
        t2_ms:       Sorted T₂ array in ms.
        amplitude:   Differential amplitude array.
        thresholds:  Ordered dict mapping label → (lo_ms, hi_ms).
        system_name: "A" or "B" for bookkeeping.
        mode:        Integration method (default: BIN_SUMMATION).

    Returns:
        ClassificationResult with counts, sums and ratios.
    """
    labels: list[str] = []
    counts: list[int] = []
    sums:   list[float] = []

    for label, (lo, hi) in thresholds.items():
        mask = (t2_ms >= lo) & (t2_ms < hi)
        labels.append(label)
        counts.append(int(mask.sum()))
        sums.append(_integrate_segment(t2_ms[mask], amplitude[mask], mode))

    sums_arr   = np.array(sums,   dtype=np.float64)
    counts_arr = np.array(counts, dtype=np.int64)
    # For log/linear trap, values may be tiny or negative in edge cases;
    # take absolute values before normalising to keep ratios physical.
    pos_sums = np.abs(sums_arr)
    total    = pos_sums.sum()
    ratios   = pos_sums / total if total > 0 else np.zeros_like(sums_arr)

    return ClassificationResult(
        system_name=system_name,
        labels=labels,
        counts=counts_arr,
        sums=sums_arr,
        ratios=ratios,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _read_file(file_path: Path) -> pd.DataFrame:
    """Read an Excel or CSV file into a DataFrame.

    Args:
        file_path: Path to the data file.

    Returns:
        Raw DataFrame.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file format is unsupported.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path, engine="openpyxl")
    elif suffix == ".csv":
        return pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported file format: '{suffix}'. Use .xlsx or .csv")


def get_amplitude_columns(file_path: Path) -> list[str]:
    """Return all non-time column names in the file.

    Useful for multi-sample files where each column represents a specimen.

    Args:
        file_path: Path to the data file (.xlsx / .csv).

    Returns:
        List of column names that are NOT the T₂ time column.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If no T₂ column or no amplitude columns are found.
    """
    df = _read_file(file_path)
    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T₂ time")
    candidates = [c for c in df.columns if c != t2_col]
    if not candidates:
        raise ValueError("No amplitude columns found after excluding the T₂ column.")
    return candidates


def load_raw_data(
    file_path: Path,
    column: Optional[str] = None,
) -> RawData:
    """Load and validate NMR data from an Excel or CSV file.

    The function performs fuzzy column matching, drops non-positive rows,
    and guarantees the returned arrays are sorted by T₂ in ascending order.

    Args:
        file_path: Absolute or relative path to the data file (.xlsx / .csv).
        column: Explicit amplitude column name to use.  When *None* the
            function falls back to fuzzy alias matching against
            ``AMPLITUDE_COLUMN_ALIASES``.  Pass a column name obtained from
            :func:`get_amplitude_columns` to handle multi-sample files.

    Returns:
        RawData with clean, sorted numeric arrays.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If required columns cannot be found or data is unusable.
    """
    file_path = Path(file_path)
    df = _read_file(file_path)

    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T₂ time")

    if column is not None:
        if column not in df.columns:
            raise ValueError(
                f"Specified column '{column}' not found.\n"
                f"Available columns: {list(df.columns)}"
            )
        amp_col = column
    else:
        amp_col = _fuzzy_find_column(df, AMPLITUDE_COLUMN_ALIASES, "Amplitude")

    sub = df[[t2_col, amp_col]].copy()
    sub.columns = ["t2", "amp"]
    sub = sub.apply(pd.to_numeric, errors="coerce").dropna()
    sub = sub[(sub["t2"] > 0) & (sub["amp"] > 0)].reset_index(drop=True)

    if len(sub) < 3:
        raise ValueError(
            f"Insufficient valid data rows ({len(sub)}) after cleaning. "
            "Check that T₂ and Amplitude columns contain positive numeric values."
        )

    sub = sub.sort_values("t2").reset_index(drop=True)

    # Use column name as sample name for multi-sample files
    sample_name = column if column is not None else file_path.stem

    return RawData(
        t2_ms=sub["t2"].to_numpy(dtype=np.float64),
        amplitude=sub["amp"].to_numpy(dtype=np.float64),
        source_path=file_path,
        sample_name=sample_name,
    )


def compute_radius(t2_ms: np.ndarray) -> np.ndarray:
    """Convert T₂ relaxation times to pore radii.

    Uses the calibration anchor T₂ = 4.2 ms ↔ r = 100 nm.

    Args:
        t2_ms: Array of T₂ values in milliseconds.

    Returns:
        Array of pore radii in nanometres.
    """
    return RADIUS_FACTOR * t2_ms


def compute_cumulative(amplitude: np.ndarray) -> np.ndarray:
    """Compute normalised cumulative porosity distribution.

    Args:
        amplitude: Differential amplitude array (positive, sorted by T₂).

    Returns:
        Normalised cumulative sum in [0, 1].
    """
    cum = np.cumsum(amplitude)
    total = cum[-1]
    return cum / total if total > 0 else cum


def analyse(
    file_path: Path,
    column: Optional[str] = None,
    mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
) -> AnalysisResult:
    """Full analysis pipeline for one NMR data file.

    Orchestrates loading → cleaning → conversion → integration.

    Args:
        file_path: Path to the .xlsx or .csv data file.
        column:    Explicit amplitude column name.  Pass *None* to use fuzzy
                   alias matching (single-column files), or a column name from
                   :func:`get_amplitude_columns` for multi-sample files.
        mode:      Integration method.  Defaults to
                   :attr:`IntegrationMode.BIN_SUMMATION` which is appropriate
                   for log-spaced NMR inversion output.

    Returns:
        AnalysisResult containing all derived quantities.

    Raises:
        FileNotFoundError: Propagated from load_raw_data.
        ValueError: Propagated from load_raw_data or classification.
    """
    raw        = load_raw_data(file_path, column=column)
    radius_nm  = compute_radius(raw.t2_ms)
    cumulative = compute_cumulative(raw.amplitude)

    system_a = _bin_summation(raw.t2_ms, raw.amplitude, SYSTEM_A, "A", mode)
    system_b = _bin_summation(raw.t2_ms, raw.amplitude, SYSTEM_B, "B", mode)

    return AnalysisResult(
        raw=raw,
        radius_nm=radius_nm,
        cumulative=cumulative,
        system_a=system_a,
        system_b=system_b,
        total_amplitude=float(raw.amplitude.sum()),
    )
