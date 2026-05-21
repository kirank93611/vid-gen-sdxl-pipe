.PHONY: test-integration run benchmark-product

# `source` requires bash (not plain POSIX sh on some systems).
SHELL := /bin/bash

INFERENCE_DIR := services/inference-api
VENV := .venv/bin/activate

run:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && uvicorn main:app --host 127.0.0.1 --port $${PORT:-8001} --reload

test-integration:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && python -m unittest discover -s tests -p 'test_*.py' -v

# Requires API running (make run) and fixture JPEGs in benchmarks/product_similarity/fixtures/
benchmark-product:
	source $(VENV) && python scripts/run_product_benchmark.py
