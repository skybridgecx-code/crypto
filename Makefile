.PHONY: fix format lint typecheck test validate validate-edited

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

validate: format lint typecheck test

validate-edited: fix format lint typecheck test
