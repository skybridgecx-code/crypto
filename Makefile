.PHONY: preflight phase-start phase-finish phase-close-check fix format lint typecheck test validate validate-check

preflight:
	./scripts/phase_start_preflight.sh

phase-start: preflight

phase-finish:
	./scripts/phase_finish_guardrail.sh

phase-close-check:
	./scripts/phase_close_check.sh

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
