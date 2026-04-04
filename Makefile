format:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest -q

validate: format lint typecheck test
