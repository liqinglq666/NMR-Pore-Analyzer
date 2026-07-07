"""
Professional multi-sheet Excel research report for NMR-Pore-Analyzer.

Workbook structure
------------------
Sheet 1 - Summary_Peak_Statistics    : SCI three-line table (Table 3).
           Hierarchical headers: Main Peak / Sub-Peak / Boundary / Ratio.
Sheet 2 - Pore_Classification_Ratios : SCI three-line table (Fig 14/16).
           Rows = mixtures, Cols = 8 pore categories (Sys A x4 + Sys B x4).
Sheet 3 - Cumulative_Curve_Data      : Mixtures side-by-side, 3 cols each.
           Row 1 = mixture name (merged), Row 2 = sub-headers, Rows 3+ = data.
           Columns per mixture: Radius (nm) | Differential (%) | Cumulative (%).

Three-line Table convention (Sheet 1 & 2)
------------------------------------------
  Row 1 (group headers) : thick top border.
  Row 2 (sub-headers)   : thin bottom border.
  Last data row         : thick bottom border.
  Plain white, Times New Roman 11 pt, no fill.

Origin column convention (Sheet 3 & 4)
----------------------------------------
  Row 1 : quantity header  (e.g. "Pore radius" / "Cumulative porosity")
  Row 2 : unit             ("nm" / "%")
  Row 3 : mixture name     (e.g. "CSC" - in X column only)
  Row 4+: numeric data pairs
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, Border, Side
from openpyxl.utils import get_column_letter

from logic.analyzer import AnalysisResult
from logic.peak_processor import PeakResult


# ---------------------------------------------------------------------------
# Shared style constants
# ---------------------------------------------------------------------------
_TNR    = "Times New Roman"
_FONT   = Font(name=_TNR, size=11)
_FONT_B = Font(name=_TNR, size=11, bold=True)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

_THICK = Side(border_style="medium", color="000000")
_THIN  = Side(border_style="thin",   color="000000")
_NONE  = Side(border_style=None)


def _border(
    top:    Side = _NONE,
    bottom: Side = _NONE,
    left:   Side = _NONE,
    right:  Side = _NONE,
) -> Border:
    return Border(top=top, bottom=bottom, left=left, right=right)


_B_TOP_THICK = _border(top=_THICK)
_B_BOT_THIN  = _border(bottom=_THIN)
_B_BOT_THICK = _border(bottom=_THICK)
_B_NONE      = _border()


def _fmt_r(value: float) -> str:
    """Format pore radius: 1 decimal if < 1000 nm, else integer."""
    return f"{value:.1f}" if value < 1000 else str(round(value))


def _set_cell(
    ws,
    row: int,
    col: int,
    value,
    font: Font = _FONT,
    align: Alignment = _CENTER,
    border: Border = _B_NONE,
) -> None:
    """Write a single cell with full style."""
    c           = ws.cell(row=row, column=col, value=value)
    c.font      = font
    c.alignment = align
    c.border    = border


# ---------------------------------------------------------------------------
# Sheet 1 - Summary_Peak_Statistics
# ---------------------------------------------------------------------------
# Columns (1-indexed):
#  1 Mixture | 2 MP T2 | 3 MP r | 4 MP Area |
#  5 SP T2   | 6 SP r  | 7 SP Area |
#  8 Valley T2 | 9 Ratio

_PS_GROUPS: List[Tuple[int, int, str]] = [
    (1, 1, "Mixture"),
    (2, 4, "Main Peak"),
    (5, 7, "Sub-Peak"),
    (8, 8, "Boundary"),
    (9, 9, "Peak Ratio\n(Main / Sub)"),
]
_PS_SUB = [
    "Mixture",
    "T2 (ms)", "r (nm)", "Area (%)",
    "T2 (ms)", "r (nm)", "Area (%)",
    "Valley T2 (ms)",
    "Main / Sub",
]


def _write_peak_statistics_sheet(
    ws,
    batch: Dict[str, Tuple[AnalysisResult, PeakResult]],
) -> None:
    """Populate Sheet 1 with SCI three-line peak statistics.

    Args:
        ws: Empty openpyxl Worksheet.
        batch: Ordered mapping of mixture name -> (AnalysisResult, PeakResult).
    """
    # Row 1: group headers + thick top border
    for col_s, col_e, label in _PS_GROUPS:
        if col_e > col_s:
            ws.merge_cells(
                start_row=1, start_column=col_s,
                end_row=1,   end_column=col_e,
            )
        _set_cell(ws, 1, col_s, label, font=_FONT_B, border=_B_TOP_THICK)
        for col in range(col_s + 1, col_e + 1):
            ws.cell(row=1, column=col).border = _B_TOP_THICK

    # Row 2: sub-headers + thin bottom
    for col, label in enumerate(_PS_SUB, start=1):
        _set_cell(ws, 2, col, label, font=_FONT_B, border=_B_BOT_THIN)

    # Data rows
    names = list(batch.keys())
    n     = len(names)
    for i, name in enumerate(names):
        row     = i + 3
        _an, pk = batch[name]
        bdr     = _B_BOT_THICK if i == n - 1 else _B_NONE

        def _w(col: int, value, _row: int = row, _bdr: Border = bdr) -> None:
            _set_cell(ws, _row, col, value, border=_bdr)

        _w(1, name)
        _w(2, round(pk.primary.t2_ms, 2))
        _w(3, _fmt_r(pk.primary.radius_nm))
        _w(4, round(pk.primary.area_ratio * 100, 2))

        if pk.has_secondary and pk.secondary is not None and pk.valley is not None:
            _w(5, round(pk.secondary.t2_ms, 2))
            _w(6, _fmt_r(pk.secondary.radius_nm))
            _w(7, round(pk.secondary.area_ratio * 100, 2))
            _w(8, round(pk.valley.t2_ms, 2))
            ratio = (
                round(pk.primary.area_ratio / pk.secondary.area_ratio, 2)
                if pk.secondary.area_ratio > 0 else "N/A"
            )
            _w(9, ratio)
        else:
            for col in range(5, 10):
                _w(col, "N/A")

    # Column widths
    for col, w in enumerate([14, 11, 11, 11, 11, 11, 11, 18, 16], start=1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 22


# ---------------------------------------------------------------------------
# Sheet 2 - Pore_Classification_Ratios
# ---------------------------------------------------------------------------
# Columns:
#  1 Mixture | 2-5 Sys A (Gel, Transition, Capillary, Air-voids) |
#  6-9 Sys B (Harmless, Less-harmful, Harmful, More-harmful)

_A_LABELS = ["Gel", "Transition", "Capillary", "Air-voids"]
_B_LABELS = ["Harmless", "Less-harmful", "Harmful", "More-harmful"]

_PCR_GROUPS: List[Tuple[int, int, str]] = [
    (1, 1, "Mixture"),
    (2, 5, "System A  (Gel / Capillary)"),
    (6, 9, "System B  (Harmless / Harmful)"),
]


def _write_pore_classification_sheet(
    ws,
    batch: Dict[str, Tuple[AnalysisResult, PeakResult]],
) -> None:
    """Populate Sheet 2 with SCI three-line pore classification ratios.

    Args:
        ws: Empty openpyxl Worksheet.
        batch: Ordered mapping of mixture name -> (AnalysisResult, PeakResult).
    """
    # Row 1: group headers
    for col_s, col_e, label in _PCR_GROUPS:
        if col_e > col_s:
            ws.merge_cells(
                start_row=1, start_column=col_s,
                end_row=1,   end_column=col_e,
            )
        _set_cell(ws, 1, col_s, label, font=_FONT_B, border=_B_TOP_THICK)
        for col in range(col_s + 1, col_e + 1):
            ws.cell(row=1, column=col).border = _B_TOP_THICK

    # Row 2: sub-headers
    for col, label in enumerate(["Mixture"] + _A_LABELS + _B_LABELS, start=1):
        _set_cell(ws, 2, col, label, font=_FONT_B, border=_B_BOT_THIN)

    # Data rows
    names = list(batch.keys())
    n     = len(names)
    for i, name in enumerate(names):
        row     = i + 3
        an, _pk = batch[name]
        bdr     = _B_BOT_THICK if i == n - 1 else _B_NONE

        _set_cell(ws, row, 1, name, border=bdr)
        a_dict = dict(zip(an.system_a.labels, an.system_a.ratios))
        b_dict = dict(zip(an.system_b.labels, an.system_b.ratios))

        for j, lbl in enumerate(_A_LABELS, start=2):
            _set_cell(ws, row, j, round(a_dict.get(lbl, 0.0) * 100, 2), border=bdr)
        for j, lbl in enumerate(_B_LABELS, start=6):
            _set_cell(ws, row, j, round(b_dict.get(lbl, 0.0) * 100, 2), border=bdr)

    # Column widths
    ws.column_dimensions["A"].width = 14
    for col in range(2, 10):
        ws.column_dimensions[get_column_letter(col)].width = 16
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 22


# ---------------------------------------------------------------------------
# Sheet 3 - Curve_Data  (Radius / Differential / Cumulative × n mixtures)
# ---------------------------------------------------------------------------
# Layout: mixtures placed side-by-side, each occupying 3 columns.
#   Group col_start = 3*(k-1)+1  for k = 1 … N
#   Col offsets within group:
#     +0  Radius (nm)
#     +1  Differential (%)
#     +2  Cumulative (%)
#
# Row 1 : mixture name (merged across 3 cols, bold, centre)
# Row 2 : sub-headers  "Radius (nm)" | "Differential (%)" | "Cumulative (%)"
# Row 3+: numeric data


def _write_curve_sheet(
    ws,
    batch: Dict[str, Tuple[AnalysisResult, PeakResult]],
) -> None:
    """Write a combined curve sheet: Radius / Differential / Cumulative per mixture.

    Args:
        ws: Empty openpyxl Worksheet.
        batch: Ordered mapping of mixture name -> (AnalysisResult, PeakResult).
    """
    sub_hdrs = ["Radius (nm)", "Differential (%)", "Cumulative (%)"]

    for k, (name, (an, _pk)) in enumerate(batch.items()):
        c0 = 3 * k + 1          # first column of this group (1-indexed)
        c1 = c0 + 1
        c2 = c0 + 2

        # Row 1 – mixture name, merged across 3 cols
        ws.merge_cells(start_row=1, start_column=c0, end_row=1, end_column=c2)
        _set_cell(ws, 1, c0, name, font=_FONT_B, border=_B_TOP_THICK)
        for col in (c1, c2):
            ws.cell(row=1, column=col).border = _B_TOP_THICK

        # Row 2 – sub-headers with thin bottom border
        for ci, hdr in zip((c0, c1, c2), sub_hdrs):
            _set_cell(ws, 2, ci, hdr, font=_FONT_B, border=_B_BOT_THIN)

        # Compute y arrays
        x_vals   = an.radius_nm
        diff_arr = _differential_y(an)
        cum_arr  = an.cumulative * 100.0
        n_rows   = len(x_vals)

        for offset, (xv, dv, cv) in enumerate(zip(x_vals, diff_arr, cum_arr)):
            row = offset + 3
            bdr = _B_BOT_THICK if offset == n_rows - 1 else _B_NONE
            _set_cell(ws, row, c0, float(round(xv, 4)), border=bdr)
            _set_cell(ws, row, c1, float(round(dv, 6)), border=bdr)
            _set_cell(ws, row, c2, float(round(cv, 4)), border=bdr)

    # Column widths
    for k in range(len(batch)):
        c0 = 3 * k + 1
        ws.column_dimensions[get_column_letter(c0)].width     = 14
        ws.column_dimensions[get_column_letter(c0 + 1)].width = 16
        ws.column_dimensions[get_column_letter(c0 + 2)].width = 16
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 22


def _differential_y(an: AnalysisResult) -> np.ndarray:
    """Amplitude as % of total signal (porosity component)."""
    total = an.raw.amplitude.sum()
    if total == 0:
        return np.zeros_like(an.raw.amplitude, dtype=float)
    return (an.raw.amplitude / total) * 100.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_batch_results(
    output_path: Path,
    batch: Dict[str, Tuple[AnalysisResult, PeakResult]],
) -> Path:
    """Write a 4-sheet research workbook for all mixtures in *batch*.

    Sheet layout
    ------------
    1. Summary_Peak_Statistics    - SCI three-line peak statistics (Table 3).
    2. Pore_Classification_Ratios - SCI three-line 8-category ratios (Fig 14/16).
    3. Cumulative_Curve_Data      - Origin-ready S-curve paired columns.
    4. Differential_Curve_Data    - Origin-ready distribution paired columns.

    Args:
        output_path: Destination .xlsx file path.
        batch: Ordered dict mapping mixture name ->
               (AnalysisResult, PeakResult) tuple.

    Returns:
        Resolved absolute path of the written file.

    Raises:
        OSError: If the output directory is not writable.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sheet_names = [
        "Summary_Peak_Statistics",
        "Pore_Classification_Ratios",
        "Cumulative_Curve_Data",
    ]
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sname in sheet_names:
            pd.DataFrame().to_excel(writer, sheet_name=sname, index=False)

    wb = load_workbook(output_path)

    ws1 = wb["Summary_Peak_Statistics"]
    ws1.delete_rows(1, ws1.max_row)
    _write_peak_statistics_sheet(ws1, batch)

    ws2 = wb["Pore_Classification_Ratios"]
    ws2.delete_rows(1, ws2.max_row)
    _write_pore_classification_sheet(ws2, batch)

    ws3 = wb["Cumulative_Curve_Data"]
    ws3.delete_rows(1, ws3.max_row)
    _write_curve_sheet(ws3, batch)

    wb.save(output_path)
    return output_path.resolve()


def export_results(
    output_path: Path,
    analysis: AnalysisResult,
    peak_result: PeakResult,
) -> Path:
    """Convenience wrapper: export a single sample as a one-mixture batch.

    Args:
        output_path: Destination .xlsx file path.
        analysis: Full analysis result from ``analyzer.analyse()``.
        peak_result: Peak detection result from ``peak_processor.detect_peaks()``.

    Returns:
        Resolved absolute path of the written file.
    """
    return export_batch_results(
        output_path,
        batch={"Sample": (analysis, peak_result)},
    )
