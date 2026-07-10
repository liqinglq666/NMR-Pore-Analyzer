from __future__ import annotations

import math
import re
import warnings
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


@dataclass(frozen=True)
class RawData:
    t2_ms: np.ndarray
    amplitude: np.ndarray
    source_path: Path
    sample_name: str


@dataclass(frozen=True)
class ClassificationResult:
    system_name: str
    labels: list[str]
    counts: np.ndarray
    sums: np.ndarray
    ratios: np.ndarray


@dataclass(frozen=True)
class AnalysisResult:
    raw: RawData
    radius_nm: np.ndarray
    cumulative: np.ndarray
    system_a: ClassificationResult
    system_b: ClassificationResult
    total_amplitude: float


_SUBSCRIPT_MAP = str.maketrans({
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
})


def _normalise_col(name: object) -> str:
    text = str(name).translate(_SUBSCRIPT_MAP).lower()
    text = text.replace("／", "/").replace("（", "(").replace("）", ")")
    return re.sub(r"[\s\W_]+", "", text)


def _fuzzy_find_column(df: pd.DataFrame, aliases: list[str], label: str) -> str:
    normalised = {_normalise_col(column): column for column in df.columns}
    for alias in aliases:
        key = _normalise_col(alias)
        if key in normalised:
            return normalised[key]
    raise ValueError(
        f"Cannot locate '{label}' column. Tried aliases: {aliases}. "
        f"Available columns: {list(df.columns)}"
    )


def _coerce_mode(mode: IntegrationMode | str) -> IntegrationMode:
    if isinstance(mode, IntegrationMode):
        return mode
    try:
        return IntegrationMode(mode)
    except ValueError:
        try:
            return IntegrationMode[str(mode)]
        except KeyError as exc:
            valid = ", ".join(item.value for item in IntegrationMode)
            raise ValueError(f"Unsupported integration mode '{mode}'. Valid: {valid}") from exc


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    try:
        return float(np.trapezoid(y, x))
    except AttributeError:
        return float(np.trapz(y, x))


def _integrate_segment(
    t2_seg: np.ndarray,
    amp_seg: np.ndarray,
    mode: IntegrationMode,
) -> float:
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
    if len(t2_ms) < 2:
        return np.array([], dtype=float), np.array([], dtype=float)

    lower = max(float(lo), float(t2_ms[0]))
    upper = min(float(hi) if math.isfinite(hi) else float(t2_ms[-1]), float(t2_ms[-1]))
    if upper <= lower:
        return np.array([], dtype=float), np.array([], dtype=float)

    interior = (t2_ms > lower) & (t2_ms < upper)
    xs = [lower, *t2_ms[interior].astype(float).tolist(), upper]
    ys = [
        float(np.interp(lower, t2_ms, amplitude)),
        *amplitude[interior].astype(float).tolist(),
        float(np.interp(upper, t2_ms, amplitude)),
    ]
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def _integrate_interval(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    lo: float,
    hi: float,
    mode: IntegrationMode,
) -> float:
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
    mode = _coerce_mode(mode)
    labels: list[str] = []
    counts: list[int] = []
    sums: list[float] = []

    for label, (lo, hi) in thresholds.items():
        mask = (t2_ms >= lo) & (t2_ms < hi)
        labels.append(label)
        counts.append(int(mask.sum()))
        sums.append(_integrate_interval(t2_ms, amplitude, lo, hi, mode))

    sums_arr = np.asarray(sums, dtype=np.float64)
    counts_arr = np.asarray(counts, dtype=np.int64)
    total = float(sums_arr.sum())
    ratios = sums_arr / total if total > 0 else np.zeros_like(sums_arr)
    return ClassificationResult(system_name, labels, counts_arr, sums_arr, ratios)


_bin_summation = _classify


def _read_file(file_path: Path) -> pd.DataFrame:
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
            raise ImportError("Reading .xls files requires xlrd.") from exc
    if suffix == ".csv":
        try:
            return pd.read_csv(file_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(file_path, encoding="gb18030")
    raise ValueError(f"Unsupported file format: '{suffix}'. Use .xlsx, .xls or .csv")


def _numeric_candidate(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    return len(finite) >= 3 and float(np.clip(finite.to_numpy(dtype=float), 0.0, None).sum()) > 0


def get_amplitude_columns(file_path: Path) -> list[str]:
    df = _read_file(file_path)
    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T2 time")
    candidates = [
        column
        for column in df.columns
        if column != t2_col and _numeric_candidate(df[column])
    ]
    if not candidates:
        raise ValueError("No numeric amplitude columns found after excluding the T2 column.")
    return candidates


def load_raw_data(file_path: Path, column: Optional[str] = None) -> RawData:
    file_path = Path(file_path)
    df = _read_file(file_path)
    t2_col = _fuzzy_find_column(df, TIME_COLUMN_ALIASES, "T2 time")

    if column is not None:
        if column not in df.columns:
            raise ValueError(
                f"Specified column '{column}' not found. Available columns: {list(df.columns)}"
            )
        amp_col = column
    else:
        amp_col = _fuzzy_find_column(df, AMPLITUDE_COLUMN_ALIASES, "Amplitude")

    sub = df[[t2_col, amp_col]].copy()
    sub.columns = ["t2", "amp"]
    sub = sub.apply(pd.to_numeric, errors="coerce").dropna()
    sub = sub[sub["t2"] > 0].reset_index(drop=True)

    if len(sub) < 3:
        raise ValueError(f"Insufficient valid T2 rows ({len(sub)}) after cleaning.")

    negative_count = int((sub["amp"] < 0).sum())
    if negative_count:
        warnings.warn(
            f"{negative_count} negative amplitude value(s) were clipped to zero; T2 bins were kept.",
            RuntimeWarning,
            stacklevel=2,
        )
        sub["amp"] = sub["amp"].clip(lower=0.0)

    sub = sub.sort_values("t2").groupby("t2", as_index=False, sort=True)["amp"].sum()
    if len(sub) < 3:
        raise ValueError("At least three unique positive T2 bins are required.")
    if float(sub["amp"].sum()) <= 0:
        raise ValueError("Amplitude column is empty or all-zero after cleaning.")

    sample_name = str(column) if column is not None else file_path.stem
    return RawData(
        t2_ms=sub["t2"].to_numpy(dtype=np.float64),
        amplitude=sub["amp"].to_numpy(dtype=np.float64),
        source_path=file_path,
        sample_name=sample_name,
    )


def compute_radius(t2_ms: np.ndarray) -> np.ndarray:
    return RADIUS_FACTOR * np.asarray(t2_ms, dtype=np.float64)


def compute_cumulative(amplitude: np.ndarray) -> np.ndarray:
    amplitude = np.asarray(amplitude, dtype=np.float64)
    if len(amplitude) == 0:
        return np.array([], dtype=np.float64)
    cumulative = np.cumsum(amplitude)
    total = float(cumulative[-1])
    return cumulative / total if total > 0 else np.zeros_like(cumulative)


def analyse(
    file_path: Path,
    column: Optional[str] = None,
    mode: IntegrationMode = IntegrationMode.BIN_SUMMATION,
) -> AnalysisResult:
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
