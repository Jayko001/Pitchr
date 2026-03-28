"""Research Agent: creates a kernel.sh browser session, scrapes PitchBook comps."""
from __future__ import annotations

import os
import time
from typing import Any, Optional, Callable

import requests
from playwright.sync_api import sync_playwright

from agents.models import CompRecord

KERNEL_SH_BASE_URL = "https://api.onkernel.com"


def create_kernel_session(api_key: str) -> tuple[str, str]:
    """POST to kernel.sh to create a browser session. Returns (session_id, cdp_ws_url)."""
    resp = requests.post(
        f"{KERNEL_SH_BASE_URL}/browsers",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"headless": True, "stealth": True, "timeout_seconds": 120},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["session_id"], data["cdp_ws_url"]


def destroy_kernel_session(api_key: str, session_id: str) -> None:
    """DELETE the kernel.sh session to free resources."""
    requests.delete(
        f"{KERNEL_SH_BASE_URL}/browsers/{session_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )


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

        # Login
        page.goto("https://pitchbook.com/login", wait_until="networkidle")
        sso_btn = page.query_selector("text=Sign in with SSO")
        if sso_btn:
            sso_btn.click()
            page.wait_for_load_state("networkidle")

        page.fill("input[name='email'], input[type='email']", pitchbook_user)
        page.fill("input[name='password'], input[type='password']", pitchbook_pass)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Navigate to company search
        page.goto(
            "https://pitchbook.com/platform/search#entities=company",
            wait_until="networkidle",
        )
        time.sleep(2)

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
    session_id, cdp_url = create_kernel_session(api_key)

    comps: list[CompRecord] = []
    try:
        if status_callback:
            status_callback("Research Agent: logging into PitchBook and scraping comps...")
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
