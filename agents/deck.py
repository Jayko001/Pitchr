"""Deck Agent: prompts Claude for slide content, fills a python-pptx template."""
from __future__ import annotations

import os
from typing import Optional, Callable

import anthropic
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor

from agents.models import ValuationRange, DeckContent, Slide

DECK_SYSTEM_PROMPT = """You are a top-tier startup pitch deck writer.
Given a startup description, valuation range, and comparable companies, generate compelling slide content.

Return ONLY valid JSON matching this schema (no markdown, no prose):
{
  "company_name": "string",
  "tagline": "string (under 10 words)",
  "slides": [
    {"title": "string", "bullets": ["string", ...], "notes": null},
    ... (exactly 6 slides)
  ]
}

Slides must be in this exact order:
1. Cover: company name, tagline, stage, founding year
2. Problem: 2-3 crisp bullets with market data
3. Solution: 2-3 bullets on what you built
4. Market Size: TAM / SAM / SOM with dollar figures
5. Competitive Landscape: comparison to top comps, reference EV/ARR multiples
6. Valuation & Ask: fundraise amount, use of funds, valuation range from comps
"""


def call_claude_for_deck_content(
    startup_description: str,
    valuation_range: ValuationRange,
    top_comps_summary: str,
) -> DeckContent:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_msg = f"""Startup description: {startup_description}

Valuation range from comps:
  Low: ${valuation_range.low / 1e6:.1f}M
  Mid: ${valuation_range.mid / 1e6:.1f}M
  High: ${valuation_range.high / 1e6:.1f}M
  Methodology: {valuation_range.methodology}

Top comps: {top_comps_summary}

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
    """Create a minimal blank .pptx template (16:9, no slides)."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    prs.save(output_path)


def fill_deck(content: DeckContent, template_path: str, output_path: str) -> None:
    """Add 6 slides to the template, one per DeckContent slide."""
    prs = Presentation(template_path)
    blank_layout = prs.slide_layouts[6]  # blank layout

    BG_COLOR = RGBColor(0x0D, 0x1B, 0x2A)
    TITLE_COLOR = RGBColor(0xFF, 0xFF, 0xFF)
    BODY_COLOR = RGBColor(0xCC, 0xDD, 0xEE)
    ACCENT_COLOR = RGBColor(0x44, 0x72, 0xC4)

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
        run = title_para.runs[0]
        run.font.size = Pt(36)
        run.font.bold = True
        run.font.color.rgb = TITLE_COLOR

        # Accent line under title
        line = slide.shapes.add_shape(
            1,  # MSO_SHAPE_TYPE.RECTANGLE
            Inches(0.5), Inches(1.55), Inches(12.3), Emu(45720),
        )
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT_COLOR
        line.line.fill.background()

        # Bullets text box
        body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(12.3), Inches(5.2))
        body_tf = body_box.text_frame
        body_tf.word_wrap = True

        for i, bullet in enumerate(slide_data.bullets):
            para = body_tf.paragraphs[0] if i == 0 else body_tf.add_paragraph()
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
    status_callback: Optional[Callable[[str], None]] = None,
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
