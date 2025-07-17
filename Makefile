.PHONY: help test test-coverage test-watch install install-dev lint format clean

help:
	@echo "Available commands:"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install development dependencies"
	@echo "  make test          Run tests"
	@echo "  make test-coverage Run tests with coverage report"
	@echo "  make test-watch    Run tests in watch mode"
	@echo "  make lint          Run linting"
	@echo "  make format        Format code"
	@echo "  make clean         Clean up generated files"

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-test.txt
	pip install black isort flake8 pytest-watch
	pre-commit install

test:
	pytest -v

test-coverage:
	pytest -v --cov=src --cov-report=term-missing --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

test-watch:
	ptw --runner "pytest -x -vs"

test-specific:
	@read -p "Enter test name pattern: " pattern; \
	pytest -v -k "$$pattern"

lint:
	flake8 src tests --max-line-length=100 --extend-ignore=E203,W503
	isort --check-only src tests
	black --check src tests

format:
	isort src tests
	black src tests --line-length=100

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov .pytest_cache
	rm -rf .mypy_cache .ruff_cache
	rm -f test.db test_scraper.db