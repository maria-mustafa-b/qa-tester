.PHONY: install browsers test lint demo scan-demo

install:
	python -m pip install -e ".[dev]"

browsers:
	playwright install chromium

test:
	pytest -q

lint:
	ruff check .

demo:
	python -m http.server 8080 --directory demo_site

scan-demo:
	preflight-qa scan --config preflight.example.yml --authorized --output reports/demo

