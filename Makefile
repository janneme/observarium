.DEFAULT_GOAL := help
AWS_PROFILE   ?= personal

.PHONY: help deploy dev-server dev-client data-prep data-upload

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

deploy: ## Apply Terraform, deploy Lambda, sync data, deploy client
	@echo "==> Terraform apply"
	cd infra && terraform apply -auto-approve
	@echo "==> Deploy Lambda"
	$(MAKE) _deploy-lambda
	@echo "==> Sync data to S3"
	$(MAKE) data-upload
	@echo "==> Deploy client to S3"
	$(MAKE) _deploy-client

dev-server: ## Run the Lambda handler via the local HTTP wrapper
	cd server && python local_server.py

dev-client: ## Start the Vite dev server for the Svelte client
	cd client && npm run dev

data-prep: ## Run the data preparation pipeline
	cd data_prep && python main.py $(ARGS)

data-upload: ## Detect changed data files, re-zip and upload to S3
	@echo "data-upload: not yet implemented"

# Internal targets (not advertised in help)
_deploy-lambda:
	@echo "_deploy-lambda: not yet implemented"

_deploy-client:
	@echo "_deploy-client: not yet implemented"
