format:
	uv run black pytale-tools test-plugin
	uv run isort pytale-tools test-plugin

lint:
	uv run black --check --diff pytale-tools test-plugin
	uv run isort --check --diff pytale-tools test-plugin
	uv run mypy pytale-tools test-plugin
