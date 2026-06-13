.PHONY: test-integration run benchmark-product clean download-llm download-ltx download-tiefighter \
	download-dolphin spheron-download-llm \
	spheron-check spheron-set-ip \
	spheron-sync spheron-setup spheron-up spheron-tunnel spheron-smoke spheron-benchmark \
	spheron-web spheron-deploy deploy-web deploy-api

# Dynamic VM IP: copy .env.spheron.example → .env.spheron, or: make spheron-set-ip IP=1.2.3.4
ifneq (,$(wildcard .env.spheron))
include .env.spheron
export
endif

SPHERON_IP ?=
SPHERON_USER ?= ubuntu
SPHERON_DIR ?= /home/ubuntu/image-sd
SPHERON_SSH_KEY ?= $(HOME)/.ssh/id_ed25519
SPHERON_HOST = $(SPHERON_USER)@$(SPHERON_IP)

# spheron-sync / spheron-web: run from your Mac only (rsync Mac → VM).
# On the VM itself, use: make deploy-web   (or: bash scripts/spheron_deploy_web.sh)
SPHERON_SSH_OPTS := -o BatchMode=yes -o StrictHostKeyChecking=accept-new
SPHERON_RSYNC := rsync -avz -e "ssh -i $(SPHERON_SSH_KEY) $(SPHERON_SSH_OPTS)"
SPHERON_SSH := ssh -i $(SPHERON_SSH_KEY) $(SPHERON_SSH_OPTS)

spheron-check:
	@test -n "$(SPHERON_IP)" || (echo "Set VM IP: make spheron-set-ip IP=216.81.248.248"; echo "  or copy .env.spheron.example to .env.spheron"; exit 1)

spheron-set-ip:
	@test -n "$(IP)" || (echo "Usage: make spheron-set-ip IP=<vm-ip>"; echo "  optional: SPM_USER=ubuntu make spheron-set-ip IP=..."; exit 1)
	SPM_USER="$(SPM_USER)" bash scripts/spheron_set_ip.sh "$(IP)"

# Code sync only (~seconds)
spheron-sync: spheron-check
	@echo "→ $(SPHERON_HOST):$(SPHERON_DIR)"
	$(SPHERON_RSYNC) --exclude .venv --exclude '/models/' --exclude node_modules --exclude apps/web/.next --exclude generated --exclude .git \
		./ $(SPHERON_HOST):$(SPHERON_DIR)/

# First VM: full torch + SDXL download (~15–25 min)
spheron-setup: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/spheron_setup.sh'

# After IP change: sync + skip model/torch if disk retained (~5–15 min with web build)
spheron-up: spheron-sync
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/spheron_bootstrap_quick.sh'

spheron-tunnel: spheron-check
	bash scripts/spheron_tunnel.sh

# `source` requires bash (not plain POSIX sh on some systems).
SHELL := /bin/bash

INFERENCE_DIR := services/inference-api
VENV := .venv/bin/activate

clean:
	bash scripts/clean.sh

# GGUF_MODEL_ID: tiefighter_20b | dolphin_mixtral_8x7b (see model_catalog.py)
GGUF_MODEL_ID ?= dolphin_mixtral_8x7b

download-llm:
	source $(VENV) && GGUF_MODEL_ID=$(GGUF_MODEL_ID) python scripts/download_gguf_model.py

download-tiefighter:
	$(MAKE) download-llm GGUF_MODEL_ID=tiefighter_20b

download-dolphin:
	$(MAKE) download-llm GGUF_MODEL_ID=dolphin_mixtral_8x7b

download-ltx:
	source $(VENV) && python scripts/download_ltx.py

spheron-download-llm: spheron-check
	$(SPHERON_SSH) $(SPHERON_HOST) 'cd $(SPHERON_DIR) && bash scripts/ensure_llama_cpp_cuda.sh && \
		source .venv/bin/activate && GGUF_MODEL_ID=$(GGUF_MODEL_ID) python scripts/download_gguf_model.py'

run:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && uvicorn main:app --host 127.0.0.1 --port $${PORT:-8001} --reload

test-integration:
	cd $(INFERENCE_DIR) && source ../../$(VENV) && python -m unittest discover -s tests -p 'test_*.py' -v

# Requires API running (make run) and fixture JPEGs in benchmarks/product_similarity/fixtures/
benchmark-product:
	source $(VENV) && python scripts/run_product_benchmark.py

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
