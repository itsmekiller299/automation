resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  service_prefix = "${var.project}-${var.environment}"

  log_groups = {
    api       = "/ecs/${local.service_prefix}/api"
    worker    = "/ecs/${local.service_prefix}/worker"
    beat      = "/ecs/${local.service_prefix}/beat"
    dashboard = "/ecs/${local.service_prefix}/dashboard"
  }

  common_environment = [
    { name = "ENVIRONMENT", value = "production" },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "QUEUE_BACKEND", value = "celery" },
    { name = "CELERY_TASK_ALWAYS_EAGER", value = "false" },
    { name = "OUTBOUND_MODE", value = "auto" },
    { name = "ALLOW_UNSIGNED_WEBHOOKS", value = "false" },
    { name = "ENABLE_MOCK_ORDERS_API", value = "false" },
    { name = "DATA_RETENTION_DAYS", value = tostring(var.data_retention_days) },
    { name = "PUBLIC_BASE_URL", value = local.public_base_url },
    { name = "DASHBOARD_BASE_URL", value = local.public_base_url },
    { name = "CORS_ORIGINS", value = local.public_base_url },
    { name = "NLU_BACKEND", value = "auto" },
    { name = "NLU_MODEL_DIR", value = "/app/ml/artifacts/intent-model" },
    { name = "NLU_ONNX_PATH", value = "/app/ml/artifacts/intent-model/model.onnx" },
    { name = "NLU_EVALUATION_PATH", value = "/app/ml/artifacts/evaluation/evaluation.json" },
    { name = "RAG_BACKEND", value = "lexical" },
    { name = "FAQ_PATH", value = "/app/ml/data/faqs.jsonl" },
    { name = "ORDERS_FIXTURE_PATH", value = "/app/ml/data/orders.json" },
    { name = "ORDERS_API_URL", value = var.orders_api_url },
    { name = "PHONE_NUMBER_ID", value = var.phone_number_id },
    { name = "WHATSAPP_BUSINESS_ACCOUNT_ID", value = var.whatsapp_business_account_id },
    { name = "WHATSAPP_TEMPLATE_NAME", value = var.whatsapp_template_name },
    { name = "WHATSAPP_TEMPLATE_LANGUAGE", value = var.whatsapp_template_language },
    { name = "IG_BUSINESS_ACCOUNT_ID", value = var.ig_business_account_id },
    { name = "LLM_PROVIDER", value = var.llm_provider },
    { name = "LLM_MODEL", value = var.llm_model },
    { name = "SMTP_HOST", value = var.smtp_host },
    { name = "SMTP_PORT", value = tostring(var.smtp_port) },
    { name = "SMTP_USERNAME", value = var.smtp_username },
    { name = "SMTP_FROM", value = var.smtp_from },
    { name = "HANDOFF_EMAIL_TO", value = var.handoff_email_to },
  ]

  container_secrets = [
    for name in sort(keys(local.secret_values)) : {
      name      = name
      valueFrom = "${aws_secretsmanager_secret.app.arn}:${name}::"
    }
  ]

  api_container = {
    name      = "api"
    image     = var.api_image
    essential = true
    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
      protocol      = "tcp"
    }]
    environment = local.common_environment
    secrets     = local.container_secrets
    stopTimeout = 30
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = local.log_groups.api
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }

  worker_container = {
    name      = "worker"
    image     = var.api_image
    essential = true
    command = [
      "celery",
      "-A",
      "app.worker.celery_app.celery",
      "worker",
      "--loglevel=info",
      "--concurrency=2",
    ]
    environment = local.common_environment
    secrets     = local.container_secrets
    stopTimeout = 60
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = local.log_groups.worker
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }

  beat_container = {
    name      = "beat"
    image     = var.api_image
    essential = true
    command = [
      "celery",
      "-A",
      "app.worker.celery_app.celery",
      "beat",
      "--loglevel=info",
      "--schedule=/tmp/celerybeat-schedule",
    ]
    environment = local.common_environment
    secrets     = local.container_secrets
    stopTimeout = 30
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = local.log_groups.beat
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "beat"
      }
    }
  }

  dashboard_container = {
    name      = "dashboard"
    image     = var.dashboard_image
    essential = true
    portMappings = [{
      containerPort = 80
      hostPort      = 80
      protocol      = "tcp"
    }]
    environment = []
    secrets     = []
    stopTimeout = 30
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = local.log_groups.dashboard
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "dashboard"
      }
    }
  }
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = local.log_groups

  name              = each.value
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.service_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.api_container])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  depends_on = [
    aws_cloudwatch_log_group.services,
    aws_secretsmanager_secret_version.app,
  ]
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.service_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.worker_container])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  depends_on = [
    aws_cloudwatch_log_group.services,
    aws_secretsmanager_secret_version.app,
  ]
}

resource "aws_ecs_task_definition" "beat" {
  family                   = "${local.service_prefix}-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.beat_container])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  depends_on = [
    aws_cloudwatch_log_group.services,
    aws_secretsmanager_secret_version.app,
  ]
}

resource "aws_ecs_task_definition" "dashboard" {
  family                   = "${local.service_prefix}-dashboard"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.dashboard_cpu
  memory                   = var.dashboard_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.dashboard_container])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  depends_on = [
    aws_cloudwatch_log_group.services,
    aws_secretsmanager_secret_version.app,
  ]
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  platform_version = "LATEST"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 90

  lifecycle {
    ignore_changes = [desired_count]
  }
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }
}

resource "aws_ecs_service" "beat" {
  name            = "beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "dashboard" {
  name            = "dashboard"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.dashboard.arn
  desired_count   = var.dashboard_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.dashboard.arn
    container_name   = "dashboard"
    container_port   = 80
  }

  health_check_grace_period_seconds = 60
}

# API autoscaling on average CPU. Worker scaling on CPU is a coarse proxy;
# production should scale on Celery queue depth via a custom CloudWatch metric.
resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_min_count
  max_capacity       = var.api_max_count
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${local.service_prefix}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 1
  max_capacity       = var.worker_max_count
}

resource "aws_appautoscaling_policy" "worker_cpu" {
  name               = "${local.service_prefix}-worker-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 70

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_in_cooldown  = 180
    scale_out_cooldown = 60
  }
}
