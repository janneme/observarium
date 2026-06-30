.DEFAULT_GOAL := help
AWS_PROFILE   ?= personal
MAG           ?= 9

.PHONY: help deploy deploy-lambda deploy-client dev dev-server dev-client data-prep data-upload-local data-upload-s3 lint test

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

deploy: ## Apply Terraform, deploy Lambda, sync data, deploy client
	@echo "==> OpenTofu init"
	cd infra && tofu init -upgrade
	@echo "==> OpenTofu apply"
	cd infra && tofu apply -auto-approve
	@echo "==> Deploy Lambda"
	$(MAKE) deploy-lambda
	@echo "==> Sync data to S3"
	@DATA_BUCKET=$$(cd infra && tofu output -raw data_bucket_name); \
	$(MAKE) data-upload-s3 DATA_BUCKET=$$DATA_BUCKET
	@echo "==> Deploy client to S3"
	$(MAKE) deploy-client
	@echo "==> Deployment endpoints"
	@echo "Client: $$(cd infra && tofu output -raw cloudfront_url)"
	@echo "Server: $$(cd infra && tofu output -raw lambda_function_url)"

dev: ## Run both frontend and backend development servers
	python3 run.py

dev-server: ## Run the Lambda handler via the local HTTP wrapper
	$(MAKE) -C server dev

dev-client: ## Start the Vite dev server for the Svelte client
	cd client && VITE_APP_VERSION_DATE=$$(date +%Y-%m-%d) npm run dev

data-prep: ## Run the data preparation pipeline
	cd data_prep && uv run python main.py $(ARGS)

data-upload-local: ## Bundle and upload data to local storage backend
	cd data_prep && STORAGE=local PYTHONPATH=.. uv run python data_upload.py $(if $(findstring command line,$(origin MAG)),--mag $(MAG),)

data-upload-s3: ## Bundle and upload data to S3 (requires DATA_BUCKET)
	cd data_prep && STORAGE=s3 DATA_BUCKET=$(DATA_BUCKET) PYTHONPATH=.. uv run python data_upload.py $(if $(findstring command line,$(origin MAG)),--mag $(MAG),)

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
	@DATA_BUCKET=$$(cd infra && tofu output -raw data_bucket_name); \
	AWS_PROFILE=$(AWS_PROFILE) aws s3 cp $(CURDIR)/infra/lambda_function.zip \
	  s3://$$DATA_BUCKET/_lambda/lambda_function.zip --quiet
	@echo "==> Updating Lambda function code"
	@DATA_BUCKET=$$(cd infra && tofu output -raw data_bucket_name); \
	AWS_PROFILE=$(AWS_PROFILE) aws lambda update-function-code \
	  --function-name observarium \
	  --s3-bucket $$DATA_BUCKET \
	  --s3-key _lambda/lambda_function.zip \
	  --query '{LastModified:LastModified,CodeSize:CodeSize}' \
	  --output json

deploy-client: ## Build client and sync to S3
	cd client && VITE_APP_VERSION_DATE=$$(date +%Y-%m-%d) VITE_SERVER_URL=$$(cd ../infra && tofu output -raw lambda_function_url) npm run build
	@CLIENT_BUCKET=$$(cd infra && tofu output -raw client_bucket_name); \
	AWS_PROFILE=$(AWS_PROFILE) aws s3 sync client/dist/ s3://$$CLIENT_BUCKET --delete
