all:
	python3 main.py /dev/ttyUSB0 -e auto -o

help:
	COLUMNS=94 python3 main.py -h

lint:
	pylint *.py helpers/*.py tobes_ui/*.py
