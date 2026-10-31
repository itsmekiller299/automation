resource "aws_lb" "main" {
  name               = "${var.project}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  idle_timeout                     = 120
  enable_deletion_protection       = var.db_deletion_protection
  enable_http2                     = true
  enable_cross_zone_load_balancing = true
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project}-${var.environment}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/readyz"
    matcher             = "200"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group" "dashboard" {
  name        = "${var.project}-${var.environment}-web"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  count = var.certificate_arn == "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard.arn
  }
}

resource "aws_lb_listener" "redirect" {
  count = var.certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard.arn
  }
}

locals {
  active_listener_arn = one(concat(
    aws_lb_listener.https[*].arn,
    aws_lb_listener.http[*].arn,
  ))

  api_path_rules = {
    api = {
      priority = 10
      paths    = ["/api/*", "/webhook/*", "/internal/*"]
    }
    health = {
      priority = 20
      paths    = ["/healthz", "/readyz", "/health"]
    }
    docs = {
      priority = 30
      paths    = ["/docs", "/docs/*", "/openapi.json"]
    }
  }
}

resource "aws_lb_listener_rule" "api" {
  for_each = local.api_path_rules

  listener_arn = local.active_listener_arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = each.value.paths
    }
  }
}
