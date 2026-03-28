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
