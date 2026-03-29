"""Research Agent: Claude computer-use agent navigates PitchBook via kernel.sh browser."""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional, Callable

import anthropic
from kernel import Kernel

from agents.models import CompRecord


@dataclass(frozen=True)
class KernelSession:
    session_id: str
    cdp_url: str
    live_view_url: str
    should_destroy: bool


# ---------------------------------------------------------------------------
# Kernel session management
# ---------------------------------------------------------------------------

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

    for method_name in ("get", "retrieve", "fetch"):
        method = getattr(client.browsers, method_name, None)
        if not callable(method):
            continue
        browser = method(session_id)
        resolved_cdp = getattr(browser, "cdp_ws_url", None) or getattr(browser, "cdp_url", None)
        resolved_live = getattr(browser, "browser_live_view_url", None) or ""
        resolved_id = getattr(browser, "session_id", None) or session_id
        if not resolved_cdp:
            raise ValueError(f"No CDP URL found for session '{session_id}'.")
        return resolved_id, resolved_cdp, resolved_live

    raise ValueError(f"SDK has no browser lookup method. Set KERNEL_SH_CDP_URL explicitly.")


def destroy_kernel_session(api_key: str, session_id: str) -> None:
    client = Kernel(api_key=api_key)
    client.browsers.delete(session_id)


def resolve_kernel_session(
    api_key: str,
    existing_session_id: Optional[str] = None,
    existing_cdp_url: Optional[str] = None,
    existing_live_view_url: Optional[str] = None,
) -> KernelSession:
    if existing_session_id:
        sid, cdp, live = get_existing_kernel_session(
            api_key=api_key,
            session_id=existing_session_id,
            cdp_url=existing_cdp_url,
            live_view_url=existing_live_view_url,
        )
        return KernelSession(session_id=sid, cdp_url=cdp, live_view_url=live, should_destroy=False)

    sid, cdp, live = create_kernel_session(api_key)
    return KernelSession(session_id=sid, cdp_url=cdp, live_view_url=live, should_destroy=True)


# ---------------------------------------------------------------------------
# Claude computer-use agent
# ---------------------------------------------------------------------------

def _take_screenshot(kernel_client: Kernel, session_id: str) -> str:
    """Take a screenshot and return it as base64 PNG."""
    img_data = kernel_client.browsers.computer.capture_screenshot(id=session_id)
    return base64.b64encode(img_data.read()).decode()


def _execute_computer_action(kernel_client: Kernel, session_id: str, action: dict) -> None:
    """Execute a Claude computer-use action on the kernel.sh browser."""
    action_type = action.get("action")

    if action_type in ("left_click", "right_click", "double_click", "middle_click"):
        x, y = action["coordinate"]
        button = "right" if action_type == "right_click" else "left"
        num_clicks = 2 if action_type == "double_click" else 1
        kernel_client.browsers.computer.click_mouse(
            id=session_id, x=x, y=y, button=button, num_clicks=num_clicks
        )

    elif action_type == "type":
        kernel_client.browsers.computer.type_text(id=session_id, text=action["text"])

    elif action_type == "key":
        kernel_client.browsers.computer.press_key(id=session_id, keys=[action["text"]])

    elif action_type == "scroll":
        x, y = action["coordinate"]
        direction = action.get("direction", "down")
        amount = action.get("amount", 3)
        delta_y = amount * 100 if direction == "down" else (-amount * 100 if direction == "up" else 0)
        delta_x = amount * 100 if direction == "right" else (-amount * 100 if direction == "left" else 0)
        kernel_client.browsers.computer.scroll(
            id=session_id, x=x, y=y, delta_x=delta_x, delta_y=delta_y
        )

    elif action_type == "mouse_move":
        x, y = action["coordinate"]
        kernel_client.browsers.computer.move_mouse(id=session_id, x=x, y=y)


def run_computer_use_scrape(
    session_id: str,
    sector: str,
    stage: str,
    anthropic_api_key: str,
    kernel_api_key: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """
    Use Claude computer-use to navigate PitchBook and extract comparable company data.
    Claude sees screenshots of the browser and controls it via kernel.sh.
    """
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    kernel_client = Kernel(api_key=kernel_api_key)

    tools = [{
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": 1280,
        "display_height_px": 800,
    }]

    system = f"""You are a data extraction agent on PitchBook. Extract comparable company data for {sector} companies at {stage} stage.

For each company in the search results, collect:
- name (string)
- valuation_usd (float in dollars, e.g. 1200000000 for $1.2B, null if unavailable)
- arr_usd (float in dollars, null if unavailable)
- ebitda_usd (float in dollars, null if unavailable)
- last_funding_round (string, e.g. "Series B")
- last_funding_amount_usd (float in dollars, null if unavailable)
- lead_investors (list of strings)

Scroll through all visible results to collect up to 12 companies.
When you have collected all available data, respond with ONLY a valid JSON array. No prose, no markdown.
Example: [{{"name": "Acme", "valuation_usd": 1200000000, "arr_usd": 50000000, "ebitda_usd": null, "last_funding_round": "Series B", "last_funding_amount_usd": 30000000, "lead_investors": ["Sequoia"]}}]"""

    # Seed conversation with initial screenshot
    if status_callback:
        status_callback("Research Agent: Claude taking initial screenshot of PitchBook...")

    initial_screenshot = _take_screenshot(kernel_client, session_id)
    messages: list[dict] = [{
        "role": "user",
        "content": [
            {"type": "text", "text": f"Extract all {sector} {stage} company data visible on screen. Scroll as needed to get up to 12 companies, then return the JSON array."},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": initial_screenshot}},
        ],
    }]

    extracted: list[dict] = []

    for iteration in range(30):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Claude finished — parse JSON from text response
            for block in response.content:
                if hasattr(block, "text"):
                    raw = block.text.strip()
                    start = raw.find("[")
                    end = raw.rfind("]") + 1
                    if start >= 0 and end > start:
                        try:
                            extracted = json.loads(raw[start:end])
                        except json.JSONDecodeError:
                            pass
            if status_callback:
                status_callback(f"Research Agent: Claude extracted {len(extracted)} companies.")
            break

        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            action = block.input

            if action.get("action") == "screenshot":
                if status_callback:
                    status_callback(f"Research Agent: Claude taking screenshot (step {iteration + 1})...")
                screenshot = _take_screenshot(kernel_client, session_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot}}],
                })
            else:
                if status_callback:
                    status_callback(f"Research Agent: Claude → {action.get('action')} at {action.get('coordinate', action.get('text', ''))}")
                _execute_computer_action(kernel_client, session_id, action)
                time.sleep(0.8)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Action executed.",
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    # Normalize extracted records
    normalized = []
    for comp in extracted:
        comp.setdefault("sector", sector)
        comp.setdefault("stage", stage)
        comp.setdefault("ebitda_usd", None)
        comp.setdefault("last_funding_round", "")
        comp.setdefault("last_funding_amount_usd", None)
        comp.setdefault("lead_investors", [])
        normalized.append(comp)

    return normalized


# ---------------------------------------------------------------------------
# Legacy helpers (kept for tests that mock run_playwright_scrape)
# ---------------------------------------------------------------------------

def _is_logged_in_url(url: str) -> bool:
    return any(marker in url for marker in ("/platform", "/profiles", "pitchbook.com/your-dashboard"))


def _iter_browser_pages(browser: Any) -> list[tuple[Any, Any]]:
    pages: list[tuple[Any, Any]] = []
    for context in browser.contexts:
        for page in context.pages:
            pages.append((context, page))
    return pages


def _get_or_create_attached_page(browser: Any) -> tuple[Any, Any]:
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
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for _, page in _iter_browser_pages(browser):
            if _is_logged_in_url(page.url):
                return page
        if _is_logged_in_url(preferred_page.url):
            return preferred_page
        time.sleep(1)
    raise TimeoutError("Timed out waiting for PitchBook login.")


def run_playwright_scrape(
    cdp_url: str,
    pitchbook_user: str,
    pitchbook_pass: str,
    sector: str,
    stage: str,
) -> list[dict[str, Any]]:
    """Fallback Playwright scraper (used in tests via mock)."""
    from playwright.sync_api import sync_playwright
    comps: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        _, page = _get_or_create_attached_page(browser)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(2)
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
    """Fallback: used by tests that mock run_playwright_scrape."""
    raw = run_playwright_scrape(
        cdp_url=cdp_url,
        pitchbook_user=pitchbook_user,
        pitchbook_pass=pitchbook_pass,
        sector=sector,
        stage=stage,
    )
    return [CompRecord(**r) for r in raw]


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def run_research_agent(
    sector: str,
    stage: str,
    kernel_session_id: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[CompRecord]:
    """
    Top-level entry point called by the orchestrator.
    Uses Claude computer-use to extract comps from PitchBook via kernel.sh.
    """
    api_key = os.environ["KERNEL_SH_API_KEY"]
    anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]
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
        raw = run_computer_use_scrape(
            session_id=session.session_id,
            sector=sector,
            stage=stage,
            anthropic_api_key=anthropic_api_key,
            kernel_api_key=api_key,
            status_callback=status_callback,
        )
        comps = [CompRecord(**r) for r in raw]
    finally:
        if session.should_destroy:
            destroy_kernel_session(api_key, session.session_id)
        elif status_callback:
            status_callback(f"Research Agent: preserved existing kernel.sh session '{session.session_id}'.")
        if status_callback:
            status_callback(f"Research Agent: done. Found {len(comps)} comps.")

    return comps
