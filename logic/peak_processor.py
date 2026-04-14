"""
Peak detection and characterisation for NMR T₂ distributions.

Algorithm
---------
1. Primary peak  – global maximum inside  T₂ ∈ [0, 10] ms.
2. Secondary peak – local maximum inside  T₂ ∈ (10, 1000] ms with the
                    highest amplitude (dominant secondary lobe).
3. Valley        – absolute minimum between the two peak positions.
                   If no strict local minimum exists the valley degenerates
                   to T₂ = 10 ms (``ValleyInfo.is_fallback = True``).
4. Area proportions computed via **Bin Summation** (physical accuracy on
   log-spaced NMR inversion grids).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import argrelmin

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
    """Characterisation of one spectral peak.

    Attributes:
        t2_ms: Peak position in milliseconds.
        radius_nm: Corresponding pore radius in nanometres.
        amplitude: Peak amplitude value.
        area: Bin-summation area for this peak's domain.
        area_ratio: Fraction of total amplitude belonging to this peak.
        label: Human-readable label ("Primary" / "Secondary").
    """
    t2_ms:      float
    radius_nm:  float
    amplitude:  float
    area:       float
    area_ratio: float
    label:      str


@dataclass(frozen=True)
class ValleyInfo:
    """Valley (minimum) separating the primary and secondary peaks.

    Attributes:
        t2_ms: Valley position in milliseconds.
        radius_nm: Corresponding pore radius in nanometres.
        amplitude: Amplitude at the valley.
        is_fallback: True when no true local minimum was found and the
                     canonical fallback value (10 ms) is used instead.
    """
    t2_ms:       float
    radius_nm:   float
    amplitude:   float
    is_fallback: bool


@dataclass(frozen=True)
class PeakResult:
    """Complete peak analysis output for one sample.

    Attributes:
        primary: Primary (low-T₂) peak information.
        secondary: Secondary (high-T₂) peak information, or None if absent.
        valley: Valley between the two peaks, or None if secondary is absent.
        has_secondary: Convenience flag – True when a secondary peak exists.
    """
    primary:       PeakInfo
    secondary:     PeakInfo | None
    valley:        ValleyInfo | None
    has_secondary: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _window_indices(
    t2_ms: np.ndarray,
    lo: float,
    hi: float,
) -> np.ndarray:
    """Return boolean mask for elements inside [lo, hi)."""
    return (t2_ms >= lo) & (t2_ms < hi)


def _find_dominant_local_max(
    amplitude: np.ndarray,
    mask: np.ndarray,
) -> int | None:
    """Find the index (global) of the highest local maximum inside *mask*.

    Uses ``scipy.signal.argrelmin`` on the inverted signal so that we detect
    true local maxima (not just the boundary maximum).

    Args:
        amplitude: Full amplitude array.
        mask: Boolean mask selecting the search window.

    Returns:
        Global index of the dominant local maximum, or None.
    """
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return None

    local_amp = amplitude[indices]
    # argrelmin on -amplitude ≡ argrelmax on amplitude
    rel_max_local, = argrelmin(-local_amp, order=1)

    if len(rel_max_local) == 0:
        # No interior extremum – fall back to global max of the window
        return int(indices[np.argmax(local_amp)])

    # Pick the local max with the highest amplitude
    best_local = rel_max_local[np.argmax(local_amp[rel_max_local])]
    return int(indices[best_local])


def _bin_area(
    amplitude: np.ndarray,
    mask: np.ndarray,
) -> float:
    """Bin-summation area: sum of amplitudes inside *mask*."""
    return float(amplitude[mask].sum())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_peaks(
    t2_ms: np.ndarray,
    amplitude: np.ndarray,
) -> PeakResult:
    """Identify primary/secondary peaks and the intervening valley.

    Args:
        t2_ms: T₂ array in milliseconds (sorted ascending).
        amplitude: Differential amplitude array (same length).

    Returns:
        PeakResult with full peak and valley characterisation.

    Raises:
        ValueError: If the primary peak window contains no data.
    """
    total_amp = float(amplitude.sum())
    if total_amp <= 0:
        raise ValueError("Amplitude array is empty or all-zero.")

    lo_p, hi_p = PEAK_PRIMARY_WINDOW
    lo_s, hi_s = PEAK_SECONDARY_WINDOW

    # ------------------------------------------------------------------
    # Primary peak – global maximum in [0, 10) ms
    # ------------------------------------------------------------------
    primary_mask = _window_indices(t2_ms, lo_p, hi_p)
    if not primary_mask.any():
        raise ValueError(
            f"No data points found in the primary peak window "
            f"[{lo_p}, {hi_p}) ms. Check your T₂ range."
        )

    pri_idx = int(np.argmax(amplitude * primary_mask))
    pri_t2  = float(t2_ms[pri_idx])
    pri_amp = float(amplitude[pri_idx])

    # ------------------------------------------------------------------
    # Secondary peak – dominant local maximum in (10, 1000] ms
    # ------------------------------------------------------------------
    sec_mask = _window_indices(t2_ms, lo_s, hi_s)
    has_secondary = sec_mask.any()
    secondary: PeakInfo | None = None
    valley:    ValleyInfo | None = None

    if has_secondary:
        sec_idx_candidate = _find_dominant_local_max(amplitude, sec_mask)
        if sec_idx_candidate is None:
            has_secondary = False
        else:
            sec_idx = sec_idx_candidate
            sec_t2  = float(t2_ms[sec_idx])
            sec_amp = float(amplitude[sec_idx])

            # --------------------------------------------------------------
            # Valley – minimum between pri_idx and sec_idx
            # --------------------------------------------------------------
            left  = min(pri_idx, sec_idx)
            right = max(pri_idx, sec_idx)
            between_mask = np.zeros(len(t2_ms), dtype=bool)
            between_mask[left : right + 1] = True
            # Exclude the peaks themselves
            between_mask[pri_idx] = False
            between_mask[sec_idx] = False

            is_fallback = not between_mask.any()

            if is_fallback:
                # No bins between peaks → use fallback T₂
                fallback_t2 = VALLEY_FALLBACK_MS
                fb_idx = int(np.argmin(np.abs(t2_ms - fallback_t2)))
                valley = ValleyInfo(
                    t2_ms=fallback_t2,
                    radius_nm=RADIUS_FACTOR * fallback_t2,
                    amplitude=float(amplitude[fb_idx]),
                    is_fallback=True,
                )
                split_t2 = fallback_t2
            else:
                v_local_idx = int(np.argmin(amplitude[between_mask]))
                v_global_idx = int(np.where(between_mask)[0][v_local_idx])
                v_t2  = float(t2_ms[v_global_idx])
                v_amp = float(amplitude[v_global_idx])
                valley = ValleyInfo(
                    t2_ms=v_t2,
                    radius_nm=RADIUS_FACTOR * v_t2,
                    amplitude=v_amp,
                    is_fallback=False,
                )
                split_t2 = v_t2

            # --------------------------------------------------------------
            # Area proportions via Bin Summation
            # Domains: primary ← [0, split_t2); secondary ← [split_t2, ∞)
            # --------------------------------------------------------------
            pri_area_mask = t2_ms <  split_t2
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

    # ------------------------------------------------------------------
    # No secondary peak – entire amplitude belongs to primary
    # ------------------------------------------------------------------
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
