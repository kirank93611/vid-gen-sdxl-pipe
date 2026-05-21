.PHONY: test-integration run benchmark-product clean spheron-setup spheron-smoke spheron-benchmark spheron-web spheron-deploy deploy-web deploy-api

SPHERON_HOST ?= ubuntu@64.247.196.216
SPHERON_DIR ?= ~/image-sd
# spheron-sync / spheron-web: run from your Mac only (rsync Mac → VM).
# On the VM itself, use: make deploy-web   (or: bash scripts/spheron_deploy_web.sh)
SPHERON_SSH_KEY ?= $(HOME)/.ssh/id_ed25519
SPHERON_RSYNC := rsync -avz -e "ssh -i $(SPHERON_SSH_KEY) -o BatchMode=yes"
SPHERON_SSH := ssh -i $(SPHERON_SSH_KEY) -o BatchMode=yes

# `source` requires bash (not plain POSIX sh on some systems).
SHELL := /bin/bash

INFERENCE_DIR := services/inference-api
VENV := .venv/bin/activate

clean:
	bash scripts/clean.sh

run:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && uvicorn main:app --host 127.0.0.1 --port $${PORT:-8001} --reload

test-integration:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && python -m unittest discover -s tests -p 'test_*.py' -v

# Requires API running (make run) and fixture JPEGs in benchmarks/product_similarity/fixtures/
benchmark-product:
	source $(VENV) && python scripts/run_product_benchmark.py

# Sync repo to Spheron VM (excludes .venv, models, node_modules)
# Code only — do NOT sync models/ (download on VM via spheron_setup.sh)
spheron-sync:
	$(SPHERON_RSYNC) --exclude .venv --exclude models --exclude node_modules --exclude apps/web/.next --exclude generated --exclude .git \
		./ $(SPHERON_HOST):$(SPHERON_DIR)/

spheron-setup: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/spheron_setup.sh'

# --- Mac → VM (do not run these while SSH'd into the VM) ---
spheron-web: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/spheron_deploy_web.sh'

# --- VM only (run after code is on the machine: git pull, or spheron-sync from Mac) ---
deploy-web:
	bash scripts/spheron_deploy_web.sh

deploy-api:
	bash scripts/spheron_restart_api.sh

# Mac: sync inference + web, then restart both on VM
spheron-deploy: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/spheron_restart_api.sh && bash scripts/spheron_deploy_web.sh'

spheron-smoke:
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && source .venv/bin/activate && \
		export DEVICE=cuda GENERATION_TIMEOUT_SECONDS=300 && \
		(cd services/inference-api && nohup uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/sdxl-api.log 2>&1 &) && \
		sleep 3 && python scripts/spheron_generate.py --api-url http://127.0.0.1:8001 --out generated/spheron_smoke.jpg'

# Sync code, restart API on VM, run product benchmark against localhost:8001 on GPU
spheron-benchmark: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && source .venv/bin/activate && \
		export DEVICE=cuda GENERATION_TIMEOUT_SECONDS=300 GENERATION_CANCEL_GRACE_SECONDS=120 \
		INPAINT_STRENGTH=0.85 BENCHMARK_GENERATE_TIMEOUT_S=660 BENCHMARK_JOB_POLL_TIMEOUT_S=1800 && \
		pkill -f "uvicorn main:app" 2>/dev/null || true; sleep 2; \
		cd services/inference-api && nohup uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/sdxl-api.log 2>&1 & \
		sleep 8 && cd $(SPHERON_DIR) && python scripts/run_product_benchmark.py --api-url http://127.0.0.1:8001 && \
		cat benchmarks/product_similarity/results/latest.md'
