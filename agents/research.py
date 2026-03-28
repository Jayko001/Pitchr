"""Research Agent: creates a kernel.sh browser session, scrapes PitchBook comps."""
from __future__ import annotations

import os
import time
from typing import Any, Optional, Callable

import requests
from playwright.sync_api import sync_playwright
from kernel import Kernel

from agents.models import CompRecord


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


def destroy_kernel_session(api_key: str, session_id: str) -> None:
    """Delete the kernel.sh browser session."""
    client = Kernel(api_key=api_key)
    client.browsers.delete(session_id)


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
        context = browser.new_context()
        page = context.new_page()

        # Navigate to PitchBook homepage — user logs in manually via the live view URL
        page.goto("https://pitchbook.com", wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)

        # Wait up to 3 minutes for the user to log in manually.
        # We detect login by waiting for a URL that contains /platform or /profiles.
        try:
            page.wait_for_url(
                lambda url: "/platform" in url or "/profiles" in url or "pitchbook.com/your-dashboard" in url,
                timeout=180000,
            )
        except Exception:
            # If still not logged in, try auto-fill as fallback
            try:
                page.goto("https://pitchbook.com/login", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                email_input = page.query_selector("input[type='email']") or page.query_selector("input[name='email']") or page.query_selector("input[type='text']")
                pass_input = page.query_selector("input[type='password']")
                if email_input and pass_input:
                    email_input.fill(pitchbook_user)
                    pass_input.fill(pitchbook_pass)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(4)
            except Exception:
                pass

        # Navigate to company search
        page.goto(
            "https://pitchbook.com/platform/search#entities=company",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        time.sleep(3)

        # Apply sector filter
        sector_filter = page.query_selector("text=Sector")
        if sector_filter:
            sector_filter.click()
            try:
                page.wait_for_selector("input[placeholder*='Search']", timeout=5000)
                page.fill("input[placeholder*='Search']", sector)
            except Exception:
                pass
            option = page.query_selector(f"text={sector}")
            if option:
                option.click()
            time.sleep(1)

        # Apply stage filter
        stage_filter = page.query_selector("text=Deal Stage")
        if stage_filter:
            stage_filter.click()
            option = page.query_selector(f"text={stage}")
            if option:
                option.click()
            time.sleep(1)

        # Scrape results
        try:
            page.wait_for_selector("table, [data-testid='results-table']", timeout=10000)
        except Exception:
            browser.close()
            return comps

        rows = page.query_selector_all("tr[data-company-id], tbody tr")

        for row in rows[:12]:
            cells = row.query_selector_all("td")
            if len(cells) < 4:
                continue
            try:
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

        browser.close()

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


def run_research_agent(
    sector: str,
    stage: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[CompRecord]:
    """
    Top-level entry point called by the orchestrator.
    Creates a kernel.sh session, scrapes PitchBook, destroys session.
    """
    api_key = os.environ["KERNEL_SH_API_KEY"]
    pb_user = os.environ["PITCHBOOK_USER"]
    pb_pass = os.environ["PITCHBOOK_PASS"]

    if status_callback:
        status_callback("Research Agent: creating kernel.sh browser session...")
    session_id, cdp_url, live_view_url = create_kernel_session(api_key)

    if status_callback and live_view_url:
        status_callback(f"LIVE VIEW (open in browser): {live_view_url}")

    comps: list[CompRecord] = []
    try:
        if status_callback:
            status_callback("Research Agent: opened pitchbook.com — OPEN THE LIVE VIEW LINK ABOVE and log in manually. Waiting up to 3 minutes...")
        comps = scrape_pitchbook_comps(
            sector=sector,
            stage=stage,
            cdp_url=cdp_url,
            pitchbook_user=pb_user,
            pitchbook_pass=pb_pass,
        )
    finally:
        destroy_kernel_session(api_key, session_id)
        if status_callback:
            status_callback(f"Research Agent: done. Found {len(comps)} comps.")

    return comps
