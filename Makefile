SHELL := /bin/bash

.PHONY: docs
TOX_ARGS?=

install:
	poetry install

clean: clean_docs
	rm -rf dist

clean_docs:
	cd docs && make clean

test: install
	poetry run tox -p -o -r -- -- $(TOX_ARGS)

docs:
	cd docs && poetry run make html
	echo You can now browse the documentation at ./docs/build/index.html

build: docs
	poetry build

# deactivated by default to prevent accidental uploads
publish: test clean build
	echo "NOT uploading to PyPI. You need to uncomment the command in the Makefile."
#	poetry run python -mtwine upload dist/* --verbose
