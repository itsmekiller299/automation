resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "redis_auth" {
  length  = 48
  special = false
}

resource "random_password" "admin_key" {
  length  = 40
  special = false
}

locals {
  admin_api_key = var.admin_api_key != "" ? var.admin_api_key : random_password.admin_key.result

  # Only values that must stay secret live in the JSON secret. Non-secret
  # configuration is passed as plain ECS environment variables below.
  secret_values = {
    DATABASE_URL      = "postgresql+psycopg://${var.db_username}:${random_password.db.result}@${aws_db_instance.main.address}:5432/${var.db_name}?sslmode=require"
    REDIS_URL         = "rediss://:${random_password.redis_auth.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
    APP_SECRET        = var.app_secret
    VERIFY_TOKEN      = var.verify_token
    ADMIN_API_KEY     = local.admin_api_key
    WHATSAPP_TOKEN    = var.whatsapp_token
    IG_PAGE_TOKEN     = var.ig_page_token
    ORDERS_API_TOKEN  = var.orders_api_token
    SLACK_WEBHOOK_URL = var.slack_webhook_url
    SMTP_PASSWORD     = var.smtp_password
    LLM_API_KEY       = var.llm_api_key
  }

  public_base_url = var.public_base_url != "" ? var.public_base_url : (
    "${var.certificate_arn != "" ? "https" : "http"}://${aws_lb.main.dns_name}"
  )
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}/${var.environment}/app"
  description             = "Orbit application configuration and credentials"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.secret_values)
}
