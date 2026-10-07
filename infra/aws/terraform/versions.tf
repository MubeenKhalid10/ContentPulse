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

  # Optional: keep state in S3 so a team can share it. Create the bucket first,
  # then uncomment and run `terraform init -migrate-state`.
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "contentpulse/prod.tfstate"
  #   region = "us-east-1"
  # }
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
