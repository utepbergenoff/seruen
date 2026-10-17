PYTHON ?= python3
POI_PATH ?= data/poi_sample.json
export POI_PATH
.PHONY: setup run test eval index mock
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
