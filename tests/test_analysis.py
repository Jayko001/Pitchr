import pytest
from unittest.mock import patch
from agents.analysis import build_excel_model, run_analysis_agent
from agents.models import CompRecord, ValuationRange, ExcelInstructions, CellWrite
import openpyxl


SAMPLE_COMPS = [
    CompRecord(
        name="Stripe", sector="Fintech", stage="Series B",
        valuation_usd=65_000_000_000, arr_usd=3_000_000_000,
        ebitda_usd=None, last_funding_round="Series I",
        last_funding_amount_usd=600_000_000, lead_investors=["Sequoia"],
    ),
    CompRecord(
        name="Brex", sector="Fintech", stage="Series C",
        valuation_usd=12_300_000_000, arr_usd=500_000_000,
        ebitda_usd=None, last_funding_round="Series C",
        last_funding_amount_usd=300_000_000, lead_investors=["Tiger Global"],
    ),
]

MOCK_EXCEL_INSTRUCTIONS = ExcelInstructions(
    sheets=["Comps", "Multiples", "Valuation"],
    writes=[
        CellWrite(sheet="Comps", cell="A1", value="Company", bold=True),
        CellWrite(sheet="Comps", cell="B1", value="Valuation ($M)", bold=True),
        CellWrite(sheet="Comps", cell="A2", value="Stripe"),
        CellWrite(sheet="Comps", cell="B2", value=65000.0),
        CellWrite(sheet="Multiples", cell="A1", value="Metric", bold=True),
        CellWrite(sheet="Multiples", cell="B1", value="Median", bold=True),
        CellWrite(sheet="Multiples", cell="A2", value="EV/ARR"),
        CellWrite(sheet="Multiples", cell="B2", formula="=MEDIAN(Comps!C2:C10)"),
        CellWrite(sheet="Valuation", cell="A1", value="Scenario", bold=True),
        CellWrite(sheet="Valuation", cell="A2", value="Low"),
        CellWrite(sheet="Valuation", cell="B2", value=40_000_000),
        CellWrite(sheet="Valuation", cell="A3", value="Mid"),
        CellWrite(sheet="Valuation", cell="B3", value=60_000_000),
        CellWrite(sheet="Valuation", cell="A4", value="High"),
        CellWrite(sheet="Valuation", cell="B4", value=80_000_000),
    ],
    column_widths={"Comps": {"A": 20.0, "B": 15.0}},
)


def test_build_excel_model_creates_file(tmp_path):
    output_path = str(tmp_path / "comps.xlsx")
    build_excel_model(MOCK_EXCEL_INSTRUCTIONS, output_path)
    wb = openpyxl.load_workbook(output_path)
    assert "Comps" in wb.sheetnames
    assert "Multiples" in wb.sheetnames
    assert "Valuation" in wb.sheetnames
    ws = wb["Comps"]
    assert ws["A1"].value == "Company"
    assert ws["A1"].font.bold is True


def test_run_analysis_agent_returns_valuation_range(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    output_path = str(tmp_path / "comps.xlsx")

    with patch("agents.analysis.call_claude_for_excel_instructions", return_value=MOCK_EXCEL_INSTRUCTIONS):
        valuation_range, path = run_analysis_agent(
            comps=SAMPLE_COMPS,
            startup_description="A fintech startup processing B2B payments, $5M ARR",
            output_path=output_path,
        )

    assert isinstance(valuation_range, ValuationRange)
    assert valuation_range.low < valuation_range.mid < valuation_range.high
    assert path == output_path
