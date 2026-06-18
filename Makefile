.DEFAULT_GOAL := help
AWS_PROFILE   ?= personal

.PHONY: help deploy deploy-lambda deploy-client dev dev-server dev-client data-prep data-upload lint test

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

deploy: ## Apply Terraform, deploy Lambda, sync data, deploy client
	@echo "==> Terraform apply"
	cd infra && terraform apply -auto-approve
	@echo "==> Deploy Lambda"
	$(MAKE) deploy-lambda
	@echo "==> Sync data to S3"
	$(MAKE) data-upload
	@echo "==> Deploy client to S3"
	$(MAKE) deploy-client

dev: ## Run both frontend and backend development servers
	python3 run.py

dev-server: ## Run the Lambda handler via the local HTTP wrapper
	$(MAKE) -C server dev

dev-client: ## Start the Vite dev server for the Svelte client
	cd client && VITE_APP_VERSION_DATE=$$(date +%Y-%m-%d) npm run dev

data-prep: ## Run the data preparation pipeline
	cd data_prep && uv run python main.py $(ARGS)

data-upload: ## Detect changed data files, re-zip and upload to storage backend
	@echo "Running data upload (STORAGE=$(STORAGE) MAG=$(mag))"
	cd data_prep && MAG=$(mag) STORAGE=$(STORAGE) PYTHONPATH=.. uv run python data_upload.py

lint: ## Run ruff, pylint, eslint, prettier, and svelte-check on all packages
	@printf '\033[1;36m==> Linting server\033[0m\n'
	$(MAKE) -C server lint
	@printf '\033[1;36m==> Linting data_prep\033[0m\n'
	$(MAKE) -C data_prep lint
	@printf '\033[1;36m==> Linting client\033[0m\n'
	$(MAKE) -C client lint

test: ## Run server and data-prep test suites (from repo root)
	@printf '\033[1;36m==> Running server tests\033[0m\n'
	cd server && PYTHONPATH=$(CURDIR) uv run pytest -q
	@printf '\033[1;36m==> Running data_prep tests\033[0m\n'
	cd data_prep && uv run pytest -q

deploy-lambda: ## Build Lambda zip (linux/x86_64 wheels) and update the function code
	@echo "==> Building Lambda package"
	rm -rf /tmp/lambda-build && mkdir /tmp/lambda-build
	cp server/handler.py /tmp/lambda-build/
	cp -r python_lib /tmp/lambda-build/python_lib
	pip3 install --quiet -t /tmp/lambda-build \
	  --platform manylinux2014_x86_64 --python-version 3.12 \
	  --only-binary :all: --upgrade \
	  "boto3>=1.35.0" "PyJWT>=2.9.0" "cryptography>=43.0.0"
	cd /tmp/lambda-build && zip -qr $(CURDIR)/infra/lambda_function.zip .
	@echo "==> Staging Lambda package via S3"
	AWS_PROFILE=$(AWS_PROFILE) aws s3 cp $(CURDIR)/infra/lambda_function.zip \
	  s3://observarium-data-0b5ad51e/_lambda/lambda_function.zip --quiet
	@echo "==> Updating Lambda function code"
	AWS_PROFILE=$(AWS_PROFILE) aws lambda update-function-code \
	  --function-name observarium \
	  --s3-bucket observarium-data-0b5ad51e \
	  --s3-key _lambda/lambda_function.zip \
	  --query '{LastModified:LastModified,CodeSize:CodeSize}' \
	  --output json

deploy-client: ## Build client and sync to S3
	cd client && VITE_APP_VERSION_DATE=$$(date +%Y-%m-%d) npm run build
