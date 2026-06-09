format:
	uv run black pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run isort pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin

lint:
	uv run black --check --diff pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run isort --check --diff pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run mypy pyTale pytale-tools test-plugin
