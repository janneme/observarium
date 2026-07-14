terraform {
  required_version = ">= 1.5"

  backend "s3" {
    bucket       = "observarium-tfstate-0b5ad51e"
    key          = "observarium/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  profile = "personal"
  region  = "eu-central-1"
}

# Random suffix for globally unique bucket names
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  project_name = "observarium"
  data_bucket_name = "${local.project_name}-data-${random_id.suffix.hex}"
  client_bucket_name = "${local.project_name}-client-${random_id.suffix.hex}"
}

# ============================================================================
# S3 Buckets
# ============================================================================

# Data bucket (private) - stores objects.zip, images.zip, user observations
resource "aws_s3_bucket" "data" {
  bucket = local.data_bucket_name

  tags = {
    Name = "Observarium Data Bucket"
    Project = local.project_name
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  cors_rule {
    allowed_origins = [
      "http://${aws_s3_bucket_website_configuration.client.website_endpoint}",
      "https://${aws_cloudfront_distribution.client.domain_name}",
      "http://localhost:6543",
      "http://127.0.0.1:6543"
    ]
    allowed_methods = ["GET"]
    allowed_headers = ["*"]
    expose_headers  = ["Content-Length", "ETag"]
    max_age_seconds = 3600
  }
}

# Client bucket (public website hosting)
resource "aws_s3_bucket" "client" {
  bucket = local.client_bucket_name

  tags = {
    Name = "Observarium Client Bucket"
    Project = local.project_name
  }
}

resource "aws_s3_bucket_website_configuration" "client" {
  bucket = aws_s3_bucket.client.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"  # SPA fallback
  }
}

resource "aws_s3_bucket_public_access_block" "client" {
  bucket = aws_s3_bucket.client.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "client" {
  bucket = aws_s3_bucket.client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.client.arn}/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.client]
}

# CloudFront distribution for HTTPS client delivery (default cloudfront.net domain)
resource "aws_cloudfront_distribution" "client" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Observarium client distribution"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name = aws_s3_bucket_website_configuration.client.website_endpoint
    origin_id   = "client-s3-website"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "client-s3-website"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 10
    max_ttl     = 60
  }

  # SPA fallback
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# ============================================================================
# Cognito User Pool
# ============================================================================

resource "aws_cognito_user_pool" "main" {
  name = "${local.project_name}-user-pool"

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  # Disable self-registration
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # User attributes
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  tags = {
    Name = "Observarium User Pool"
    Project = local.project_name
  }
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${local.project_name}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # Authentication flows
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  # Public client (no client secret for JavaScript apps)
  generate_secret = false

  # Token validity
  access_token_validity  = 1  # hours
  id_token_validity      = 1  # hours
  refresh_token_validity = 30 # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # generate_secret is write-only: the Cognito API never returns it, so a
  # freshly-imported resource always shows it as null in state. It's also
  # ForceNew, so without ignoring it here, every plan would want to destroy
  # and recreate this client (invalidating the real client ID in use).
  lifecycle {
    ignore_changes = [generate_secret]
  }
}

# ============================================================================
# IAM Role for Lambda
# ============================================================================

resource "aws_iam_role" "lambda" {
  name = "${local.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "Observarium Lambda Role"
    Project = local.project_name
  }
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.project_name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3DataBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:HeadObject"
        ]
        Resource = "${aws_s3_bucket.data.arn}/*"
      },
      {
        Sid    = "S3DataBucketList"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.data.arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      }
    ]
  })
}

# ============================================================================
# CloudWatch Log Group
# ============================================================================

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.project_name}"
  retention_in_days = 30

  tags = {
    Name = "Observarium Lambda Logs"
    Project = local.project_name
  }
}

# ============================================================================
# Lambda Function
# ============================================================================

# Package Lambda code
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../server"
  output_path = "${path.module}/lambda_function.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "tests"]
}

resource "aws_lambda_function" "main" {
  filename         = data.archive_file.lambda.output_path
  function_name    = local.project_name
  role            = aws_iam_role.lambda.arn
  handler         = "handler.lambda_handler"
  source_code_hash = data.archive_file.lambda.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30
  memory_size     = 256

  environment {
    variables = {
      DATA_BUCKET          = aws_s3_bucket.data.bucket
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.main.id
      COGNITO_REGION       = "eu-central-1"
      STORAGE              = "s3"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda
  ]

  tags = {
    Name = "Observarium Lambda"
    Project = local.project_name
  }
}

# Lambda Function URL
resource "aws_lambda_function_url" "main" {
  function_name      = aws_lambda_function.main.function_name
  authorization_type = "NONE"

  cors {
    allow_origins     = [
      "http://${aws_s3_bucket_website_configuration.client.website_endpoint}",
      "https://${aws_cloudfront_distribution.client.domain_name}",
      "http://localhost:6543",
      "http://127.0.0.1:6543"
    ]
    allow_methods     = ["GET", "POST", "DELETE"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = []
    max_age          = 86400
  }
}

# Lambda permissions for public function URL access (required as of October 2025)
# See: https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html
resource "aws_lambda_permission" "function_url_invoke_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.main.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "function_url_invoke" {
  statement_id  = "FunctionURLInvokeAllowPublicAccess"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "*"
  
  # Restricts InvokeFunction to only calls made through the function URL
  qualifier = null
  
  # This is handled by source_arn or invoked_via_function_url in newer providers
  # For now, we rely on the condition key being set by --invoked-via-function-url flag
  # which Terraform doesn't directly support, so we manage this via CLI/import
}

# ============================================================================
# Outputs
# ============================================================================

output "data_bucket_name" {
  description = "Name of the S3 bucket for data storage"
  value       = aws_s3_bucket.data.bucket
}

output "client_bucket_name" {
  description = "Name of the S3 bucket for client hosting"
  value       = aws_s3_bucket.client.bucket
}

output "client_website_endpoint" {
  description = "S3 website endpoint for the client"
  value       = aws_s3_bucket_website_configuration.client.website_endpoint
}

output "client_website_url" {
  description = "Full URL for the client website"
  value       = "http://${aws_s3_bucket_website_configuration.client.website_endpoint}"
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.client.domain_name
}

output "cloudfront_url" {
  description = "CloudFront HTTPS URL for client access"
  value       = "https://${aws_cloudfront_distribution.client.domain_name}"
}

output "lambda_function_url" {
  description = "Lambda Function URL for API access"
  value       = aws_lambda_function_url.main.function_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "cognito_region" {
  description = "AWS region for Cognito"
  value       = "eu-central-1"
}
