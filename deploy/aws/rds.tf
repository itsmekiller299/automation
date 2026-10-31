resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project}-${var.environment}-db" }
}

resource "aws_db_parameter_group" "main" {
  name   = "${var.project}-${var.environment}-pg16"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "main" {
  identifier = "${var.project}-${var.environment}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  publicly_accessible          = false
  multi_az                     = var.db_multi_az
  backup_retention_period      = var.db_backup_retention_days
  backup_window                = "03:00-04:00"
  maintenance_window           = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade   = true
  deletion_protection          = var.db_deletion_protection
  skip_final_snapshot          = var.db_skip_final_snapshot
  final_snapshot_identifier    = var.db_skip_final_snapshot ? null : "${var.project}-${var.environment}-final"
  performance_insights_enabled = false
  apply_immediately            = false

  lifecycle {
    ignore_changes = [password]
  }
}
