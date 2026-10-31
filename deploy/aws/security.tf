resource "aws_security_group" "alb" {
  name        = "${var.project}-${var.environment}-alb"
  description = "Public ingress for the Orbit dashboard and API"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP (redirects to HTTPS when a certificate is set)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-alb" }
}

resource "aws_security_group" "ecs" {
  name        = "${var.project}-${var.environment}-ecs"
  description = "API, worker, beat, and dashboard tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "API from the load balancer"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Dashboard from the load balancer"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "ECR, CloudWatch, Secrets Manager, Meta, Anthropic, SMTP"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-ecs" }
}

resource "aws_security_group" "db" {
  name        = "${var.project}-${var.environment}-db"
  description = "PostgreSQL from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = { Name = "${var.project}-${var.environment}-db" }
}

resource "aws_security_group" "redis" {
  name        = "${var.project}-${var.environment}-redis"
  description = "Redis (TLS) from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = { Name = "${var.project}-${var.environment}-redis" }
}
