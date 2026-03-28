# Startup Analysis Agent — Design Spec
**Date:** 2026-03-28
**Hackathon:** RevUC (24-hour build)
**Stack:** Python 3.11, Anthropic SDK, kernel.sh, Playwright, pandas, openpyxl, python-pptx, Streamlit

---

## Overview

An agent-powered tool that takes an early-stage startup as input and produces two deliverables: a comps/market valuation Excel model and a pitch deck PowerPoint. The agent scrapes PitchBook for comparable companies via a cloud browser (kernel.sh), then uses Claude to generate both the Excel model structure and the pitch deck narrative.

---

## Architecture

```
User Input (Streamlit)
  "Startup name, sector, stage, 2-3 sentence description"
        │
        ▼
  Orchestrator Agent (claude-sonnet-4-6)
  ├── Research Agent
  │       └── kernel.sh API → cloud browser session (CDP)
  │               → Playwright connects via CDP URL
  │               → PitchBook login (university SSO via env vars)
  │               → search comps by sector / stage / geography
  │               → extract: name, valuation, revenue, EBITDA, funding rounds, investors
  │               → destroys session, returns structured JSON
  │
  ├── Analysis Agent
  │       └── receives PitchBook JSON
  │               → Claude generates Excel structure (tabs, formulas, multiples)
  │               → openpyxl executes Claude's output to write .xlsx
  │               → Tab 1: Comps Table
  │               → Tab 2: Trading Multiples (EV/Rev, EV/EBITDA, P/E)
  │               → Tab 3: Market Valuation (multiples-based range)
  │
  └── Deck Agent
          └── receives analysis summary from Analysis Agent
                  → Claude generates slide content:
                      problem, solution, market size (TAM/SAM/SOM),
                      competitive positioning, valuation range
                  → python-pptx fills base .pptx template with content
                  → Output: pitch_deck.pptx

Streamlit UI
  - Live agent status feed (which agent is currently running)
  - Download buttons for comps.xlsx and pitch_deck.pptx on completion
```

---

## Components

### 1. Orchestrator Agent
- Model: `claude-sonnet-4-6`
- Receives startup prompt from Streamlit
- Calls Research → Analysis → Deck in sequence
- Passes outputs between agents as structured dicts
- Reports status back to Streamlit via a shared state object (e.g. `st.session_state`)

### 2. Research Agent
- Calls kernel.sh API to create a browser session
- Connects Playwright via the CDP URL returned by kernel.sh
- Logs into PitchBook using `PITCHBOOK_USER` / `PITCHBOOK_PASS` env vars (university SSO)
- Searches for 8–12 comparable companies matching sector, stage, and geography
- Scrapes per-company fields: name, last valuation, ARR/revenue, EBITDA, last funding round, lead investors
- Destroys the kernel.sh session on completion
- Returns: `List[Dict]` of comp records

### 3. Analysis Agent
- Input: comp records JSON + startup description
- Prompts Claude to decide which multiples are most appropriate for the sector
- Claude returns openpyxl-compatible instructions (cell values, formulas, formatting)
- Agent executes those instructions to write `comps.xlsx`
- Computes implied valuation range (low / mid / high) from median multiples × startup metrics

### 4. Deck Agent
- Input: startup description + valuation range + top 5 comps summary
- Prompts Claude to generate structured slide content (title, bullets, data points per slide)
- 6-slide structure:
  1. Cover (name, tagline, stage)
  2. Problem
  3. Solution
  4. Market Size (TAM / SAM / SOM)
  5. Competitive Landscape (comps table)
  6. Valuation & Ask
- `python-pptx` fills a base template (`templates/base_deck.pptx`) with Claude's content
- Output: `pitch_deck.pptx`

### 5. Streamlit UI
- Single-page app with an input form: startup name, sector, stage, short description
- On submit: runs orchestrator, streams status updates per agent
- On completion: renders download buttons for both output files
- Error state: shows which agent failed and why

---

## Data Flow

```
startup_prompt (str)
    → research_agent() → comps_data: List[Dict]
    → analysis_agent(comps_data, startup_prompt) → valuation_range: Dict, writes comps.xlsx
    → deck_agent(startup_prompt, valuation_range, comps_data[:5]) → writes pitch_deck.pptx
    → streamlit renders download links
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `PITCHBOOK_USER` | PitchBook university login email |
| `PITCHBOOK_PASS` | PitchBook university login password |
| `KERNEL_SH_API_KEY` | kernel.sh API key for browser sessions |

---

## File Structure

```
RevUC/
├── main.py                  # Streamlit app entry point
├── agents/
│   ├── orchestrator.py      # Orchestrator agent
│   ├── research.py          # Research agent (kernel.sh + Playwright)
│   ├── analysis.py          # Analysis agent (Claude + openpyxl)
│   └── deck.py              # Deck agent (Claude + python-pptx)
├── templates/
│   └── base_deck.pptx       # Base PowerPoint template
├── outputs/                 # Generated .xlsx and .pptx files (gitignored)
├── .env                     # Env vars (gitignored)
├── requirements.txt
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-03-28-startup-analysis-agent-design.md
```

---

## 24-Hour Execution Plan

| Hours | Task |
|-------|------|
| 0–1 | Repo scaffolding, requirements.txt, env wiring, verify kernel.sh + Anthropic SDK connect |
| 1–4 | Research Agent: kernel.sh session creation, Playwright PitchBook login + comp scraper |
| 4–7 | Analysis Agent: Claude-generated Excel model via openpyxl, comps + multiples + valuation tabs |
| 7–10 | Deck Agent: Claude slide content generation + python-pptx template filler |
| 10–12 | Orchestrator: wire all 3 agents, pass data between them end-to-end |
| 12–15 | Streamlit UI: input form, live status feed, download buttons |
| 15–20 | Integration test full pipeline on a real startup (e.g. a fintech seed-stage co) |
| 20–22 | Polish: error handling, fallback if PitchBook is slow, demo script |
| 22–24 | Buffer + rehearse demo |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| PitchBook login breaks (2FA, SSO redirect) | Test auth flow in hour 1; have 5 pre-scraped comp JSON fixtures as fallback |
| kernel.sh session latency | Set 60s timeout; fall back to local Playwright if needed |
| python-pptx template formatting issues | Keep base template minimal (text placeholders only); style in post if needed |
| Claude Excel output is malformed | Parse and validate openpyxl instructions before executing; retry once on failure |

---

## Success Criteria

A working demo where a judge can type a startup name + sector into Streamlit, watch 3 agents run sequentially, and download a populated `.xlsx` comps model and `.pptx` pitch deck within ~2 minutes.
