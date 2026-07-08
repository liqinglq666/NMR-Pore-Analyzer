from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from logic.analyzer import analyse, get_amplitude_columns
from logic.config import IntegrationMode
from logic.peak_processor import detect_peaks


def test_multisample_xlsx_analysis(tmp_path: Path) -> None:
    file_path = tmp_path / "nmr.xlsx"
    df = pd.DataFrame(
        {
            "T₂(ms)": [0.1, 0.2, 1.0, 5.0, 20.0, 80.0],
            "A": [1, 4, 2, 1, 0.5, 0.2],
            "B": [2, 5, 3, 1, 0.4, 0.1],
        }
    )
    df.to_excel(file_path, index=False)

    cols = get_amplitude_columns(file_path)
    assert cols == ["A", "B"]

    result = analyse(file_path, column="A", mode=IntegrationMode.BIN_SUMMATION)
    assert result.raw.sample_name == "A"
    assert np.isclose(result.cumulative[-1], 1.0)
    assert np.isclose(result.system_a.ratios.sum(), 1.0)
    assert np.isclose(result.system_b.ratios.sum(), 1.0)


def test_monotonic_tail_is_not_secondary_peak() -> None:
    t2 = np.array([0.1, 0.2, 1.0, 5.0, 20.0, 80.0, 300.0], dtype=float)
    amp = np.array([1.0, 8.0, 5.0, 2.0, 1.0, 0.5, 0.2], dtype=float)

    peaks = detect_peaks(t2, amp)
    assert peaks.has_secondary is False
    assert peaks.secondary is None
    assert peaks.primary.area_ratio == 1.0


def test_true_secondary_peak_and_real_adjacent_valley() -> None:
    t2 = np.array([0.1, 0.2, 1.0, 5.0, 20.0, 80.0, 300.0], dtype=float)
    amp = np.array([1.0, 8.0, 4.0, 2.0, 1.0, 3.0, 0.5], dtype=float)

    peaks = detect_peaks(t2, amp)
    assert peaks.has_secondary is True
    assert peaks.secondary is not None
    assert peaks.valley is not None
    assert peaks.valley.is_fallback is False
    assert peaks.valley.t2_ms == 20.0


def test_true_secondary_peak_without_real_valley_uses_fallback() -> None:
    t2 = np.array([0.1, 0.2, 1.0, 5.0, 20.0, 80.0, 300.0], dtype=float)
    amp = np.array([1.0, 8.0, 7.0, 6.0, 5.0, 9.0, 0.5], dtype=float)

    peaks = detect_peaks(t2, amp)
    assert peaks.has_secondary is True
    assert peaks.valley is not None
    assert peaks.valley.is_fallback is True
    assert peaks.valley.t2_ms == 10.0


def test_log_integration_preserves_normalized_ratios(tmp_path: Path) -> None:
    file_path = tmp_path / "nmr.csv"
    df = pd.DataFrame(
        {
            "弛豫时间/ms": [0.1, 0.4, 1.0, 4.0, 10.0, 40.0, 100.0],
            "信号强度": [1, 2, 4, 6, 3, 2, 1],
        }
    )
    df.to_csv(file_path, index=False, encoding="utf-8-sig")

    result = analyse(file_path, mode=IntegrationMode.LOG_TRAPEZOIDAL)
    assert np.isclose(result.system_a.ratios.sum(), 1.0)
    assert np.isclose(result.system_b.ratios.sum(), 1.0)
