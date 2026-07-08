"""
Core computational engine for NMR pore-structure analysis.

Responsibilities
----------------
- Robust ingestion of .xlsx / .xls / .csv files with fuzzy column matching.
- Data cleaning and validation.
- T2-to-radius conversion.
- Pore classification with bin summation or boundary-aware trapezoidal modes.
- Cumulative porosity computation.
"""

from __future__ import annotations

import math
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
    """Validated, cleaned NMR measurement vectors."""

    t2_ms: np.ndarray
    amplitude: np.ndarray
    source_path: Path
    sample_name: str


@dataclass(frozen=True)
class ClassificationResult:
    """Integration results for one pore classification system."""

    system_name: str
    labels: list[str]
    counts: np.ndarray
    sums: np.ndarray
    ratios: np.ndarray


@dataclass(frozen=True)
class AnalysisResult:
    """Complete analysis output for one sample."""

    raw: RawData
    radius_nm: np.ndarray
    cumulative: np.ndarray
    system_a: ClassificationResult
    system_b: ClassificationResult
    total_amplitude: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SUBSCRIPT_MAP = str.maketrans({
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
})


def _normalise_col(name: object) -> str:
    """Strip whitespace/punctuation, convert subscript digits and lower-case."""
    text = str(name).translate(_SUBSCRIPT_MAP).lower()
    text = text.replace("／", "/").replace("（", "(").replace("）", ")")
    return re.sub(r"[\s\W_]+", "", text)


def _fuzzy_find_column(
    df: pd.DataFrame,
    aliases: list[str],
    label: str,
) -> str:
    """Return the first DataFrame column that matches any alias."""
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


def _coerce_mode(mode: IntegrationMode | str) -> IntegrationMode:
    """Accept IntegrationMode or its value/name and return IntegrationMode."""
    if isinstance(mode, IntegrationMode):
        return mode
    try:
        return IntegrationMode(mode)
    except ValueError:
        try:
            return IntegrationMode[str(mode)]
        except KeyError as exc:
            valid = ", ".join(m.value for m in IntegrationMode)
            raise ValueError(f"Unsupported integration mode '{mode}'. Valid: {valid}") from exc


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    """NumPy-version-safe trapezoidal integration."""
    try:
        return float(np.trapezoid(y, x))  # NumPy >= 2.0
    except AttributeError:
        return float(np.trapz(y, x))      # NumPy < 2.0


def _integrate_segment(
    t2_seg: np.ndarray,
    amp_seg: np.ndarray,
    mode: IntegrationMode,
) -> float:
    """Compute the integrated area for one explicit T2 segment."""
    if len(t2_seg) == 0:
        return 0.0
    if mode is IntegrationMode.BIN_SUMMATION:
        return float(amp_seg.sum())
    if len(t2_seg) < 2:
        return 0.0
    if mode is IntegrationMode.LOG_TRAPEZOIDAL:
        return _trapezoid(amp_seg, np.log10(t2_seg))
    return _trapezoid(amp_seg, t2_seg)


def _clip_curve_to_interval(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    lo: float,
    hi: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Clip a spectrum to [lo, hi] with linear interpolation at boundaries.

    This is used only by trapezoidal integration modes. It avoids area loss when
    a classification threshold falls between two measured T2 points.
    """
    if len(t2_ms) < 2:
        return np.array([], dtype=float), np.array([], dtype=float)

    finite_hi = math.isfinite(hi)
    lower = max(float(lo), float(t2_ms[0]))
    upper = min(float(hi) if finite_hi else float(t2_ms[-1]), float(t2_ms[-1]))
    if upper <= lower:
        return np.array([], dtype=float), np.array([], dtype=float)

    interior_mask = (t2_ms > lower) & (t2_ms < upper)
    xs = [lower]
    ys = [float(np.interp(lower, t2_ms, amplitude))]

    if interior_mask.any():
        xs.extend(t2_ms[interior_mask].astype(float).tolist())
        ys.extend(amplitude[interior_mask].astype(float).tolist())

    xs.append(upper)
    ys.append(float(np.interp(upper, t2_ms, amplitude)))

    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def _integrate_interval(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    lo: float,
    hi: float,
    mode: IntegrationMode,
) -> float:
    """Integrate one pore-class interval.

    Bin summation keeps the instrument-bin semantics. Trapezoidal modes treat the
    spectrum as a continuous curve and interpolate exact class boundaries.
    """
    if mode is IntegrationMode.BIN_SUMMATION:
        mask = (t2_ms >= lo) & (t2_ms < hi)
        return _integrate_segment(t2_ms[mask], amplitude[mask], mode)

    x_clip, y_clip = _clip_curve_to_interval(t2_ms, amplitude, lo, hi)
    return _integrate_segment(x_clip, y_clip, mode)


def _classify(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    thresholds: dict[str, tuple[float, float]],
    system_name: str,
    mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
) -> ClassificationResult:
    """Compute pore-fraction distribution for one classification system."""
    mode = _coerce_mode(mode)
    labels: list[str] = []
    counts: list[int] = []
    sums: list[float] = []

    for label, (lo, hi) in thresholds.items():
        mask = (t2_ms >= lo) & (t2_ms < hi)
        labels.append(label)
        counts.append(int(mask.sum()))
        sums.append(_integrate_interval(t2_ms, amplitude, lo, hi, mode))

    sums_arr = np.array(sums, dtype=np.float64)
    counts_arr = np.array(counts, dtype=np.int64)
    pos_sums = np.abs(sums_arr)
    total = float(pos_sums.sum())
    ratios = pos_sums / total if total > 0 else np.zeros_like(sums_arr)

    return ClassificationResult(
        system_name=system_name,
        labels=labels,
        counts=counts_arr,
        sums=sums_arr,
        ratios=ratios,
    )


# Backwards-compatible private name used by older code/tests.
_bin_summation = _classify


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _read_file(file_path: Path) -> pd.DataFrame:
    """Read an Excel or CSV file into a DataFrame."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        return pd.read_excel(file_path, engine="openpyxl")
    if suffix == ".xls":
        try:
            return pd.read_excel(file_path, engine="xlrd")
        except ImportError as exc:
            raise ImportError(
                "Reading legacy .xls files requires xlrd. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc
    if suffix == ".csv":
        try:
            return pd.read_csv(file_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(file_path, encoding="gbk")

    raise ValueError(f"Unsupported file format: '{suffix}'. Use .xlsx, .xls or .csv")


def get_amplitude_columns(file_path: Path) -> list[str]:
    """Return all non-time column names in the file."""
    df = _read_file(file_path)
    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T2 time")
    candidates = [c for c in df.columns if c != t2_col]
    if not candidates:
        raise ValueError("No amplitude columns found after excluding the T2 column.")
    return candidates


def load_raw_data(
    file_path: Path,
    column: Optional[str] = None,
) -> RawData:
    """Load and validate NMR data from an Excel or CSV file."""
    file_path = Path(file_path)
    df = _read_file(file_path)

    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T2 time")

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
            "Check that T2 and Amplitude columns contain positive numeric values."
        )

    sub = sub.sort_values("t2").reset_index(drop=True)

    # Merge duplicate T2 bins by summing their positive amplitudes. This prevents
    # zero-width intervals from breaking log/linear integration.
    sub = sub.groupby("t2", as_index=False, sort=True)["amp"].sum()
    if len(sub) < 3:
        raise ValueError(
            "Insufficient unique positive T2 bins after merging duplicates. "
            "At least three unique T2 values are required."
        )

    sample_name = str(column) if column is not None else file_path.stem

    return RawData(
        t2_ms=sub["t2"].to_numpy(dtype=np.float64),
        amplitude=sub["amp"].to_numpy(dtype=np.float64),
        source_path=file_path,
        sample_name=sample_name,
    )


def compute_radius(t2_ms: np.ndarray) -> np.ndarray:
    """Convert T2 relaxation times to pore radii in nanometres."""
    return RADIUS_FACTOR * np.asarray(t2_ms, dtype=np.float64)


def compute_cumulative(amplitude: np.ndarray) -> np.ndarray:
    """Compute normalised cumulative porosity distribution."""
    amplitude = np.asarray(amplitude, dtype=np.float64)
    if len(amplitude) == 0:
        return np.array([], dtype=np.float64)
    cum = np.cumsum(amplitude)
    total = float(cum[-1])
    return cum / total if total > 0 else np.zeros_like(cum)


def analyse(
    file_path: Path,
    column: Optional[str] = None,
    mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
) -> AnalysisResult:
    """Full analysis pipeline for one NMR data file / amplitude column."""
    mode = _coerce_mode(mode)
    raw = load_raw_data(file_path, column=column)
    radius_nm = compute_radius(raw.t2_ms)
    cumulative = compute_cumulative(raw.amplitude)

    system_a = _classify(raw.t2_ms, raw.amplitude, SYSTEM_A, "A", mode)
    system_b = _classify(raw.t2_ms, raw.amplitude, SYSTEM_B, "B", mode)

    return AnalysisResult(
        raw=raw,
        radius_nm=radius_nm,
        cumulative=cumulative,
        system_a=system_a,
        system_b=system_b,
        total_amplitude=float(raw.amplitude.sum()),
    )
