all:
	python3 main.py /dev/ttyUSB0 -e auto -o

lint:
	pylint *.py
