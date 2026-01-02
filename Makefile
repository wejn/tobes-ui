.PHONY: all help examples lint lintmod

all:
	python3 -m tobes_ui.main /dev/ttyUSB0 -e auto -o

oo:
	python3 -m tobes_ui.main oo: -e auto -o -q

wlc:
	python3 -m tobes_ui.main oo: -m wlc

help:
	@COLUMNS=94 python3 -m tobes_ui.main -h

examples:
	python3 -m tobes_ui.main -d examples/*.json

lint:
	pylint *.py helpers/*.py tobes_ui/*.py tobes_ui/*/*.py

lintmod:
	@FILES=$$(git diff --name-only HEAD | grep 'py$$'); \
	if [ -n "$$FILES" ]; then \
		pylint $$FILES; \
	else \
		echo "No python files modified."; \
	fi

push:
	@if [ ! -z "$$(git status --porcelain)" ]; then \
		echo "Not clean, won't push"; \
		false; \
	fi
	rm -rf dist/ tobes_ui.egg-info/
	python -m build
	twine upload dist/*

test:
	pytest tests
