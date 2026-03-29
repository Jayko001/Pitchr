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
    kernel_session_id: Optional[str] = None,
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
    safe_name = startup_name.replace(" ", "_")
    excel_path = str(output_dir_path / f"{safe_name}_comps.xlsx")
    pptx_path = str(output_dir_path / f"{safe_name}_pitch_deck.pptx")

    # Ensure base template exists
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TEMPLATES_PATH.exists():
        create_base_template(str(TEMPLATES_PATH))

    # Step 1: Research
    _status("Starting Research Agent...")
    comps = run_research_agent(
        sector=sector,
        stage=stage,
        description=description,
        kernel_session_id=kernel_session_id,
        status_callback=_status,
    )

    if not comps:
        _status("No comps found — loading fallback fixtures...")
        comps = load_fallback_comps(sector)

    # Step 2: Analysis
    _status("Starting Analysis Agent...")
    valuation_range, excel_path = run_analysis_agent(
        comps=comps,
        startup_description=startup_prompt,
        output_path=excel_path,
        status_callback=_status,
    )

    # Step 3: Deck
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
