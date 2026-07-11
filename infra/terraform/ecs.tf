# ── ECS cluster + IAM ─────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pull image, write logs, read secrets at container start
resource "aws_iam_role" "execution" {
  name               = "${var.project}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "read-app-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.openrouter_key.arn,
        aws_secretsmanager_secret.langsmith_key.arn,
        aws_secretsmanager_secret.checkpoint_uri.arn,
      ]
    }]
  })
}

# Task role: what the running app may touch
resource "aws_iam_role" "task" {
  name               = "${var.project}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task_s3" {
  name = "reports-bucket"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.reports.arn, "${aws_s3_bucket.reports.arn}/*"]
    }]
  })
}

# ── Logs ──────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/${var.project}-web"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "mcp" {
  name              = "/ecs/${var.project}-mcp"
  retention_in_days = 14
}

# ── Shared container env/secrets ──────────────────────────────────────

locals {
  image = "${aws_ecr_repository.aro.repository_url}:${var.image_tag}"

  common_env = [
    { name = "LANGSMITH_TRACING", value = "true" },
    { name = "LANGSMITH_PROJECT", value = "${var.project}-prod" },
  ]

  common_secrets = [
    { name = "OPENROUTER_API_KEY", valueFrom = aws_secretsmanager_secret.openrouter_key.arn },
    { name = "LANGSMITH_API_KEY", valueFrom = aws_secretsmanager_secret.langsmith_key.arn },
    { name = "ARO_CHECKPOINT_URI", valueFrom = aws_secretsmanager_secret.checkpoint_uri.arn },
  ]
}

# ── Web service (Flask UI + API) ──────────────────────────────────────

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "web"
    image        = local.image
    essential    = true
    portMappings = [{ containerPort = 5000, protocol = "tcp" }]
    environment = concat(local.common_env, [
      { name = "ARO_HOST", value = "0.0.0.0" },
      { name = "ARO_PORT", value = "5000" },
    ])
    secrets = local.common_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.web.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "web"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:5000/api/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_ecs_service" "web" {
  name            = "${var.project}-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 5000
  }

  depends_on = [aws_lb_listener.web]
}

# ── MCP service (remote streamable HTTP) ──────────────────────────────

resource "aws_ecs_task_definition" "mcp" {
  family                   = "${var.project}-mcp"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "mcp"
    image        = local.image
    essential    = true
    command      = ["python", "-m", "mcp_server.server", "--http", "--host", "0.0.0.0", "--port", "8001"]
    portMappings = [{ containerPort = 8001, protocol = "tcp" }]
    environment  = local.common_env
    secrets      = local.common_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.mcp.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "mcp"
      }
    }
  }])
}

resource "aws_ecs_service" "mcp" {
  name            = "${var.project}-mcp"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp.arn
  desired_count   = var.mcp_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.mcp.arn
    container_name   = "mcp"
    container_port   = 8001
  }

  depends_on = [aws_lb_listener.mcp]
}

# ── Load balancer ─────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.project}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "web" {
  name        = "${var.project}-web"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
  }
}

resource "aws_lb_target_group" "mcp" {
  name        = "${var.project}-mcp"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/mcp"
    matcher             = "200-499" # MCP endpoint rejects GETs; reachability is enough
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
  }
}

resource "aws_lb_listener" "web" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener" "mcp" {
  load_balancer_arn = aws_lb.main.arn
  port              = 8001
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mcp.arn
  }
}

# ── Observability ─────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "web_cpu_high" {
  alarm_name          = "${var.project}-web-cpu-high"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 85
  comparison_operator = "GreaterThanThreshold"
  alarm_description   = "ARO web service sustained high CPU"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.web.name
  }
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-overview"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "ECS CPU / Memory"
          region = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.web.name],
            [".", "MemoryUtilization", ".", ".", ".", "."],
          ]
          period = 300
          stat   = "Average"
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "ALB requests / 5xx"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix],
            [".", "HTTPCode_Target_5XX_Count", ".", "."],
          ]
          period = 300
          stat   = "Sum"
        }
      },
    ]
  })
}
