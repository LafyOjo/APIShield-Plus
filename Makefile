PYTHON := python
PIP := pip

.PHONY: fmt lint test

fmt:
	$(PYTHON) -m isort backend
	$(PYTHON) -m black backend
	$(PYTHON) -m ruff format backend

lint:
	$(PYTHON) -m ruff check backend

test:
	$(PYTHON) -m pytest backend/tests

seed:
	$(PYTHON) scripts/seed.py
