.PHONY: preflight phase-start fix format lint typecheck test validate validate-check

preflight:
	./scripts/phase_start_preflight.sh

phase-start: preflight

fix:
	ruff check --fix .

format:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest -q

validate-check: format lint typecheck test

validate: fix format lint typecheck test
