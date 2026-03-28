import json
import pytest
from unittest.mock import patch, MagicMock
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


def _mock_kernel_client():
    mock_proxy = MagicMock()
    mock_proxy.id = "proxy_123"

    mock_browser = MagicMock()
    mock_browser.session_id = "sess_abc123"
    mock_browser.cdp_ws_url = "wss://browser.onkernel.com/sess_abc123"
    mock_browser.browser_live_view_url = "https://live.onkernel.com/sess_abc123"

    mock_client = MagicMock()
    mock_client.proxies.create.return_value = mock_proxy
    mock_client.browsers.create.return_value = mock_browser
    return mock_client


def test_create_kernel_session_returns_cdp_url():
    with patch("agents.research.Kernel", return_value=_mock_kernel_client()):
        session_id, cdp_url, live_url = create_kernel_session(api_key="test_key")
    assert session_id == "sess_abc123"
    assert cdp_url == "wss://browser.onkernel.com/sess_abc123"
    assert "live" in live_url


def test_destroy_kernel_session():
    mock_client = _mock_kernel_client()
    with patch("agents.research.Kernel", return_value=mock_client):
        destroy_kernel_session(api_key="test_key", session_id="sess_abc123")
    mock_client.browsers.delete.assert_called_once_with("sess_abc123")


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
