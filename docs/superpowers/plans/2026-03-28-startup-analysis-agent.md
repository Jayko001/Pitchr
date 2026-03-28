# Startup Analysis Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agent pipeline that takes an early-stage startup description, scrapes PitchBook via kernel.sh for comparable companies, and produces a comps Excel model and PowerPoint pitch deck.

**Architecture:** Orchestrator agent (claude-sonnet-4-6) sequences three specialist agents: Research (kernel.sh + Playwright → PitchBook), Analysis (Claude → openpyxl Excel), and Deck (Claude → python-pptx). Streamlit UI provides input form, live status feed, and file downloads.

**Tech Stack:** Python 3.11, `anthropic`, `playwright`, `openpyxl`, `python-pptx`, `streamlit`, `pydantic`, `python-dotenv`, `requests`

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | All dependencies pinned |
| `.env.example` | Env var template (committed) |
| `.gitignore` | Ignore `.env`, `outputs/` |
| `agents/models.py` | Shared Pydantic models (CompRecord, ValuationRange, DeckContent, ExcelInstructions) |
| `agents/research.py` | kernel.sh session + Playwright PitchBook scraper |
| `agents/analysis.py` | Claude prompt → openpyxl Excel writer |
| `agents/deck.py` | Base template creator + Claude prompt → python-pptx filler |
| `agents/orchestrator.py` | Sequences Research → Analysis → Deck, returns output paths |
| `main.py` | Streamlit UI: form, status feed, download buttons |
| `fixtures/sample_comps.json` | Pre-scraped fallback data for demo safety |
| `tests/test_models.py` | Pydantic model validation tests |
| `tests/test_research.py` | Research agent with mocked kernel.sh + PitchBook |
| `tests/test_analysis.py` | Analysis agent with mocked Claude + Excel output verification |
| `tests/test_deck.py` | Deck agent with mocked Claude + PPTX output verification |
| `tests/test_orchestrator.py` | Orchestrator with all agents mocked |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `agents/__init__.py`
- Create: `tests/__init__.py`
- Create: `outputs/.gitkeep`
- Create: `fixtures/.gitkeep`

- [ ] **Step 1: Create `requirements.txt`**

```
anthropic==0.49.0
playwright==1.51.0
openpyxl==3.1.5
python-pptx==1.0.2
streamlit==1.44.0
pydantic==2.11.1
python-dotenv==1.1.0
requests==2.32.3
pytest==8.3.5
pytest-mock==3.14.0
```

- [ ] **Step 2: Create `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-...
PITCHBOOK_USER=your_university_email@school.edu
PITCHBOOK_PASS=your_pitchbook_password
KERNEL_SH_API_KEY=your_kernel_sh_api_key
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
outputs/
__pycache__/
*.pyc
.pytest_cache/
*.pptx
*.xlsx
```

- [ ] **Step 4: Create empty `__init__.py` files and placeholder dirs**

```bash
mkdir -p agents tests outputs fixtures
touch agents/__init__.py tests/__init__.py outputs/.gitkeep fixtures/.gitkeep
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected output: all packages install without error, `chromium` browser downloaded.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore agents/__init__.py tests/__init__.py outputs/.gitkeep fixtures/.gitkeep
git commit -m "feat: project scaffolding and dependencies"
```

---

## Task 2: Shared Data Models

**Files:**
- Create: `agents/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_models.py`:

```python
import pytest
from agents.models import CompRecord, ValuationRange, DeckContent, Slide, ExcelInstructions, CellWrite


def test_comp_record_valid():
    comp = CompRecord(
        name="Acme Corp",
        sector="Fintech",
        stage="Series B",
        valuation_usd=120_000_000,
        arr_usd=15_000_000,
        ebitda_usd=-2_000_000,
        last_funding_round="Series B",
        last_funding_amount_usd=30_000_000,
        lead_investors=["Sequoia", "a16z"],
    )
    assert comp.ev_to_arr == pytest.approx(8.0)
    assert comp.name == "Acme Corp"


def test_comp_record_ev_to_arr_none_when_no_arr():
    comp = CompRecord(
        name="Stealth Co",
        sector="SaaS",
        stage="Seed",
        valuation_usd=10_000_000,
        arr_usd=None,
        ebitda_usd=None,
        last_funding_round="Seed",
        last_funding_amount_usd=2_000_000,
        lead_investors=[],
    )
    assert comp.ev_to_arr is None


def test_valuation_range():
    vr = ValuationRange(low=50_000_000, mid=75_000_000, high=100_000_000, methodology="EV/ARR")
    assert vr.mid == 75_000_000


def test_deck_content_has_six_slides():
    slides = [
        Slide(title=f"Slide {i}", bullets=["bullet 1", "bullet 2"])
        for i in range(6)
    ]
    deck = DeckContent(company_name="Acme", tagline="Payments simplified", slides=slides)
    assert len(deck.slides) == 6


def test_deck_content_rejects_wrong_slide_count():
    slides = [Slide(title="Only one", bullets=["x"])]
    with pytest.raises(Exception):
        DeckContent(company_name="Acme", tagline="tag", slides=slides)


def test_cell_write():
    cw = CellWrite(sheet="Comps", cell="A1", value="Company", bold=True)
    assert cw.sheet == "Comps"
    assert cw.bold is True


def test_excel_instructions():
    ei = ExcelInstructions(
        sheets=["Comps", "Multiples", "Valuation"],
        writes=[CellWrite(sheet="Comps", cell="A1", value="Company")],
        column_widths={"Comps": {"A": 25.0}},
    )
    assert "Comps" in ei.sheets
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError` — `agents.models` does not exist yet.

- [ ] **Step 3: Write `agents/models.py`**

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, model_validator


class CompRecord(BaseModel):
    name: str
    sector: str
    stage: str
    valuation_usd: Optional[float]
    arr_usd: Optional[float]
    ebitda_usd: Optional[float]
    last_funding_round: str
    last_funding_amount_usd: Optional[float]
    lead_investors: list[str]

    @property
    def ev_to_arr(self) -> Optional[float]:
        if self.valuation_usd and self.arr_usd and self.arr_usd > 0:
            return round(self.valuation_usd / self.arr_usd, 2)
        return None

    @property
    def ev_to_ebitda(self) -> Optional[float]:
        if self.valuation_usd and self.ebitda_usd and self.ebitda_usd > 0:
            return round(self.valuation_usd / self.ebitda_usd, 2)
        return None


class ValuationRange(BaseModel):
    low: float
    mid: float
    high: float
    methodology: str  # e.g. "EV/ARR", "EV/EBITDA"


class Slide(BaseModel):
    title: str
    bullets: list[str]
    notes: Optional[str] = None


class DeckContent(BaseModel):
    company_name: str
    tagline: str
    slides: list[Slide]

    @model_validator(mode="after")
    def must_have_six_slides(self) -> "DeckContent":
        if len(self.slides) != 6:
            raise ValueError(f"DeckContent must have exactly 6 slides, got {len(self.slides)}")
        return self


class CellWrite(BaseModel):
    sheet: str
    cell: str          # e.g. "A1", "B3"
    value: str | float | int | None = None
    formula: Optional[str] = None  # e.g. "=AVERAGE(B2:B10)"
    bold: bool = False
    bg_color: Optional[str] = None  # hex without #, e.g. "4472C4"
    number_format: Optional[str] = None  # e.g. "#,##0.0x", "$#,##0"


class ExcelInstructions(BaseModel):
    sheets: list[str]
    writes: list[CellWrite]
    column_widths: dict[str, dict[str, float]]  # sheet -> column_letter -> width
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/models.py tests/test_models.py
git commit -m "feat: shared pydantic data models for agent interfaces"
```

---

## Task 3: Research Agent (kernel.sh + Playwright + PitchBook)

**Files:**
- Create: `agents/research.py`
- Create: `tests/test_research.py`

> **Note:** Check kernel.sh docs for the exact API endpoint and response shape. The implementation below uses the standard browser-as-a-service pattern (POST to create session, returns `cdpUrl` + `id`). Adjust `KERNEL_SH_BASE_URL` and response keys if their API differs.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_research.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
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
        "https://api.kernel.sh/v1/sessions",
        json={"id": "sess_abc123", "cdpUrl": "wss://browser.kernel.sh/sess_abc123"},
    )
    session_id, cdp_url = create_kernel_session(api_key="test_key")
    assert session_id == "sess_abc123"
    assert cdp_url == "wss://browser.kernel.sh/sess_abc123"


def test_destroy_kernel_session(requests_mock):
    requests_mock.delete(
        "https://api.kernel.sh/v1/sessions/sess_abc123",
        json={"deleted": True},
    )
    # Should not raise
    destroy_kernel_session(api_key="test_key", session_id="sess_abc123")


def test_scrape_pitchbook_comps_returns_comp_records(tmp_path, monkeypatch):
    """Uses pre-saved fixture JSON to bypass live browser call."""
    fixture_path = tmp_path / "comps.json"
    fixture_path.write_text(json.dumps(MOCK_COMPS_JSON))

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_research.py -v
```

Expected: `ImportError` — `agents.research` does not exist yet.

- [ ] **Step 3: Install `requests-mock` for tests**

```bash
pip install requests-mock pytest-requests-mock
echo "requests-mock==1.12.1" >> requirements.txt
```

- [ ] **Step 4: Write `agents/research.py`**

```python
"""Research Agent: creates a kernel.sh browser session, scrapes PitchBook comps."""
from __future__ import annotations

import os
import time
from typing import Any

import requests
from playwright.sync_api import sync_playwright

from agents.models import CompRecord

KERNEL_SH_BASE_URL = "https://api.kernel.sh/v1"
PITCHBOOK_SEARCH_URL = "https://pitchbook.com/profiles/investor"


def create_kernel_session(api_key: str) -> tuple[str, str]:
    """POST to kernel.sh to create a browser session. Returns (session_id, cdp_url)."""
    resp = requests.post(
        f"{KERNEL_SH_BASE_URL}/sessions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"browser": "chromium", "timeout": 120},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"], data["cdpUrl"]


def destroy_kernel_session(api_key: str, session_id: str) -> None:
    """DELETE the kernel.sh session to free resources."""
    requests.delete(
        f"{KERNEL_SH_BASE_URL}/sessions/{session_id}",
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

        # --- Login ---
        page.goto("https://pitchbook.com/login", wait_until="networkidle")
        # Handle SSO: click "Sign in with SSO" if present
        sso_btn = page.query_selector("text=Sign in with SSO")
        if sso_btn:
            sso_btn.click()
            page.wait_for_load_state("networkidle")

        page.fill("input[name='email'], input[type='email']", pitchbook_user)
        page.fill("input[name='password'], input[type='password']", pitchbook_pass)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # --- Navigate to company search ---
        page.goto(
            "https://pitchbook.com/platform/search#entities=company",
            wait_until="networkidle",
        )
        time.sleep(2)

        # --- Apply sector filter ---
        # PitchBook filter sidebar: click "Sector" and select matching option
        sector_filter = page.query_selector("text=Sector")
        if sector_filter:
            sector_filter.click()
            page.wait_for_selector("input[placeholder*='Search']", timeout=5000)
            page.fill("input[placeholder*='Search']", sector)
            option = page.query_selector(f"text={sector}")
            if option:
                option.click()
            time.sleep(1)

        # --- Apply stage filter ---
        stage_filter = page.query_selector("text=Deal Stage")
        if stage_filter:
            stage_filter.click()
            option = page.query_selector(f"text={stage}")
            if option:
                option.click()
            time.sleep(1)

        # --- Scrape results table ---
        page.wait_for_selector("table, [data-testid='results-table']", timeout=10000)
        rows = page.query_selector_all("tr[data-company-id], tbody tr")

        for row in rows[:12]:  # cap at 12 comps
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
    status_callback=None,
) -> list[CompRecord]:
    """
    Top-level entry point called by the orchestrator.
    Creates a kernel.sh session, scrapes PitchBook, destroys session.
    status_callback(msg: str) is called with progress updates.
    """
    api_key = os.environ["KERNEL_SH_API_KEY"]
    pb_user = os.environ["PITCHBOOK_USER"]
    pb_pass = os.environ["PITCHBOOK_PASS"]

    if status_callback:
        status_callback("Research Agent: creating kernel.sh browser session...")
    session_id, cdp_url = create_kernel_session(api_key)

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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_research.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agents/research.py tests/test_research.py requirements.txt
git commit -m "feat: research agent with kernel.sh session management and PitchBook scraper"
```

---

## Task 4: Analysis Agent (Claude → openpyxl Excel)

**Files:**
- Create: `agents/analysis.py`
- Create: `tests/test_analysis.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analysis.py`:

```python
import os
import pytest
from unittest.mock import patch, MagicMock
from agents.analysis import build_excel_model, run_analysis_agent
from agents.models import CompRecord, ValuationRange, ExcelInstructions, CellWrite


SAMPLE_COMPS = [
    CompRecord(
        name="Stripe",
        sector="Fintech",
        stage="Series B",
        valuation_usd=65_000_000_000,
        arr_usd=3_000_000_000,
        ebitda_usd=None,
        last_funding_round="Series I",
        last_funding_amount_usd=600_000_000,
        lead_investors=["Sequoia"],
    ),
    CompRecord(
        name="Brex",
        sector="Fintech",
        stage="Series C",
        valuation_usd=12_300_000_000,
        arr_usd=500_000_000,
        ebitda_usd=None,
        last_funding_round="Series C",
        last_funding_amount_usd=300_000_000,
        lead_investors=["Tiger Global"],
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
    import openpyxl
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analysis.py -v
```

Expected: `ImportError` — `agents.analysis` does not exist yet.

- [ ] **Step 3: Write `agents/analysis.py`**

```python
"""Analysis Agent: prompts Claude to design an Excel comps model, writes it with openpyxl."""
from __future__ import annotations

import json
import os
from typing import Optional

import anthropic
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from agents.models import CompRecord, ValuationRange, ExcelInstructions, CellWrite

SYSTEM_PROMPT = """You are a senior investment banker specializing in early-stage startup valuations.
Given a list of comparable companies and a startup description, you will return JSON instructions
for building a 3-tab Excel model: Comps, Multiples, and Valuation.

Return ONLY valid JSON matching the ExcelInstructions schema. No prose, no markdown, just JSON.

ExcelInstructions schema:
{
  "sheets": ["Comps", "Multiples", "Valuation"],
  "writes": [
    {"sheet": "Comps", "cell": "A1", "value": "Company", "bold": true},
    ...
  ],
  "column_widths": {"Comps": {"A": 25.0, "B": 15.0}, ...}
}

Rules:
- Tab 1 (Comps): header row + one row per comp. Columns: Company, Valuation ($M), ARR ($M), EV/ARR, Last Round, Lead Investors
- Tab 2 (Multiples): summary stats — median/mean/high/low for EV/ARR and EV/EBITDA across comps
- Tab 3 (Valuation): implied value range for the target startup. Use median multiple × target ARR. Show Low (25th pct), Mid (median), High (75th pct).
- Use bold for header rows. Use bg_color "4472C4" (blue) for header cells.
- Format valuation cells with number_format "$#,##0"
- Format multiple cells with number_format "#,##0.0x"
"""


def call_claude_for_excel_instructions(
    comps: list[CompRecord],
    startup_description: str,
) -> ExcelInstructions:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    comps_json = json.dumps([c.model_dump() for c in comps], indent=2)
    user_msg = f"""Comparable companies:
{comps_json}

Target startup description:
{startup_description}

Return the ExcelInstructions JSON to build the 3-tab comps model."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return ExcelInstructions.model_validate_json(raw.strip())


def build_excel_model(instructions: ExcelInstructions, output_path: str) -> None:
    """Execute ExcelInstructions to write an .xlsx file at output_path."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    for sheet_name in instructions.sheets:
        wb.create_sheet(sheet_name)

    for write in instructions.writes:
        ws = wb[write.sheet]
        cell = ws[write.cell]

        if write.formula:
            cell.value = write.formula
        elif write.value is not None:
            cell.value = write.value

        if write.bold:
            cell.font = Font(bold=True, color="FFFFFF" if write.bg_color else "000000")

        if write.bg_color:
            cell.fill = PatternFill(
                start_color=write.bg_color,
                end_color=write.bg_color,
                fill_type="solid",
            )

        if write.number_format:
            cell.number_format = write.number_format

    for sheet_name, cols in instructions.column_widths.items():
        ws = wb[sheet_name]
        for col_letter, width in cols.items():
            ws.column_dimensions[col_letter].width = width

    wb.save(output_path)


def _extract_valuation_range(instructions: ExcelInstructions) -> ValuationRange:
    """Read Low/Mid/High rows from Valuation sheet instructions."""
    val_writes = {w.cell: w for w in instructions.writes if w.sheet == "Valuation"}
    low = mid = high = 0.0
    for row_idx in range(2, 20):
        label_cell = f"A{row_idx}"
        val_cell = f"B{row_idx}"
        label_write = val_writes.get(label_cell)
        val_write = val_writes.get(val_cell)
        if not label_write or not val_write:
            continue
        label = str(label_write.value or "").strip().lower()
        val = val_write.value
        if isinstance(val, (int, float)):
            if label == "low":
                low = float(val)
            elif label == "mid":
                mid = float(val)
            elif label == "high":
                high = float(val)
    return ValuationRange(low=low, mid=mid, high=high, methodology="EV/ARR")


def run_analysis_agent(
    comps: list[CompRecord],
    startup_description: str,
    output_path: str,
    status_callback=None,
) -> tuple[ValuationRange, str]:
    """
    Top-level entry point called by the orchestrator.
    Returns (valuation_range, output_path).
    """
    if status_callback:
        status_callback("Analysis Agent: asking Claude to design Excel model...")

    instructions = call_claude_for_excel_instructions(comps, startup_description)

    if status_callback:
        status_callback("Analysis Agent: writing Excel file...")

    build_excel_model(instructions, output_path)
    valuation_range = _extract_valuation_range(instructions)

    if status_callback:
        status_callback(f"Analysis Agent: done. Valuation range: ${valuation_range.low/1e6:.0f}M–${valuation_range.high/1e6:.0f}M")

    return valuation_range, output_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_analysis.py -v
```

Expected: all 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/analysis.py tests/test_analysis.py
git commit -m "feat: analysis agent - Claude-generated Excel comps model via openpyxl"
```

---

## Task 5: Deck Agent (Claude → python-pptx)

**Files:**
- Create: `agents/deck.py`
- Create: `templates/base_deck.pptx` (generated programmatically)
- Create: `tests/test_deck.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deck.py`:

```python
import pytest
from unittest.mock import patch
from agents.deck import create_base_template, fill_deck, run_deck_agent
from agents.models import ValuationRange, DeckContent, Slide
from pptx import Presentation


SAMPLE_VALUATION = ValuationRange(low=40_000_000, mid=60_000_000, high=80_000_000, methodology="EV/ARR")

MOCK_DECK_CONTENT = DeckContent(
    company_name="PayFlow",
    tagline="Instant B2B payments for SMBs",
    slides=[
        Slide(title="PayFlow", bullets=["Instant B2B payments", "Seed Stage", "Founded 2024"]),
        Slide(title="Problem", bullets=["SMBs wait 45 days for invoices to clear", "Cash flow crisis kills 30% of SMBs"]),
        Slide(title="Solution", bullets=["Real-time payment rails", "Auto-reconciliation", "1-click payouts"]),
        Slide(title="Market Size", bullets=["TAM: $850B global B2B payments", "SAM: $120B US SMB segment", "SOM: $1.2B reachable in 5 years"]),
        Slide(title="Competitive Landscape", bullets=["vs Stripe: SMB-focused, lower fees", "vs Brex: payments-first, not cards", "Median comp EV/ARR: 8x"]),
        Slide(title="Valuation & Ask", bullets=["Raising $3M Seed", "Post-money: $15M", "Comparable range: $40M–$80M at scale"]),
    ],
)


def test_create_base_template_creates_pptx(tmp_path):
    path = str(tmp_path / "base.pptx")
    create_base_template(path)
    prs = Presentation(path)
    assert len(prs.slides) == 0  # blank template, slides added later


def test_fill_deck_creates_six_slides(tmp_path):
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)
    fill_deck(MOCK_DECK_CONTENT, template_path, output_path)
    prs = Presentation(output_path)
    assert len(prs.slides) == 6


def test_fill_deck_slide_titles_match(tmp_path):
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)
    fill_deck(MOCK_DECK_CONTENT, template_path, output_path)
    prs = Presentation(output_path)
    titles = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame and shape.shape_type == 13 or "title" in shape.name.lower():
                titles.append(shape.text_frame.text)
                break
    assert len(titles) == 6


def test_run_deck_agent_calls_claude_and_fills_pptx(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)

    with patch("agents.deck.call_claude_for_deck_content", return_value=MOCK_DECK_CONTENT):
        result_path = run_deck_agent(
            startup_description="PayFlow: B2B payments for SMBs, $1M ARR, Seed stage",
            valuation_range=SAMPLE_VALUATION,
            top_comps_summary="Stripe 21x, Brex 24x, Adyen 18x, median 21x EV/ARR",
            template_path=template_path,
            output_path=output_path,
        )

    prs = Presentation(result_path)
    assert len(prs.slides) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_deck.py -v
```

Expected: `ImportError` — `agents.deck` does not exist yet.

- [ ] **Step 3: Write `agents/deck.py`**

```python
"""Deck Agent: prompts Claude for slide content, fills a python-pptx template."""
from __future__ import annotations

import json
import os

import anthropic
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from agents.models import ValuationRange, DeckContent, Slide

DECK_SYSTEM_PROMPT = """You are a top-tier startup pitch deck writer with experience at Y Combinator.
Given a startup description, valuation range, and comparable companies, generate compelling slide content.

Return ONLY valid JSON matching this schema (no markdown, no prose):
{
  "company_name": "string",
  "tagline": "string (under 10 words)",
  "slides": [
    {"title": "string", "bullets": ["string", ...], "notes": "string or null"},
    ... (exactly 6 slides)
  ]
}

Slides must be in this exact order:
1. Cover: company name, tagline, stage, founding year
2. Problem: 2-3 crisp bullets on the pain point with market data
3. Solution: 2-3 bullets on what you built and why it's better
4. Market Size: TAM / SAM / SOM with dollar figures
5. Competitive Landscape: how you compare to top comps, reference the EV/ARR multiples
6. Valuation & Ask: fundraise amount, use of funds, implied valuation range from comps
"""


def call_claude_for_deck_content(
    startup_description: str,
    valuation_range: ValuationRange,
    top_comps_summary: str,
) -> DeckContent:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_msg = f"""Startup description: {startup_description}

Valuation range from comps analysis:
  Low: ${valuation_range.low / 1e6:.1f}M
  Mid: ${valuation_range.mid / 1e6:.1f}M
  High: ${valuation_range.high / 1e6:.1f}M
  Methodology: {valuation_range.methodology}

Top comparable companies: {top_comps_summary}

Generate the 6-slide pitch deck JSON."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=DECK_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return DeckContent.model_validate_json(raw.strip())


def create_base_template(output_path: str) -> None:
    """Create a minimal blank .pptx template (no slides, dark theme)."""
    prs = Presentation()
    # Widescreen 16:9
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    prs.save(output_path)


def fill_deck(content: DeckContent, template_path: str, output_path: str) -> None:
    """Add 6 slides to the template, one per DeckContent slide."""
    prs = Presentation(template_path)
    blank_layout = prs.slide_layouts[6]  # completely blank layout

    BG_COLOR = RGBColor(0x0D, 0x1B, 0x2A)      # dark navy
    TITLE_COLOR = RGBColor(0xFF, 0xFF, 0xFF)    # white
    BODY_COLOR = RGBColor(0xCC, 0xDD, 0xEE)     # light blue-white
    ACCENT_COLOR = RGBColor(0x44, 0x72, 0xC4)   # blue

    for slide_data in content.slides:
        slide = prs.slides.add_slide(blank_layout)

        # Background
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR

        # Title text box
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12.3), Inches(1.2))
        title_tf = title_box.text_frame
        title_tf.word_wrap = True
        title_para = title_tf.paragraphs[0]
        title_para.text = slide_data.title
        title_run = title_para.runs[0]
        title_run.font.size = Pt(36)
        title_run.font.bold = True
        title_run.font.color.rgb = TITLE_COLOR

        # Accent line under title
        from pptx.util import Emu
        line = slide.shapes.add_shape(
            1,  # MSO_SHAPE_TYPE.RECTANGLE
            Inches(0.5), Inches(1.55), Inches(12.3), Emu(45720),  # 0.05 inch tall
        )
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT_COLOR
        line.line.fill.background()

        # Bullets text box
        body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(12.3), Inches(5.2))
        body_tf = body_box.text_frame
        body_tf.word_wrap = True

        for i, bullet in enumerate(slide_data.bullets):
            if i == 0:
                para = body_tf.paragraphs[0]
            else:
                para = body_tf.add_paragraph()
            para.text = f"• {bullet}"
            run = para.runs[0]
            run.font.size = Pt(22)
            run.font.color.rgb = BODY_COLOR
            para.space_after = Pt(10)

    prs.save(output_path)


def run_deck_agent(
    startup_description: str,
    valuation_range: ValuationRange,
    top_comps_summary: str,
    template_path: str,
    output_path: str,
    status_callback=None,
) -> str:
    """Top-level entry point called by the orchestrator. Returns output_path."""
    if status_callback:
        status_callback("Deck Agent: asking Claude to write slide content...")

    content = call_claude_for_deck_content(startup_description, valuation_range, top_comps_summary)

    if status_callback:
        status_callback("Deck Agent: building PowerPoint...")

    fill_deck(content, template_path, output_path)

    if status_callback:
        status_callback("Deck Agent: done. Pitch deck ready.")

    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_deck.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/deck.py tests/test_deck.py
git commit -m "feat: deck agent - Claude slide content generation and python-pptx writer"
```

---

## Task 6: Orchestrator

**Files:**
- Create: `agents/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from agents.orchestrator import run_pipeline
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
         patch("agents.orchestrator.run_deck_agent", return_value=str(tmp_path / "deck.pptx")):

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
         patch("agents.orchestrator.run_deck_agent", return_value=str(tmp_path / "deck.pptx")):

        run_pipeline(
            startup_name="PayFlow", sector="Fintech", stage="Series B",
            description="test", output_dir=str(tmp_path),
        )

    mock_fallback.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: `ImportError` — `agents.orchestrator` does not exist yet.

- [ ] **Step 3: Write `agents/orchestrator.py`**

```python
"""Orchestrator: sequences Research → Analysis → Deck agents."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Optional

from agents.models import CompRecord, ValuationRange
from agents.research import run_research_agent
from agents.analysis import run_analysis_agent
from agents.deck import run_deck_agent, create_base_template

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "sample_comps.json"
TEMPLATES_PATH = Path(__file__).parent.parent / "templates" / "base_deck.pptx"


def load_fallback_comps(sector: str) -> list[CompRecord]:
    """Load pre-scraped fixture data when PitchBook scrape returns nothing."""
    if FIXTURES_PATH.exists():
        raw = json.loads(FIXTURES_PATH.read_text())
        return [CompRecord(**r) for r in raw]
    return []


def _comps_summary(comps: list[CompRecord]) -> str:
    parts = []
    for c in comps[:5]:
        if c.ev_to_arr:
            parts.append(f"{c.name} {c.ev_to_arr:.1f}x EV/ARR")
    return ", ".join(parts) if parts else "No EV/ARR data available"


def run_pipeline(
    startup_name: str,
    sector: str,
    stage: str,
    description: str,
    output_dir: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> dict[str, str]:
    """
    Run the full Research → Analysis → Deck pipeline.
    Returns {"excel_path": "...", "pptx_path": "..."}.
    """
    def _status(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    startup_prompt = f"{startup_name}: {description} (Sector: {sector}, Stage: {stage})"
    excel_path = str(output_dir_path / f"{startup_name.replace(' ', '_')}_comps.xlsx")
    pptx_path = str(output_dir_path / f"{startup_name.replace(' ', '_')}_pitch_deck.pptx")

    # Ensure base template exists
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TEMPLATES_PATH.exists():
        create_base_template(str(TEMPLATES_PATH))

    # --- Step 1: Research ---
    _status("Starting Research Agent...")
    comps = run_research_agent(sector=sector, stage=stage, status_callback=_status)

    if not comps:
        _status("No comps found — loading fallback fixtures...")
        comps = load_fallback_comps(sector)

    # --- Step 2: Analysis ---
    _status("Starting Analysis Agent...")
    valuation_range, excel_path = run_analysis_agent(
        comps=comps,
        startup_description=startup_prompt,
        output_path=excel_path,
        status_callback=_status,
    )

    # --- Step 3: Deck ---
    _status("Starting Deck Agent...")
    pptx_path = run_deck_agent(
        startup_description=startup_prompt,
        valuation_range=valuation_range,
        top_comps_summary=_comps_summary(comps),
        template_path=str(TEMPLATES_PATH),
        output_path=pptx_path,
        status_callback=_status,
    )

    _status("Pipeline complete!")
    return {"excel_path": excel_path, "pptx_path": pptx_path}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: all 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator sequences research, analysis, and deck agents with fallback"
```

---

## Task 7: Fallback Fixtures

**Files:**
- Create: `fixtures/sample_comps.json`

- [ ] **Step 1: Create `fixtures/sample_comps.json` with real fintech comps**

```json
[
  {
    "name": "Brex",
    "sector": "Fintech",
    "stage": "Series C",
    "valuation_usd": 12300000000,
    "arr_usd": 500000000,
    "ebitda_usd": null,
    "last_funding_round": "Series C",
    "last_funding_amount_usd": 300000000,
    "lead_investors": ["Tiger Global", "Greenoaks"]
  },
  {
    "name": "Ramp",
    "sector": "Fintech",
    "stage": "Series D",
    "valuation_usd": 7650000000,
    "arr_usd": 300000000,
    "ebitda_usd": null,
    "last_funding_round": "Series D",
    "last_funding_amount_usd": 750000000,
    "lead_investors": ["Founders Fund", "Thrive Capital"]
  },
  {
    "name": "Plaid",
    "sector": "Fintech",
    "stage": "Late Stage",
    "valuation_usd": 13400000000,
    "arr_usd": 400000000,
    "ebitda_usd": null,
    "last_funding_round": "Series D",
    "last_funding_amount_usd": 425000000,
    "lead_investors": ["Altimeter", "Silver Lake"]
  },
  {
    "name": "Checkout.com",
    "sector": "Fintech",
    "stage": "Late Stage",
    "valuation_usd": 40000000000,
    "arr_usd": 1000000000,
    "ebitda_usd": null,
    "last_funding_round": "Series D",
    "last_funding_amount_usd": 1000000000,
    "lead_investors": ["Tiger Global", "Insight Partners"]
  },
  {
    "name": "Marqeta",
    "sector": "Fintech",
    "stage": "Public",
    "valuation_usd": 3500000000,
    "arr_usd": 850000000,
    "ebitda_usd": -120000000,
    "last_funding_round": "IPO",
    "last_funding_amount_usd": 1200000000,
    "lead_investors": ["Visa", "Goldman Sachs"]
  }
]
```

- [ ] **Step 2: Remove `.gitkeep` and commit fixtures**

```bash
rm fixtures/.gitkeep
git add fixtures/sample_comps.json
git commit -m "feat: add fallback comp fixtures for demo safety"
```

---

## Task 8: Streamlit UI

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write `main.py`**

```python
"""Streamlit UI: startup analysis agent front-end."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agents.orchestrator import run_pipeline

OUTPUT_DIR = "outputs"

st.set_page_config(
    page_title="Startup Analysis Agent",
    page_icon="📊",
    layout="centered",
)

st.title("Startup Analysis Agent")
st.caption("Enter a startup → get a comps Excel model + pitch deck PowerPoint")

with st.form("startup_form"):
    startup_name = st.text_input("Startup Name", placeholder="e.g. PayFlow")
    sector = st.selectbox(
        "Sector",
        ["Fintech", "SaaS", "HealthTech", "EdTech", "E-commerce", "AI/ML", "Dev Tools", "Other"],
    )
    stage = st.selectbox(
        "Stage",
        ["Pre-Seed", "Seed", "Series A", "Series B", "Series C", "Late Stage"],
    )
    description = st.text_area(
        "Brief Description (2-3 sentences)",
        placeholder="e.g. PayFlow processes B2B payments for SMBs with real-time settlement. Currently at $1M ARR, growing 20% MoM.",
        height=100,
    )
    submitted = st.form_submit_button("Run Analysis", type="primary")

if submitted:
    if not startup_name or not description:
        st.error("Please fill in startup name and description.")
    else:
        status_box = st.empty()
        progress_log = st.expander("Agent Log", expanded=True)
        log_lines: list[str] = []

        def update_status(msg: str) -> None:
            log_lines.append(msg)
            with progress_log:
                for line in log_lines:
                    st.write(f"→ {line}")
            status_box.info(msg)

        with st.spinner("Running pipeline..."):
            try:
                result = run_pipeline(
                    startup_name=startup_name,
                    sector=sector,
                    stage=stage,
                    description=description,
                    output_dir=OUTPUT_DIR,
                    status_callback=update_status,
                )

                st.success("Analysis complete!")

                col1, col2 = st.columns(2)

                excel_path = result["excel_path"]
                pptx_path = result["pptx_path"]

                with col1:
                    if Path(excel_path).exists():
                        with open(excel_path, "rb") as f:
                            st.download_button(
                                label="Download Comps Model (.xlsx)",
                                data=f,
                                file_name=Path(excel_path).name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                with col2:
                    if Path(pptx_path).exists():
                        with open(pptx_path, "rb") as f:
                            st.download_button(
                                label="Download Pitch Deck (.pptx)",
                                data=f,
                                file_name=Path(pptx_path).name,
                                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            )

            except Exception as e:
                st.error(f"Pipeline failed: {e}")
                raise
```

- [ ] **Step 2: Create `.env` from `.env.example` and fill in real keys**

```bash
cp .env.example .env
# Edit .env and add your real ANTHROPIC_API_KEY, PITCHBOOK_USER, PITCHBOOK_PASS, KERNEL_SH_API_KEY
```

- [ ] **Step 3: Run the app to verify it loads**

```bash
streamlit run main.py
```

Expected: browser opens at `http://localhost:8501`, form is visible, no import errors.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: streamlit UI with input form, agent status log, and file downloads"
```

---

## Task 9: End-to-End Integration Test

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run a live pipeline test with a real startup**

Open `http://localhost:8501` and submit:
- Startup Name: `Stripe` (or any fintech startup you know)
- Sector: `Fintech`
- Stage: `Series B`
- Description: `A payments infrastructure company processing online transactions for businesses. Currently processing $1T+ annually with $3B ARR.`

Expected: both download buttons appear within ~2 minutes. Open `.xlsx` — verify 3 tabs with data. Open `.pptx` — verify 6 slides with content.

- [ ] **Step 3: Verify fallback works if PitchBook fails**

Temporarily set `PITCHBOOK_USER=bad@email.com` in `.env`, re-run. Confirm fallback fixtures are used (agent log shows "loading fallback fixtures").

Restore correct credentials.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: end-to-end integration verified"
```

---

## Quick Reference: Running Locally

```bash
# Install
pip install -r requirements.txt
playwright install chromium

# Configure
cp .env.example .env  # fill in your keys

# Test
pytest tests/ -v

# Run
streamlit run main.py
```
