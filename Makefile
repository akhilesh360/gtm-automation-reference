.PHONY: setup data run scenarios test lint dashboard api erp policy screenshots clean

PY := .venv/bin/python

setup:            ## create the virtualenv and install dependencies
	python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements.txt ruff

data:             ## regenerate the seeded mock data
	$(PY) -m scripts.generate_mock_data

run:              ## run the full pipeline (offline by default; SF_ENABLED=true for a real org)
	$(PY) -m src.main run-all

scenarios:        ## run the pipeline and print the reference scenarios
	$(PY) -m src.main scenarios

test:             ## run the test suite
	$(PY) -m pytest -q

lint:             ## lint with ruff
	.venv/bin/ruff check .

dashboard:        ## start the Streamlit dashboard
	.venv/bin/streamlit run dashboard/app.py

api:              ## start the FastAPI service
	.venv/bin/uvicorn api.app:app --reload

erp:              ## start the standalone mock ERP (then set ERP_URL=http://127.0.0.1:8100)
	.venv/bin/uvicorn erp.mock_server:app --port 8100

policy:           ## regenerate docs/approval_matrix.md from config/policy.yaml
	$(PY) -m src.main policy --render

screenshots:      ## rebuild the database, then capture docs/screenshots (needs playwright)
	$(PY) -m src.main run-all >/dev/null && $(PY) -m scripts.capture_screenshots

clean:            ## remove generated database, mock stores and logs
	rm -f data/gtm.duckdb data/processed/*.json data/processed/*.csv logs/*.log

help:
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## / - /'
