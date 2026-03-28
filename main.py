"""Streamlit UI: startup analysis agent front-end."""
from __future__ import annotations

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

                with col1:
                    excel_path = result["excel_path"]
                    if Path(excel_path).exists():
                        with open(excel_path, "rb") as f:
                            st.download_button(
                                label="Download Comps Model (.xlsx)",
                                data=f,
                                file_name=Path(excel_path).name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                with col2:
                    pptx_path = result["pptx_path"]
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
