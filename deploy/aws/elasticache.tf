resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project}-${var.environment}-redis"
  description          = "Orbit Celery broker, sessions, and idempotency cache"

  engine         = "redis"
  engine_version = var.redis_engine_version
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = var.redis_num_cache_clusters
  automatic_failover_enabled = var.redis_num_cache_clusters > 1
  multi_az_enabled           = var.redis_num_cache_clusters > 1

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth.result

  maintenance_window         = "sun:05:00-sun:06:00"
  apply_immediately          = false
  auto_minor_version_upgrade = true
}
