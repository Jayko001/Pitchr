import pytest
from unittest.mock import patch, MagicMock
from agents.research import (
    _get_or_create_attached_page,
    _is_logged_in_url,
    _wait_for_logged_in_page,
    create_kernel_session,
    destroy_kernel_session,
    get_existing_kernel_session,
    run_research_agent,
    scrape_pitchbook_comps,
)
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


def test_get_existing_kernel_session_returns_cdp_url():
    mock_client = _mock_kernel_client()
    mock_client.browsers.get.return_value = mock_client.browsers.create.return_value

    with patch("agents.research.Kernel", return_value=mock_client):
        session_id, cdp_url, live_url = get_existing_kernel_session(
            api_key="test_key",
            session_id="sess_abc123",
        )

    assert session_id == "sess_abc123"
    assert cdp_url == "wss://browser.onkernel.com/sess_abc123"
    assert live_url == "https://live.onkernel.com/sess_abc123"


def test_run_research_agent_reuses_existing_session_without_deleting(monkeypatch):
    monkeypatch.setenv("KERNEL_SH_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("PITCHBOOK_USER", "u@test.com")
    monkeypatch.setenv("PITCHBOOK_PASS", "p")

    statuses = []

    with patch("agents.research.get_existing_kernel_session", return_value=("sess_abc123", "wss://browser.onkernel.com/sess_abc123", "https://live.onkernel.com/sess_abc123")) as mock_get, \
         patch("agents.research.run_computer_use_scrape", return_value=[MOCK_COMPS_JSON[0]]), \
         patch("agents.research.destroy_kernel_session") as mock_destroy:

        comps = run_research_agent(
            sector="Fintech",
            stage="Series B",
            kernel_session_id="sess_abc123",
            status_callback=statuses.append,
        )

    assert len(comps) == 1
    mock_get.assert_called_once()
    mock_destroy.assert_not_called()
    assert any("reusing kernel.sh browser session" in status for status in statuses)
    assert any("preserved existing kernel.sh session" in status for status in statuses)


def test_get_or_create_attached_page_reuses_existing_page():
    existing_page = MagicMock()
    existing_page.url = "https://pitchbook.com/platform/search#entities=company"
    existing_context = MagicMock()
    existing_context.pages = [existing_page]

    browser = MagicMock()
    browser.contexts = [existing_context]

    context, page = _get_or_create_attached_page(browser)

    assert context is existing_context
    assert page is existing_page
    browser.new_context.assert_not_called()
    existing_context.new_page.assert_not_called()


def test_is_logged_in_url_detects_pitchbook_platform_pages():
    assert _is_logged_in_url("https://pitchbook.com/platform/search#entities=company")
    assert not _is_logged_in_url("https://pitchbook.com/login")


def test_wait_for_logged_in_page_returns_existing_logged_in_page():
    existing_page = MagicMock()
    existing_page.url = "https://pitchbook.com/platform/search#entities=company"
    existing_context = MagicMock()
    existing_context.pages = [existing_page]

    browser = MagicMock()
    browser.contexts = [existing_context]

    page = _wait_for_logged_in_page(browser, existing_page, timeout_seconds=1)

    assert page is existing_page


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
