# Ordy production infrastructure (doc 01 §6).
# EU region for data residency; managed Postgres/Redis so we operate the product, not the
# database. Everything stateful gets encryption at rest with a customer-managed KMS key.

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    key = "ordy/prod/terraform.tfstate"
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type        = string
  default     = "eu-west-1"
  description = "EU by default — GDPR data residency (doc 08 §7)."
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

locals {
  name = "ordy-${var.environment}"
  tags = {
    Project     = "ordy"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---- Network ----------------------------------------------------------------

module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  name   = local.name
  cidr   = "10.20.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
  public_subnets  = ["10.20.101.0/24", "10.20.102.0/24", "10.20.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false # per-AZ: an AZ outage must not take voice down
  tags               = local.tags
}

# ---- Encryption -------------------------------------------------------------

resource "aws_kms_key" "primary" {
  description             = "Ordy envelope-encryption master key (doc 08 §4)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = local.tags
}

resource "aws_kms_alias" "primary" {
  name          = "alias/${local.name}-primary"
  target_key_id = aws_kms_key.primary.key_id
}

# ---- Data stores ------------------------------------------------------------

module "postgres" {
  source     = "terraform-aws-modules/rds/aws"
  identifier = "${local.name}-pg"

  engine                = "postgres"
  engine_version        = "16"
  instance_class        = var.db_instance_class
  allocated_storage     = 100
  max_allocated_storage = 500

  db_name  = "ordy"
  username = "ordy_migrator"
  port     = 5432

  multi_az               = true
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.primary.arn
  vpc_security_group_ids = [aws_security_group.postgres.id]
  subnet_ids             = module.vpc.private_subnets

  # RPO <= 15 min via PITR (doc 08 §10).
  backup_retention_period         = 14
  backup_window                   = "02:00-03:00"
  enabled_cloudwatch_logs_exports = ["postgresql"]
  deletion_protection             = true

  # pgvector for retrieval (ADR-005).
  parameter_group_name = aws_db_parameter_group.pg.name
  tags                 = local.tags
}

resource "aws_db_parameter_group" "pg" {
  name   = "${local.name}-pg16"
  family = "postgres16"

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }
  tags = local.tags
}

resource "aws_security_group" "postgres" {
  name   = "${local.name}-pg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
    description = "Postgres from private subnets only"
  }
  tags = local.tags
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name}-redis"
  description          = "Ordy cache, queues, sessions, rate limits"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.small"

  num_cache_clusters         = 2
  automatic_failover_enabled = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.primary.arn
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  tags                       = local.tags
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.name}-redis"
  subnet_ids = module.vpc.private_subnets
}

# ---- Object storage ---------------------------------------------------------

resource "aws_s3_bucket" "objects" {
  bucket = "${local.name}-objects"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "objects" {
  bucket = aws_s3_bucket.objects.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "objects" {
  bucket                  = aws_s3_bucket.objects.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "objects" {
  bucket = aws_s3_bucket.objects.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.primary.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "objects" {
  bucket = aws_s3_bucket.objects.id

  # Call audio defaults to 30 days (doc 06 §5); the retention worker deletes earlier when
  # a tenant asks for less. This is the backstop.
  rule {
    id     = "audio-retention"
    status = "Enabled"
    filter { prefix = "t/" }
    expiration { days = 90 }
  }
}

# ---- Outputs ----------------------------------------------------------------

output "postgres_endpoint" { value = module.postgres.db_instance_endpoint }
output "redis_endpoint"    { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "objects_bucket"    { value = aws_s3_bucket.objects.id }
output "kms_key_arn"       { value = aws_kms_key.primary.arn }
