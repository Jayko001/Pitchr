"""Research Agent: creates a kernel.sh browser session, scrapes PitchBook comps."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional, Callable

import requests
from playwright.sync_api import sync_playwright
from kernel import Kernel

from agents.models import CompRecord


@dataclass(frozen=True)
class KernelSession:
    session_id: str
    cdp_url: str
    live_view_url: str
    should_destroy: bool


def create_kernel_session(api_key: str) -> tuple[str, str, str]:
    """Create a headful browser with a US residential proxy. Returns (session_id, cdp_ws_url, live_view_url)."""
    client = Kernel(api_key=api_key)

    proxy = client.proxies.create(
        type="residential",
        name="pitchbook-us",
        config={"country": "US"},
    )

    browser = client.browsers.create(
        headless=False,
        stealth=True,
        timeout_seconds=300,
        proxy_id=proxy.id,
    )

    return browser.session_id, browser.cdp_ws_url, browser.browser_live_view_url or ""


def get_existing_kernel_session(
    api_key: str,
    session_id: str,
    cdp_url: Optional[str] = None,
    live_view_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """Resolve a previously created kernel.sh session to its CDP/live-view URLs."""
    if cdp_url:
        return session_id, cdp_url, live_view_url or ""

    client = Kernel(api_key=api_key)
    browsers_api = client.browsers

    for method_name in ("get", "retrieve", "fetch"):
        method = getattr(browsers_api, method_name, None)
        if not callable(method):
            continue

        browser = method(session_id)
        resolved_session_id = getattr(browser, "session_id", None) or getattr(browser, "id", None) or session_id
        resolved_cdp_url = getattr(browser, "cdp_ws_url", None) or getattr(browser, "cdp_url", None)
        resolved_live_view_url = (
            getattr(browser, "browser_live_view_url", None)
            or getattr(browser, "live_view_url", None)
            or ""
        )

        if not resolved_cdp_url:
            raise ValueError(
                f"Kernel session '{session_id}' was found, but no CDP URL was returned. "
                "Set KERNEL_SH_CDP_URL explicitly."
            )

        return resolved_session_id, resolved_cdp_url, resolved_live_view_url

    raise ValueError(
        f"Kernel session '{session_id}' was provided, but the installed SDK does not expose a browser lookup method. "
        "Set KERNEL_SH_CDP_URL explicitly or update the SDK integration."
    )


def destroy_kernel_session(api_key: str, session_id: str) -> None:
    """Delete the kernel.sh browser session."""
    client = Kernel(api_key=api_key)
    client.browsers.delete(session_id)


def _is_logged_in_url(url: str) -> bool:
    """Heuristic for a PitchBook page that indicates the user is logged in."""
    return any(marker in url for marker in ("/platform", "/profiles", "pitchbook.com/your-dashboard"))


def _iter_browser_pages(browser: Any) -> list[tuple[Any, Any]]:
    """Return every attached page paired with its browser context."""
    pages: list[tuple[Any, Any]] = []
    for context in browser.contexts:
        for page in context.pages:
            pages.append((context, page))
    return pages


def _get_or_create_attached_page(browser: Any) -> tuple[Any, Any]:
    """Reuse an existing page in the attached browser when possible."""
    pages = _iter_browser_pages(browser)
    for context, page in pages:
        if _is_logged_in_url(page.url):
            return context, page

    for context, page in pages:
        if "pitchbook.com" in page.url:
            return context, page

    if pages:
        return pages[-1]

    if browser.contexts:
        context = browser.contexts[0]
        return context, context.new_page()

    context = browser.new_context()
    return context, context.new_page()


def _wait_for_logged_in_page(browser: Any, preferred_page: Any, timeout_seconds: int = 180) -> Any:
    """Wait for any attached page to reach a logged-in PitchBook URL."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for _, page in _iter_browser_pages(browser):
            if _is_logged_in_url(page.url):
                return page
        if _is_logged_in_url(preferred_page.url):
            return preferred_page
        time.sleep(1)

    raise TimeoutError("Timed out waiting for PitchBook login to complete.")


def run_playwright_scrape(
    cdp_url: str,
    pitchbook_user: str,
    pitchbook_pass: str,
    sector: str,
    stage: str,
) -> list[dict[str, Any]]:
    """Connect Playwright to kernel.sh CDP session, log into PitchBook, scrape comps."""
    comps: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context, page = _get_or_create_attached_page(browser)

        current_url = page.url or ""

        # If the existing tab already has search results loaded, use it as-is.
        already_on_results = (
            "pitchbook.com/platform" in current_url
            or "pitchbook.com/profiles" in current_url
        )

        if already_on_results:
            # User already has the right tab open — don't navigate away.
            pass
        elif "pitchbook.com" not in current_url:
            # Not on PitchBook at all — navigate and wait for manual login.
            page.goto("https://pitchbook.com", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            try:
                page = _wait_for_logged_in_page(browser, page, timeout_seconds=180)
            except TimeoutError:
                pass
            page.goto(
                "https://pitchbook.com/platform/search#entities=company",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(3)
        else:
            # On PitchBook but not yet on a results page — navigate to search.
            page.goto(
                "https://pitchbook.com/platform/search#entities=company",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(3)

        # Wait for page to fully settle before touching any selectors
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        # Apply sector filter
        try:
            sector_filter = page.query_selector("text=Sector")
            if sector_filter:
                sector_filter.click()
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                try:
                    page.wait_for_selector("input[placeholder*='Search']", timeout=5000)
                    page.fill("input[placeholder*='Search']", sector)
                except Exception:
                    pass
                option = page.query_selector(f"text={sector}")
                if option:
                    option.click()
                time.sleep(1)
        except Exception:
            pass

        # Apply stage filter
        try:
            stage_filter = page.query_selector("text=Deal Stage")
            if stage_filter:
                stage_filter.click()
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                option = page.query_selector(f"text={stage}")
                if option:
                    option.click()
                time.sleep(1)
        except Exception:
            pass

        # Wait for results to load
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            page.wait_for_selector("table, [data-testid='results-table'], tbody tr", timeout=10000)
        except Exception:
            return comps

        time.sleep(1)

        # Scrape — snapshot rows before iterating to avoid mid-navigation context destruction
        try:
            rows = page.query_selector_all("tr[data-company-id], tbody tr")
        except Exception:
            return comps

        for row in rows[:12]:
            try:
                cells = row.query_selector_all("td")
                if len(cells) < 4:
                    continue
                comp = {
                    "name": cells[0].inner_text().strip(),
                    "sector": sector,
                    "stage": stage,
                    "valuation_usd": _parse_usd(cells[1].inner_text()),
                    "arr_usd": _parse_usd(cells[2].inner_text()),
                    "ebitda_usd": None,
                    "last_funding_round": cells[3].inner_text().strip() if len(cells) > 3 else "",
                    "last_funding_amount_usd": _parse_usd(cells[4].inner_text()) if len(cells) > 4 else None,
                    "lead_investors": [],
                }
                if comp["name"]:
                    comps.append(comp)
            except Exception:
                continue

    return comps


def _parse_usd(text: str) -> float | None:
    """Convert '$120M', '$1.2B', '—' etc. to float or None."""
    text = text.strip().replace(",", "").replace("$", "")
    if not text or text in ("—", "-", "N/A", ""):
        return None
    multiplier = 1.0
    if text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def scrape_pitchbook_comps(
    sector: str,
    stage: str,
    cdp_url: str,
    pitchbook_user: str,
    pitchbook_pass: str,
) -> list[CompRecord]:
    """Run the Playwright scraper and return validated CompRecord list."""
    raw = run_playwright_scrape(
        cdp_url=cdp_url,
        pitchbook_user=pitchbook_user,
        pitchbook_pass=pitchbook_pass,
        sector=sector,
        stage=stage,
    )
    return [CompRecord(**r) for r in raw]


def resolve_kernel_session(
    api_key: str,
    existing_session_id: Optional[str] = None,
    existing_cdp_url: Optional[str] = None,
    existing_live_view_url: Optional[str] = None,
) -> KernelSession:
    """Create a new kernel.sh session or reuse an existing one."""
    if existing_session_id:
        session_id, cdp_url, live_view_url = get_existing_kernel_session(
            api_key=api_key,
            session_id=existing_session_id,
            cdp_url=existing_cdp_url,
            live_view_url=existing_live_view_url,
        )
        return KernelSession(
            session_id=session_id,
            cdp_url=cdp_url,
            live_view_url=live_view_url,
            should_destroy=False,
        )

    session_id, cdp_url, live_view_url = create_kernel_session(api_key)
    return KernelSession(
        session_id=session_id,
        cdp_url=cdp_url,
        live_view_url=live_view_url,
        should_destroy=True,
    )


def run_research_agent(
    sector: str,
    stage: str,
    kernel_session_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[CompRecord]:
    """
    Top-level entry point called by the orchestrator.
    Creates a kernel.sh session, scrapes PitchBook, destroys session.
    """
    api_key = os.environ["KERNEL_SH_API_KEY"]
    pb_user = os.environ["PITCHBOOK_USER"]
    pb_pass = os.environ["PITCHBOOK_PASS"]
    session_id_override = kernel_session_id or os.getenv("KERNEL_SH_SESSION_ID")
    cdp_url_override = os.getenv("KERNEL_SH_CDP_URL")
    live_view_url_override = os.getenv("KERNEL_SH_LIVE_VIEW_URL")

    if status_callback:
        if session_id_override:
            status_callback(f"Research Agent: reusing kernel.sh browser session '{session_id_override}'...")
        else:
            status_callback("Research Agent: creating kernel.sh browser session...")
    session = resolve_kernel_session(
        api_key=api_key,
        existing_session_id=session_id_override,
        existing_cdp_url=cdp_url_override,
        existing_live_view_url=live_view_url_override,
    )

    if status_callback and session.live_view_url:
        status_callback(f"LIVE VIEW (open in browser): {session.live_view_url}")

    comps: list[CompRecord] = []
    try:
        if status_callback:
            if session_id_override:
                status_callback("Research Agent: attaching to existing browser tab and scraping...")
            else:
                status_callback("Research Agent: opened pitchbook.com — OPEN THE LIVE VIEW LINK ABOVE and log in manually. Waiting up to 3 minutes...")
        comps = scrape_pitchbook_comps(
            sector=sector,
            stage=stage,
            cdp_url=session.cdp_url,
            pitchbook_user=pb_user,
            pitchbook_pass=pb_pass,
        )
    finally:
        if session.should_destroy:
            destroy_kernel_session(api_key, session.session_id)
        elif status_callback:
            status_callback(f"Research Agent: preserved existing kernel.sh session '{session.session_id}'.")
        if status_callback:
            status_callback(f"Research Agent: done. Found {len(comps)} comps.")

    return comps
