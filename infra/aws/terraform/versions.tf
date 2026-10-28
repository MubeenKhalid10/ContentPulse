terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State lives in an encrypted, versioned S3 bucket with a DynamoDB lock, never
  # on a laptop. The bucket, region and lock table are yours, so they are given
  # at init time (see backend.hcl.example and the README):
  #   terraform init -backend-config=backend.hcl
  # (An existing local state is copied over with `-migrate-state`.)
  backend "s3" {
    key     = "contentpulse/prod.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name     = "${var.project}-${var.environment}"
  https    = var.certificate_arn != ""
  hostname = var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name
  app_url  = "${local.https ? "https" : "http"}://${local.hostname}"
}
