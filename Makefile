PY ?= python

.PHONY: data data-fresh test-data

# Rebuild data/poi.json + data/quality_report.md from raw files in data/raw/ (no keys needed)
data:
	$(PY) -m pipeline.run

# Full re-collection from OSM + Google Places + Wikipedia (+ Gemini if GEMINI_API_KEY is set)
data-fresh:
	$(PY) -m pipeline.run --fresh

test-data:
	$(PY) -m pytest -q tests/test_hours.py tests/test_enrich.py tests/test_wiki.py tests/test_dedupe.py tests/test_describe.py
