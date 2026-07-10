from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import argrelmax, argrelmin

from logic.config import (
    PEAK_PRIMARY_WINDOW,
    PEAK_SECONDARY_WINDOW,
    RADIUS_FACTOR,
    VALLEY_FALLBACK_MS,
)


@dataclass(frozen=True)
class PeakInfo:
    t2_ms: float
    radius_nm: float
    amplitude: float
    area: float
    area_ratio: float
    label: str


@dataclass(frozen=True)
class ValleyInfo:
    t2_ms: float
    radius_nm: float
    amplitude: float
    is_fallback: bool


@dataclass(frozen=True)
class PeakResult:
    primary: PeakInfo
    secondary: PeakInfo | None
    valley: ValleyInfo | None
    has_secondary: bool


def _window_indices(
    t2_ms: np.ndarray,
    lo: float,
    hi: float,
    *,
    include_left: bool = True,
    include_right: bool = False,
) -> np.ndarray:
    left = t2_ms >= lo if include_left else t2_ms > lo
    right = t2_ms <= hi if include_right else t2_ms < hi
    return left & right


def _find_dominant_local_max(amplitude: np.ndarray, mask: np.ndarray) -> int | None:
    indices = np.where(mask)[0]
    if len(indices) < 3:
        return None

    local_amp = amplitude[indices]
    rel_max, = argrelmax(local_amp, order=1)
    if len(rel_max) == 0:
        return None
    return int(indices[rel_max[np.argmax(local_amp[rel_max])]])


def _fallback_valley(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    pri_idx: int | None = None,
    sec_idx: int | None = None,
) -> tuple[ValleyInfo, float]:
    candidates = np.arange(len(t2_ms))
    if pri_idx is not None and sec_idx is not None:
        left, right = sorted((pri_idx, sec_idx))
        between = candidates[(candidates > left) & (candidates < right)]
        if len(between):
            candidates = between

    nearest = candidates[np.argmin(np.abs(t2_ms[candidates] - VALLEY_FALLBACK_MS))]
    split_t2 = float(t2_ms[nearest])
    return (
        ValleyInfo(
            t2_ms=split_t2,
            radius_nm=RADIUS_FACTOR * split_t2,
            amplitude=float(amplitude[nearest]),
            is_fallback=True,
        ),
        split_t2,
    )


def _find_valley_between(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    pri_idx: int,
    sec_idx: int,
) -> tuple[ValleyInfo, float]:
    left, right = sorted((pri_idx, sec_idx))
    if right - left < 2:
        return _fallback_valley(t2_ms, amplitude, pri_idx, sec_idx)

    indices = np.arange(left, right + 1, dtype=int)
    rel_min, = argrelmin(amplitude[indices], order=1)
    valid = [int(indices[idx]) for idx in rel_min if left < int(indices[idx]) < right]
    if not valid:
        return _fallback_valley(t2_ms, amplitude, pri_idx, sec_idx)

    best_idx = min(valid, key=lambda idx: float(amplitude[idx]))
    valley_t2 = float(t2_ms[best_idx])
    return (
        ValleyInfo(
            t2_ms=valley_t2,
            radius_nm=RADIUS_FACTOR * valley_t2,
            amplitude=float(amplitude[best_idx]),
            is_fallback=False,
        ),
        valley_t2,
    )


def _as_clean_arrays(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    t2 = np.asarray(t2_ms, dtype=np.float64)
    amp = np.asarray(amplitude, dtype=np.float64)
    if t2.ndim != 1 or amp.ndim != 1 or len(t2) != len(amp):
        raise ValueError("T2 and amplitude must be one-dimensional arrays of equal length.")
    if len(t2) < 3:
        raise ValueError("At least three data points are required for peak detection.")
    if not np.isfinite(t2).all() or not np.isfinite(amp).all():
        raise ValueError("T2 and amplitude must contain finite values only.")
    if np.any(amp < 0):
        raise ValueError("Amplitude cannot be negative during peak detection.")
    order = np.argsort(t2)
    return t2[order], amp[order]


def detect_peaks(t2_ms: np.ndarray, amplitude: np.ndarray) -> PeakResult:
    t2_ms, amplitude = _as_clean_arrays(t2_ms, amplitude)
    total_amp = float(amplitude.sum())
    if total_amp <= 0:
        raise ValueError("Amplitude array is empty or all-zero.")

    lo_p, hi_p = PEAK_PRIMARY_WINDOW
    lo_s, hi_s = PEAK_SECONDARY_WINDOW
    primary_mask = _window_indices(t2_ms, lo_p, hi_p)
    if not primary_mask.any():
        raise ValueError(f"No data points found in the primary peak window [{lo_p}, {hi_p}) ms.")

    primary_indices = np.where(primary_mask)[0]
    pri_idx = int(primary_indices[np.argmax(amplitude[primary_indices])])
    pri_t2 = float(t2_ms[pri_idx])
    pri_amp = float(amplitude[pri_idx])

    sec_mask = _window_indices(t2_ms, lo_s, hi_s, include_left=False, include_right=True)
    sec_idx = _find_dominant_local_max(amplitude, sec_mask)
    if sec_idx is None:
        primary = PeakInfo(
            t2_ms=pri_t2,
            radius_nm=RADIUS_FACTOR * pri_t2,
            amplitude=pri_amp,
            area=total_amp,
            area_ratio=1.0,
            label="Primary",
        )
        return PeakResult(primary, None, None, False)

    valley, split_t2 = _find_valley_between(t2_ms, amplitude, pri_idx, sec_idx)
    pri_area = float(amplitude[t2_ms < split_t2].sum())
    sec_area = float(amplitude[t2_ms >= split_t2].sum())

    primary = PeakInfo(
        t2_ms=pri_t2,
        radius_nm=RADIUS_FACTOR * pri_t2,
        amplitude=pri_amp,
        area=pri_area,
        area_ratio=pri_area / total_amp,
        label="Primary",
    )
    sec_t2 = float(t2_ms[sec_idx])
    secondary = PeakInfo(
        t2_ms=sec_t2,
        radius_nm=RADIUS_FACTOR * sec_t2,
        amplitude=float(amplitude[sec_idx]),
        area=sec_area,
        area_ratio=sec_area / total_amp,
        label="Secondary",
    )
    return PeakResult(primary, secondary, valley, True)
