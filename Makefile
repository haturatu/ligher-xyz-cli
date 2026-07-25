PYTHON ?= python3
PIP := $(PYTHON) -m pip
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
INSTALL_BIN ?= $(HOME)/.local/bin
BASHRC ?= $(HOME)/.bashrc
PACKAGE := ligher-xyz-cli
COMPLETION_LINE := eval "$$(lighter completion bash)" \# ligher-xyz-cli-completion
LOCALE_PO := $$(find src/lighter_cli/locale -name '*.po' -type f)

.PHONY: help install uninstall completion locales test lint format check package venv clean

help:
	@printf '%s\n' \
		'make install     Install the editable CLI and enable bash completion' \
		'make uninstall   Uninstall the package and remove the completion line' \
		'make venv        Create a local development virtualenv' \
		'make locales     Compile gettext .po catalogs into .mo files' \
		'make test        Run the test suite' \
		'make lint        Compile-check all source and tests' \
		'make format      Format source with Ruff when available' \
		'make check       Run locales, lint, and tests' \
		'make package     Build wheel and source distribution' \
		'make clean       Remove only local generated build/test artifacts'

install:
	$(PIP) install -e .
	$(MAKE) completion

uninstall:
	-$(PIP) uninstall -y $(PACKAGE)
	touch "$(BASHRC)"
	sed -i '\|^eval "$$(lighter completion bash)" # ligher-xyz-cli-completion$$|d' "$(BASHRC)"

completion:
	touch "$(BASHRC)"
	grep -Fqx '$(COMPLETION_LINE)' "$(BASHRC)" || printf '%s\n' '$(COMPLETION_LINE)' >> "$(BASHRC)"

venv:
	$(PYTHON) -m venv "$(VENV)"
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e . pytest build ruff

locales:
	@for po in $(LOCALE_PO); do \
		msgfmt "$$po" -o "$${po%.po}.mo"; \
	done

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

lint:
	PYTHONPATH=src $(PYTHON) -m compileall -q src tests

format:
	@if $(PYTHON) -m ruff --version >/dev/null 2>&1; then \
		$(PYTHON) -m ruff format src tests; \
	else \
		echo 'Ruff is not installed; run make venv or pip install ruff.'; \
	fi

check: locales lint test

package: locales
	$(PIP) wheel . --wheel-dir dist

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
