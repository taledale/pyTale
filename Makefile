HYTALE_VERSION := 0.5.6
SERVER_JAR := .pytale/servers/Server-$(HYTALE_VERSION).jar
EVENTS_DIR := pyTale/pytale/events/hytale

.PHONY: format lint test generate-events

format:
	uv run black pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run isort pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin

lint:
	uv run black --check --diff pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run isort --check --diff pyTale/pytale pytale-tools/pytale_tools test-plugin/test_plugin
	uv run mypy pyTale pytale-tools test-plugin

test:
	uv run pytest pytale-tools/tests/ -v --cov=pytale_tools --cov-report=term-missing

generate-events:
	rm -rf $(EVENTS_DIR)
	uv run pytale-tools generate $(SERVER_JAR) -o $(EVENTS_DIR)
