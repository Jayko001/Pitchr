import pytest
from unittest.mock import patch
from agents.orchestrator import run_pipeline, load_fallback_comps
from agents.models import CompRecord, ValuationRange


SAMPLE_COMPS = [
    CompRecord(
        name="Stripe", sector="Fintech", stage="Series B",
        valuation_usd=65_000_000_000, arr_usd=3_000_000_000,
        ebitda_usd=None, last_funding_round="Series I",
        last_funding_amount_usd=600_000_000, lead_investors=["Sequoia"],
    )
]
SAMPLE_VALUATION = ValuationRange(low=40e6, mid=60e6, high=80e6, methodology="EV/ARR")


def test_run_pipeline_returns_output_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("KERNEL_SH_API_KEY", "test")
    monkeypatch.setenv("PITCHBOOK_USER", "u@test.com")
    monkeypatch.setenv("PITCHBOOK_PASS", "p")

    statuses = []

    with patch("agents.orchestrator.run_research_agent", return_value=SAMPLE_COMPS), \
         patch("agents.orchestrator.run_analysis_agent", return_value=(SAMPLE_VALUATION, str(tmp_path / "comps.xlsx"))), \
         patch("agents.orchestrator.run_deck_agent", return_value=str(tmp_path / "deck.pptx")), \
         patch("agents.orchestrator.create_base_template"):

        result = run_pipeline(
            startup_name="PayFlow",
            sector="Fintech",
            stage="Series B",
            description="B2B payments for SMBs, $1M ARR",
            output_dir=str(tmp_path),
            status_callback=statuses.append,
        )

    assert "excel_path" in result
    assert "pptx_path" in result
    assert len(statuses) > 0


def test_run_pipeline_uses_fallback_on_empty_comps(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("KERNEL_SH_API_KEY", "test")
    monkeypatch.setenv("PITCHBOOK_USER", "u@test.com")
    monkeypatch.setenv("PITCHBOOK_PASS", "p")

    with patch("agents.orchestrator.run_research_agent", return_value=[]), \
         patch("agents.orchestrator.load_fallback_comps", return_value=SAMPLE_COMPS) as mock_fallback, \
         patch("agents.orchestrator.run_analysis_agent", return_value=(SAMPLE_VALUATION, str(tmp_path / "comps.xlsx"))), \
         patch("agents.orchestrator.run_deck_agent", return_value=str(tmp_path / "deck.pptx")), \
         patch("agents.orchestrator.create_base_template"):

        run_pipeline(
            startup_name="PayFlow", sector="Fintech", stage="Series B",
            description="test", output_dir=str(tmp_path),
        )

    mock_fallback.assert_called_once()


def test_load_fallback_comps_returns_comp_records():
    comps = load_fallback_comps(sector="Fintech")
    assert len(comps) > 0
    assert all(isinstance(c, CompRecord) for c in comps)
