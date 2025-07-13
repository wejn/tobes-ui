.PHONY: all help examples lint

all:
	python3 main.py /dev/ttyUSB0 -e auto -o

help:
	@COLUMNS=94 python3 main.py -h

examples:
	python3 main.py -d examples/*.json

lint:
	pylint *.py helpers/*.py tobes_ui/*.py
