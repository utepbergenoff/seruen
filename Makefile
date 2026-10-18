PYTHON ?= python3
POI_PATH ?= data/poi.json
export POI_PATH
.PHONY: setup run test eval index mock data data-fresh test-data
setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements-dev.txt
index:
	.venv/bin/python scripts/reindex.py
run:
	.venv/bin/python -m scripts.serve
mock:
	MOCK_MODE=true .venv/bin/python -m scripts.serve
test:
	.venv/bin/python -m pytest -q
eval:
	.venv/bin/python eval/run.py

# --- data pipeline (stream A): rebuild data/poi.json + data/quality_report.md ---
# from raw files in data/raw/ (no keys, no network)
data:
	$(PYTHON) -m pipeline.run
# full re-collection: OSM + Google place_id + Wikipedia (+ Gemini if GEMINI_API_KEY is set)
data-fresh:
	$(PYTHON) -m pipeline.run --fresh
test-data:
	$(PYTHON) -m pytest -q tests/test_hours.py tests/test_enrich.py tests/test_wiki.py tests/test_dedupe.py tests/test_describe.py
