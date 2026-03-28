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
        Slide(title="Problem", bullets=["SMBs wait 45 days for invoices", "Cash flow kills 30% of SMBs"]),
        Slide(title="Solution", bullets=["Real-time payment rails", "Auto-reconciliation", "1-click payouts"]),
        Slide(title="Market Size", bullets=["TAM: $850B global B2B payments", "SAM: $120B US SMB", "SOM: $1.2B"]),
        Slide(title="Competitive Landscape", bullets=["vs Stripe: SMB-focused", "vs Brex: payments-first", "Median EV/ARR: 8x"]),
        Slide(title="Valuation & Ask", bullets=["Raising $3M Seed", "Post-money: $15M", "Comp range: $40M–$80M"]),
    ],
)


def test_create_base_template_creates_pptx(tmp_path):
    path = str(tmp_path / "base.pptx")
    create_base_template(path)
    prs = Presentation(path)
    # blank template — slides are added by fill_deck
    assert prs.slide_width is not None


def test_fill_deck_creates_six_slides(tmp_path):
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)
    fill_deck(MOCK_DECK_CONTENT, template_path, output_path)
    prs = Presentation(output_path)
    assert len(prs.slides) == 6


def test_fill_deck_slide_content_present(tmp_path):
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)
    fill_deck(MOCK_DECK_CONTENT, template_path, output_path)
    prs = Presentation(output_path)
    # Collect all text from all slides
    all_text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                all_text.append(shape.text_frame.text)
    combined = " ".join(all_text)
    assert "PayFlow" in combined
    assert "Problem" in combined


def test_run_deck_agent_produces_pptx(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    template_path = str(tmp_path / "base.pptx")
    output_path = str(tmp_path / "deck.pptx")
    create_base_template(template_path)

    with patch("agents.deck.call_claude_for_deck_content", return_value=MOCK_DECK_CONTENT):
        result_path = run_deck_agent(
            startup_description="PayFlow: B2B payments for SMBs, $1M ARR, Seed stage",
            valuation_range=SAMPLE_VALUATION,
            top_comps_summary="Stripe 21x, Brex 24x, median 21x EV/ARR",
            template_path=template_path,
            output_path=output_path,
        )

    prs = Presentation(result_path)
    assert len(prs.slides) == 6
