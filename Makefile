.PHONY: all help examples lint lintmod

all:
	python3 main.py /dev/ttyUSB0 -e auto -o

help:
	@COLUMNS=94 python3 main.py -h

examples:
	python3 main.py -d examples/*.json

lint:
	pylint *.py helpers/*.py tobes_ui/*.py tobes_ui/*/*.py

lintmod:
	@FILES=$$(git diff --name-only HEAD | grep 'py$$'); \
	if [ -n "$$FILES" ]; then \
		pylint $$FILES; \
	else \
		echo "No python files modified."; \
	fi
