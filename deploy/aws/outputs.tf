output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "public_base_url" {
  value = local.public_base_url
}

output "dashboard_url" {
  value = local.public_base_url
}

output "whatsapp_webhook_url" {
  value = "${local.public_base_url}/webhook/whatsapp"
}

output "instagram_webhook_url" {
  value = "${local.public_base_url}/webhook/instagram"
}

output "ecr_repository_urls" {
  value = { for name, repo in aws_ecr_repository.repos : name => repo.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "db_address" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "redis_primary_endpoint" {
  value     = aws_elasticache_replication_group.main.primary_endpoint_address
  sensitive = true
}
