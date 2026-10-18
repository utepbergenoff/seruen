"""Point the website at the backend: writes API_URL into frontend/config.js.

    python scripts/set_api_url.py https://seruen-api.onrender.com
    python scripts/set_api_url.py ""          # same server (local run)
"""
import re
import sys
from pathlib import Path

cfg = Path(__file__).resolve().parent.parent / "frontend" / "config.js"
url = (sys.argv[1] if len(sys.argv) > 1 else "").strip().rstrip("/")
if url and not url.startswith("https://"):
    sys.exit("Use the https:// address (a phone blocks http:// calls from an https:// site).")
text = cfg.read_text(encoding="utf-8")
text, n = re.subn(r'API_URL: "[^"]*"', f'API_URL: "{url}"', text, count=1)
if n != 1:
    sys.exit("API_URL line not found in frontend/config.js")
cfg.write_text(text, encoding="utf-8")
print(f"frontend/config.js -> API_URL = {url or '(same server)'}")
