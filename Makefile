# LightRAG Docker Deployment Makefile
# ====================================
#
# Targets:
#   make setup          - Create .env, config.ini, data directories
#   make dev            - Start macOS development stack (CPU TEI)
#   make prod           - Start H200 production stack (GPU TEI)
#   make build          - Build LightRAG image for current platform
#   make build-amd64    - Cross-compile amd64 image (for H200)
#   make build-webui    - Build frontend only
#   make export         - Build amd64 + export tar (TEI GPU + LightRAG)
#   make import         - Load images from tar files
#   make download-model - Pre-download Jina Embeddings V3 model
#   make logs           - View logs (SERVICE=tei to filter)
#   make down           - Stop all containers
#   make status         - Show container status
#   make test           - Run pytest
#   make clean          - Remove containers, images, artifacts

.PHONY: setup dev prod build build-amd64 build-webui export import \
        download-model logs down status test clean help

COMPOSE_BASE   := docker-compose.yml
COMPOSE_DEV    := docker-compose.dev.yml
COMPOSE_PROD   := docker-compose.prod.yml
IMAGE_NAME     := lightrag:local
IMAGE_DIR      := docker-images
MODEL_DIR      := data/models

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup: ## Create .env, config.ini, data directories
	@mkdir -p data/rag_storage data/inputs data/models $(IMAGE_DIR)
	@if [ ! -f .env ]; then \
		cp env.example .env; \
		echo "Created .env from env.example — edit it with your LLM API keys."; \
	else \
		echo ".env already exists, skipping."; \
	fi
	@if [ ! -f config.ini ]; then \
		touch config.ini; \
		echo "Created empty config.ini."; \
	else \
		echo "config.ini already exists, skipping."; \
	fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
build: ## Build LightRAG image for current platform
	docker build -t $(IMAGE_NAME) .

build-amd64: ## Cross-compile amd64 LightRAG image (for H200)
	docker buildx build --platform linux/amd64 -t $(IMAGE_NAME) --load .

build-webui: ## Build frontend only (bun)
	cd lightrag_webui && bun install --frozen-lockfile && bun run build

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
dev: ## Start macOS development stack (CPU TEI via Rosetta 2)
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d

prod: ## Start H200 production stack (GPU TEI)
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_PROD) up -d

down: ## Stop all containers
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) -f $(COMPOSE_PROD) down

# ---------------------------------------------------------------------------
# Logs & Status
# ---------------------------------------------------------------------------
logs: ## View logs (SERVICE=tei to filter a specific service)
ifdef SERVICE
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) -f $(COMPOSE_PROD) logs -f $(SERVICE)
else
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) -f $(COMPOSE_PROD) logs -f
endif

status: ## Show container status
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) -f $(COMPOSE_PROD) ps

# ---------------------------------------------------------------------------
# Image Transfer (macOS → H200)
# ---------------------------------------------------------------------------
export: build-amd64 ## Build amd64 + export tar files for transfer
	@mkdir -p $(IMAGE_DIR)
	docker save $(IMAGE_NAME) | gzip > $(IMAGE_DIR)/lightrag-local.tar.gz
	docker pull --platform linux/amd64 ghcr.io/huggingface/text-embeddings-inference:hopper-1.8
	docker save ghcr.io/huggingface/text-embeddings-inference:hopper-1.8 | gzip > $(IMAGE_DIR)/tei-gpu-hopper.tar.gz
	@echo ""
	@echo "Exported to $(IMAGE_DIR)/:"
	@ls -lh $(IMAGE_DIR)/*.tar.gz
	@echo ""
	@echo "Transfer to H200:"
	@echo "  scp $(IMAGE_DIR)/*.tar.gz user@h200:~/lightrag/$(IMAGE_DIR)/"
	@echo "  scp -r data/models/ user@h200:~/lightrag/data/models/"

import: ## Load images from tar files
	@for f in $(IMAGE_DIR)/*.tar.gz; do \
		echo "Loading $$f ..."; \
		docker load < "$$f"; \
	done

# ---------------------------------------------------------------------------
# Model Management
# ---------------------------------------------------------------------------
download-model: ## Pre-download BGE-M3 model to data/models/
	@mkdir -p $(MODEL_DIR)
	docker run --rm \
		-v "$$(pwd)/$(MODEL_DIR):/data" \
		--platform linux/amd64 \
		ghcr.io/huggingface/text-embeddings-inference:cpu-1.7 \
		--model-id BAAI/bge-m3 \
		--port 80 &
	@echo "Waiting for model download (check docker logs) ..."
	@echo "Once the model is cached in $(MODEL_DIR)/, press Ctrl+C to stop."

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test: ## Run pytest
	python -m pytest tests

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean: down ## Remove containers, build artifacts, exported images
	@rm -rf $(IMAGE_DIR)/*.tar.gz
	@echo "Cleaned exported images."
	@echo "Note: data/models/ and data/rag_storage/ are preserved."
	@echo "To remove everything: rm -rf data/"
