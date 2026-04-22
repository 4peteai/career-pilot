.PHONY: install dev scan gmail evaluate dashboard schedule clean

install:
	pip install -e .
	playwright install chromium

dev:
	pip install -e ".[dev]"

scan:
	career-pilot scan

gmail:
	career-pilot gmail-fetch

evaluate:
	@echo "Usage: make evaluate URL=https://..."
	career-pilot evaluate $(URL)

dashboard:
	career-pilot dashboard

schedule:
	career-pilot schedule install

clean:
	rm -rf output/*.pdf output/*.html
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

lint:
	ruff check src/
	ruff format --check src/

format:
	ruff check --fix src/
	ruff format src/

typecheck:
	mypy src/
