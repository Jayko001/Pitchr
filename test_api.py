"""Quick test: verify custom browser_action tool works with real Anthropic API."""
import os, base64, struct, zlib, sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from unittest.mock import patch, MagicMock


def tiny_png():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(c[4:]) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    png += chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


tiny = tiny_png()

with patch("agents.research._take_screenshot", return_value=tiny), \
     patch("agents.research.Kernel", return_value=MagicMock()):
    from agents.research import run_computer_use_scrape
    result = run_computer_use_scrape(
        session_id="test",
        sector="Fintech",
        stage="Series B",
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        kernel_api_key=os.environ["KERNEL_SH_API_KEY"],
        status_callback=lambda m: print(f"  {m}"),
    )
    print(f"\nResult count: {len(result)}")
    print("PASS: API call succeeded with custom browser_action tool")
