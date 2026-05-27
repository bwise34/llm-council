.DEFAULT_GOAL := help

APP_NAME       := llm-council
USER_EMAIL     := bwise@redventures.com
WORKSPACE_PATH := /Workspace/Users/$(USER_EMAIL)/$(APP_NAME)

.PHONY: help install dev local-databricks build sync deploy bundle-validate bundle-deploy clean

help:
	@echo "LLM Council — make targets"
	@echo ""
	@echo "  install           install backend (uv) and frontend (npm) deps"
	@echo "  dev               local two-process dev (./start.sh): FastAPI :8001 + Vite :5173"
	@echo "  local-databricks  run the app under the Databricks Apps local proxy + debugger"
	@echo "  build             build the React frontend into frontend/dist/"
	@echo "  sync              build, then sync sources to $(WORKSPACE_PATH)"
	@echo "  deploy            build + sync + databricks apps deploy"
	@echo "  bundle-validate   validate databricks.yml"
	@echo "  bundle-deploy     databricks bundle deploy (declarative resource sync)"
	@echo "  clean             remove frontend/dist/"

install:
	uv sync
	cd frontend && npm install

dev:
	./start.sh

local-databricks:
	databricks apps run-local --prepare-environment --debug

build:
	cd frontend && npm run build

sync: build
	databricks sync . $(WORKSPACE_PATH)

deploy: sync
	databricks apps deploy $(APP_NAME) --source-code-path $(WORKSPACE_PATH)

bundle-validate:
	databricks bundle validate

bundle-deploy:
	databricks bundle deploy

clean:
	rm -rf frontend/dist
