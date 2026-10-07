# ECS Fargate: one backend image in three roles (api, worker, beat), the web
# image, and a one-off migration task that deploy.sh runs before each rollout.

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = !var.protect_data

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "repo" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 20 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  api_image = "${aws_ecr_repository.repo["api"].repository_url}:${var.image_tag}"
  web_image = "${aws_ecr_repository.repo["web"].repository_url}:${var.image_tag}"

  backend_environment = [
    for name, value in {
      APP_ENV             = "production"
      LOG_LEVEL           = "INFO"
      AUTH_PROVIDER       = var.auth_provider
      LLM_PROVIDER        = var.llm_provider
      TASK_BACKEND        = "celery"
      REDIS_URL           = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
      S3_BUCKET           = aws_s3_bucket.creatives.bucket
      AWS_REGION          = var.region
      FRONTEND_URL        = local.app_url
      CORS_ORIGINS        = jsonencode([local.app_url])
      COOKIE_SECURE       = local.https ? "true" : "false"
      TRUSTED_PROXY_COUNT = "1" # the load balancer appends the client address
    } : { name = name, value = value }
  ]
  backend_secrets = [
    for key in local.secret_keys : { name = key, valueFrom = "${aws_secretsmanager_secret.app.arn}:${key}::" }
  ]

  log_config = {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.app.name
      awslogs-region        = var.region
      awslogs-stream-prefix = "ecs"
    }
  }

  backend_roles = {
    api    = { command = null, port = 8000 }
    worker = { command = ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"], port = null }
    beat   = { command = ["celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info", "--schedule", "/tmp/celerybeat-schedule"], port = null }
  }
}

resource "aws_ecs_task_definition" "backend" {
  for_each                 = local.backend_roles
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.services[each.key].cpu
  memory                   = var.services[each.key].memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([merge(
    {
      name             = each.key
      image            = local.api_image
      essential        = true
      environment      = local.backend_environment
      secrets          = local.backend_secrets
      logConfiguration = merge(local.log_config, { options = merge(local.log_config.options, { awslogs-stream-prefix = each.key }) })
    },
    each.value.command == null ? {} : { command = each.value.command },
    each.value.port == null ? {} : { portMappings = [{ containerPort = each.value.port, protocol = "tcp" }] },
  )])
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name             = "migrate"
    image            = local.api_image
    essential        = true
    command          = ["alembic", "upgrade", "head"]
    environment      = local.backend_environment
    secrets          = local.backend_secrets
    logConfiguration = merge(local.log_config, { options = merge(local.log_config.options, { awslogs-stream-prefix = "migrate" }) })
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.services["web"].cpu
  memory                   = var.services["web"].memory
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name             = "web"
    image            = local.web_image
    essential        = true
    portMappings     = [{ containerPort = 3000, protocol = "tcp" }]
    logConfiguration = merge(local.log_config, { options = merge(local.log_config.options, { awslogs-stream-prefix = "web" }) })
  }])
}

locals {
  network = {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "backend" {
  for_each        = local.backend_roles
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend[each.key].arn
  desired_count   = var.services[each.key].count
  launch_type     = "FARGATE"

  # Beat: stop the old task before starting the new one (never two schedulers).
  deployment_minimum_healthy_percent = each.key == "beat" ? 0 : 100
  deployment_maximum_percent         = each.key == "beat" ? 100 : 200

  network_configuration {
    subnets          = local.network.subnets
    security_groups  = local.network.security_groups
    assign_public_ip = local.network.assign_public_ip
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "api"
      container_port   = 8000
    }
  }

  health_check_grace_period_seconds = each.key == "api" ? 60 : null
  depends_on                        = [aws_lb_listener.http]
}

resource "aws_ecs_service" "web" {
  name                              = "web"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.web.arn
  desired_count                     = var.services["web"].count
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = local.network.subnets
    security_groups  = local.network.security_groups
    assign_public_ip = local.network.assign_public_ip
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.http]
}
