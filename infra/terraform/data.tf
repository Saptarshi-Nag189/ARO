# ── Container registry ───────────────────────────────────────────────

resource "aws_ecr_repository" "aro" {
  name                 = var.project
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_last_10" {
  repository = aws_ecr_repository.aro.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ── Reports bucket ────────────────────────────────────────────────────

resource "aws_s3_bucket" "reports" {
  bucket_prefix = "${var.project}-reports-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ── Checkpoint store: RDS Postgres (LangGraph durable execution) ──────

resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db"
  subnet_ids = aws_subnet.public[*].id
}

resource "aws_db_instance" "checkpoints" {
  identifier        = "${var.project}-checkpoints"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage

  db_name  = "aro"
  username = "aro"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  skip_final_snapshot     = true
  backup_retention_period = 1
  apply_immediately       = true
}

# ── Secrets ───────────────────────────────────────────────────────────
# API keys are created empty; set their values once, out-of-band:
#   aws secretsmanager put-secret-value --secret-id aro/openrouter-api-key \
#     --secret-string 'sk-or-v1-...'

resource "aws_secretsmanager_secret" "openrouter_key" {
  name                    = "${var.project}/openrouter-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "langsmith_key" {
  name                    = "${var.project}/langsmith-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "checkpoint_uri" {
  name                    = "${var.project}/checkpoint-uri"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "checkpoint_uri" {
  secret_id     = aws_secretsmanager_secret.checkpoint_uri.id
  secret_string = "postgresql://aro:${random_password.db.result}@${aws_db_instance.checkpoints.address}:5432/aro"
}
