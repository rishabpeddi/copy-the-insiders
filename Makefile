# On Windows without make, `uv run cti all` does the same thing as `make all`.
.PHONY: all install ingest build test lint clean

START ?= 2014Q1
END   ?= 2026Q2

all: install ingest build test

install:
	uv sync

ingest:
	uv run cti ingest form4 --start $(START) --end $(END)

build:
	uv run cti build
	uv run cti ingest reference
	uv run cti ingest prices
	uv run cti resolve

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

clean:
	rm -rf data/staging/* data/warehouse.duckdb
