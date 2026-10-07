# --- PostgreSQL 17 with pgvector (the migrations run CREATE EXTENSION vector) ----------

resource "random_password" "db" {
  length  = 32
  special = false # goes into a connection URL
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier            = "${local.name}-db"
  engine                = "postgres"
  engine_version        = "17"
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "contentpulse"
  username = "contentpulse"
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.data.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period    = 7
  auto_minor_version_upgrade = true
  deletion_protection        = var.protect_data
  skip_final_snapshot        = !var.protect_data
  final_snapshot_identifier  = var.protect_data ? "${local.name}-db-final" : null
  apply_immediately          = true
}

# --- Redis: Celery broker and shared rate-limit counters -------------------------------

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id         = "${local.name}-redis"
  engine             = "redis"
  engine_version     = "7.1"
  node_type          = var.redis_node_type
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.data.id]
}

# --- S3: designer creatives (browsers upload with presigned URLs) ---------------------

resource "aws_s3_bucket" "creatives" {
  bucket        = "${local.name}-creatives-${data.aws_caller_identity.current.account_id}"
  force_destroy = !var.protect_data
}

resource "aws_s3_bucket_public_access_block" "creatives" {
  bucket                  = aws_s3_bucket.creatives.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "creatives" {
  bucket = aws_s3_bucket.creatives.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "creatives" {
  bucket = aws_s3_bucket.creatives.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_cors_configuration" "creatives" {
  bucket = aws_s3_bucket.creatives.id
  cors_rule {
    allowed_origins = [local.app_url]
    allowed_methods = ["PUT", "GET"]
    allowed_headers = ["Content-Type"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "creatives" {
  bucket = aws_s3_bucket.creatives.id
  rule {
    id     = "abandoned-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
