"""
Peak detection and characterisation for NMR T2 distributions.

Algorithm
---------
1. Primary peak   - global maximum inside T2 in [0, 10) ms.
2. Secondary peak - strict local maximum inside T2 in (10, 1000] ms.
                    A monotonic tail is no longer forced into a secondary peak.
3. Valley         - strict local minimum between the two peaks.
                    If no strict local minimum exists, the valley degenerates
                    to T2 = 10 ms and is flagged as a fallback.
4. Area proportions are computed via bin summation, consistent with discrete
   inversion spectra.
"""

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


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PeakInfo:
    """Characterisation of one spectral peak."""

    t2_ms: float
    radius_nm: float
    amplitude: float
    area: float
    area_ratio: float
    label: str


@dataclass(frozen=True)
class ValleyInfo:
    """Valley/minimum separating the primary and secondary peaks."""

    t2_ms: float
    radius_nm: float
    amplitude: float
    is_fallback: bool


@dataclass(frozen=True)
class PeakResult:
    """Complete peak analysis output for one sample."""

    primary: PeakInfo
    secondary: PeakInfo | None
    valley: ValleyInfo | None
    has_secondary: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _window_indices(
    t2_ms: np.ndarray,
    lo: float,
    hi: float,
    *,
    include_left: bool = True,
    include_right: bool = False,
) -> np.ndarray:
    """Return boolean mask for a configurable T2 interval."""
    left = t2_ms >= lo if include_left else t2_ms > lo
    right = t2_ms <= hi if include_right else t2_ms < hi
    return left & right


def _find_dominant_local_max(
    amplitude: np.ndarray,
    mask: np.ndarray,
) -> int | None:
    """Find the global index of the highest strict local maximum inside mask.

    Returns None when the selected window has no interior local maximum. This is
    deliberate: a monotonic high-T2 tail should not be reported as a secondary
    peak.
    """
    indices = np.where(mask)[0]
    if len(indices) < 3:
        return None

    local_amp = amplitude[indices]
    rel_max_local, = argrelmax(local_amp, order=1)
    if len(rel_max_local) == 0:
        return None

    best_local = rel_max_local[np.argmax(local_amp[rel_max_local])]
    return int(indices[best_local])


def _find_valley_between(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
    pri_idx: int,
    sec_idx: int,
) -> tuple[ValleyInfo, float]:
    """Find a strict local minimum between two peaks, or return fallback."""
    left = min(pri_idx, sec_idx)
    right = max(pri_idx, sec_idx)
    candidate_indices = np.arange(left + 1, right, dtype=int)

    if len(candidate_indices) >= 3:
        local_amp = amplitude[candidate_indices]
        rel_min_local, = argrelmin(local_amp, order=1)
        if len(rel_min_local) > 0:
            best_local = rel_min_local[np.argmin(local_amp[rel_min_local])]
            v_idx = int(candidate_indices[best_local])
            v_t2 = float(t2_ms[v_idx])
            valley = ValleyInfo(
                t2_ms=v_t2,
                radius_nm=RADIUS_FACTOR * v_t2,
                amplitude=float(amplitude[v_idx]),
                is_fallback=False,
            )
            return valley, v_t2

    fallback_t2 = VALLEY_FALLBACK_MS
    fb_idx = int(np.argmin(np.abs(t2_ms - fallback_t2)))
    valley = ValleyInfo(
        t2_ms=fallback_t2,
        radius_nm=RADIUS_FACTOR * fallback_t2,
        amplitude=float(amplitude[fb_idx]),
        is_fallback=True,
    )
    return valley, fallback_t2


def _bin_area(amplitude: np.ndarray, mask: np.ndarray) -> float:
    """Bin-summation area: sum of amplitudes inside mask."""
    return float(amplitude[mask].sum())


def _as_clean_arrays(t2_ms: np.ndarray, amplitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate basic shape/sorting assumptions for peak detection."""
    t2 = np.asarray(t2_ms, dtype=np.float64)
    amp = np.asarray(amplitude, dtype=np.float64)
    if t2.ndim != 1 or amp.ndim != 1 or len(t2) != len(amp):
        raise ValueError("T2 and amplitude must be one-dimensional arrays of equal length.")
    if len(t2) < 3:
        raise ValueError("At least three data points are required for peak detection.")
    order = np.argsort(t2)
    return t2[order], amp[order]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_peaks(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
) -> PeakResult:
    """Identify primary/secondary peaks and the intervening valley."""
    t2_ms, amplitude = _as_clean_arrays(t2_ms, amplitude)
    total_amp = float(amplitude.sum())
    if total_amp <= 0:
        raise ValueError("Amplitude array is empty or all-zero.")

    lo_p, hi_p = PEAK_PRIMARY_WINDOW
    lo_s, hi_s = PEAK_SECONDARY_WINDOW

    # Primary peak - global maximum in [0, 10) ms
    primary_mask = _window_indices(t2_ms, lo_p, hi_p, include_left=True, include_right=False)
    if not primary_mask.any():
        raise ValueError(
            f"No data points found in the primary peak window [{lo_p}, {hi_p}) ms. "
            "Check your T2 range."
        )

    primary_indices = np.where(primary_mask)[0]
    pri_idx = int(primary_indices[np.argmax(amplitude[primary_indices])])
    pri_t2 = float(t2_ms[pri_idx])
    pri_amp = float(amplitude[pri_idx])

    # Secondary peak - strict local maximum in (10, 1000] ms
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
        return PeakResult(
            primary=primary,
            secondary=None,
            valley=None,
            has_secondary=False,
        )

    sec_t2 = float(t2_ms[sec_idx])
    sec_amp = float(amplitude[sec_idx])
    valley, split_t2 = _find_valley_between(t2_ms, amplitude, pri_idx, sec_idx)

    # Domains: primary <- [0, split_t2); secondary <- [split_t2, +inf)
    pri_area_mask = t2_ms < split_t2
    sec_area_mask = t2_ms >= split_t2
    pri_area = _bin_area(amplitude, pri_area_mask)
    sec_area = _bin_area(amplitude, sec_area_mask)

    primary = PeakInfo(
        t2_ms=pri_t2,
        radius_nm=RADIUS_FACTOR * pri_t2,
        amplitude=pri_amp,
        area=pri_area,
        area_ratio=pri_area / total_amp if total_amp > 0 else 0.0,
        label="Primary",
    )
    secondary = PeakInfo(
        t2_ms=sec_t2,
        radius_nm=RADIUS_FACTOR * sec_t2,
        amplitude=sec_amp,
        area=sec_area,
        area_ratio=sec_area / total_amp if total_amp > 0 else 0.0,
        label="Secondary",
    )

    return PeakResult(
        primary=primary,
        secondary=secondary,
        valley=valley,
        has_secondary=True,
    )
