import json
import pytest
from unittest.mock import patch
from agents.research import create_kernel_session, destroy_kernel_session, scrape_pitchbook_comps
from agents.models import CompRecord


MOCK_COMPS_JSON = [
    {
        "name": "Stripe",
        "sector": "Fintech",
        "stage": "Late Stage",
        "valuation_usd": 65_000_000_000,
        "arr_usd": 3_000_000_000,
        "ebitda_usd": None,
        "last_funding_round": "Series I",
        "last_funding_amount_usd": 600_000_000,
        "lead_investors": ["Sequoia", "Andreessen Horowitz"],
    }
]


def test_create_kernel_session_returns_cdp_url(requests_mock):
    requests_mock.post(
        "https://api.onkernel.com/browsers",
        json={"session_id": "sess_abc123", "cdp_ws_url": "wss://browser.onkernel.com/sess_abc123"},
    )
    session_id, cdp_url = create_kernel_session(api_key="test_key")
    assert session_id == "sess_abc123"
    assert cdp_url == "wss://browser.onkernel.com/sess_abc123"


def test_destroy_kernel_session(requests_mock):
    requests_mock.delete(
        "https://api.onkernel.com/browsers/sess_abc123",
        json={"deleted": True},
    )
    destroy_kernel_session(api_key="test_key", session_id="sess_abc123")


def test_scrape_pitchbook_comps_returns_comp_records(tmp_path, monkeypatch):
    with patch("agents.research.run_playwright_scrape", return_value=MOCK_COMPS_JSON):
        comps = scrape_pitchbook_comps(
            sector="Fintech",
            stage="Series B",
            cdp_url="wss://fake",
            pitchbook_user="user@test.com",
            pitchbook_pass="pass",
        )

    assert len(comps) == 1
    assert isinstance(comps[0], CompRecord)
    assert comps[0].name == "Stripe"
    assert comps[0].ev_to_arr == pytest.approx(21.67, rel=0.01)
