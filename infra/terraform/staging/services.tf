# Both apps on ECS Fargate behind one load balancer. The frontend serves every page; the API
# is reachable from the frontend and, for partner webhooks only, through the load balancer.

resource "aws_ecr_repository" "this" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["api", "web"])
  name              = "/afe/${var.environment}/${each.key}"
  retention_in_days = 90
}

# Secrets are created empty here; set their values in the console or CLI, never in code.
resource "aws_secretsmanager_secret" "api" {
  for_each = toset([
    "AFE_SECRET_KEY", "AFE_PII_HASH_KEY", "AFE_DATABASE_URL", "AFE_PAYSTACK_SECRET_KEY",
    "AFE_WHATSAPP_APP_SECRET", "AFE_WHATSAPP_VERIFY_TOKEN", "AFE_WHATSAPP_ACCESS_TOKEN",
    "AFE_HUBTEL_CLIENT_ID", "AFE_HUBTEL_CLIENT_SECRET",
  ])
  name = "${local.name}/api/${each.key}"
}

# --- IAM -----------------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [for s in aws_secretsmanager_secret.api : s.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "api_task" {
  name               = "${local.name}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Least privilege: the API writes photos and documents and reads documents back for
# reviewers. It cannot delete, and nothing else can read the KYC bucket.
data "aws_iam_policy_document" "api_task" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this["media_public"].arn}/*", "${aws_s3_bucket.this["media_originals"].arn}/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.this["kyc_private"].arn}/*"]
  }
  statement {
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [aws_kms_key.kyc.arn]
  }
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      variable = "ses:FromAddress"
      values   = ["*@${var.email_domain == "" ? "example.invalid" : var.email_domain}"]
    }
  }
}

resource "aws_iam_role_policy" "api_task" {
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_task.json
}

# --- Load balancer ------------------------------------------------------------------------------

resource "aws_lb" "main" {
  name            = local.name
  subnets         = module.vpc.public_subnets
  security_groups = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "web" {
  name        = "${local.name}-web"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
  health_check {
    path = "/"
  }
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
  health_check {
    path = "/healthz"
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = var.certificate_arn == "" ? "forward" : "redirect"
    target_group_arn = var.certificate_arn == "" ? aws_lb_target_group.web.arn : null
    dynamic "redirect" {
      for_each = var.certificate_arn == "" ? [] : [1]
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

# Only the partner webhooks reach the API directly from the internet.
resource "aws_lb_listener_rule" "webhooks" {
  listener_arn = var.certificate_arn == "" ? aws_lb_listener.http.arn : aws_lb_listener.https[0].arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern {
      values = ["/api/v1/payments/webhook", "/api/v1/webhooks/whatsapp", "/api/v1/tenancies/webhook"]
    }
  }
}

# The mobile apps call the API directly on its own hostname (the website still goes through
# Cloud Map). Rate limits see the app's real address: uvicorn trusts X-Forwarded-For only from
# inside the VPC, and the load balancer appends the caller's address to it.
resource "aws_lb_listener_rule" "public_api" {
  count        = var.api_domain == "" ? 0 : 1
  listener_arn = var.certificate_arn == "" ? aws_lb_listener.http.arn : aws_lb_listener.https[0].arn
  priority     = 20
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    host_header {
      values = [var.api_domain]
    }
  }
}

# The frontend reaches the API through Cloud Map service discovery, never over the internet.
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${var.environment}.afe.internal"
  vpc  = module.vpc.vpc_id
}

resource "aws_service_discovery_service" "api" {
  name = "api"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
}

# --- Tasks and services ------------------------------------------------------------------------------

locals {
  public_url = var.certificate_arn == "" ? "http://${var.web_domain}" : "https://${var.web_domain}"
  # Shared by the API service and the scheduled jobs (operations.tf).
  api_environment = [
    { name = "AFE_FRONTEND_URL", value = local.public_url },
    { name = "FORWARDED_ALLOW_IPS", value = var.vpc_cidr }, # see backend/Dockerfile
    { name = "AFE_STORAGE_BACKEND", value = "s3" },
    { name = "AFE_S3_REGION", value = var.region },
    { name = "AFE_S3_BUCKET_PUBLIC", value = aws_s3_bucket.this["media_public"].id },
    { name = "AFE_S3_BUCKET_PRIVATE", value = aws_s3_bucket.this["kyc_private"].id },
    { name = "AFE_MEDIA_URL", value = "https://${aws_cloudfront_distribution.media.domain_name}" },
    { name = "AFE_PAYMENT_PROVIDER", value = "app.modules.billing.providers.Paystack" },
    # Uploaded documents are scanned by the ClamAV sidecar before storage (fail closed).
    { name = "AFE_MALWARE_SCANNER", value = "app.modules.media.scan.ClamAvScanner" },
    { name = "AFE_CLAMD_HOST", value = "127.0.0.1" },
    { name = "AFE_CLAMD_PORT", value = "3310" },
    # Real message providers (credentials are secrets above).
    { name = "AFE_SMS_PROVIDER", value = "app.modules.notifications.providers.HubtelSms" },
    { name = "AFE_WHATSAPP_PROVIDER", value = "app.modules.notifications.providers.WhatsAppCloud" },
    { name = "AFE_WHATSAPP_PHONE_NUMBER_ID", value = var.whatsapp_phone_number_id },
    { name = "AFE_WHATSAPP_BUSINESS_ACCOUNT_ID", value = var.whatsapp_business_account_id },
    { name = "AFE_EMAIL_PROVIDER", value = "app.modules.notifications.providers.SesEmail" },
    { name = "AFE_EMAIL_FROM", value = var.email_domain == "" ? "" : "Afe <no-reply@${var.email_domain}>" },
    { name = "AFE_SES_REGION", value = var.region },
    { name = "AFE_ALLOW_FAKE_PROVIDERS", value = var.allow_fake_providers ? "1" : "0" },
  ]
  api_secrets = [for k, s in aws_secretsmanager_secret.api : { name = k, valueFrom = s.arn }]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  # 4 GB: the ClamAV sidecar keeps its signature database (~1.5 GB) in memory.
  cpu                = 1024
  memory             = 4096
  execution_role_arn = aws_iam_role.execution.arn
  task_role_arn      = aws_iam_role.api_task.arn
  container_definitions = jsonencode([{
    name         = "api"
    image        = var.api_image
    essential    = true
    portMappings = [{ containerPort = 8000 }]
    environment  = local.api_environment
    secrets      = local.api_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["api"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
    }, {
    # ClamAV updates its own signatures (freshclam) and listens on localhost:3310 inside the task.
    name         = "clamav"
    image        = "clamav/clamav:stable"
    essential    = true
    portMappings = [{ containerPort = 3310 }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["api"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "clamav"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  container_definitions = jsonencode([{
    name         = "web"
    image        = var.web_image
    essential    = true
    portMappings = [{ containerPort = 3000 }]
    environment = [
      { name = "ORIGIN", value = local.public_url },
      { name = "AFE_API_URL", value = "http://api.${aws_service_discovery_private_dns_namespace.main.name}:8000" },
      { name = "BODY_SIZE_LIMIT", value = "20M" },
      # The ALB appends the browser's address; the web server forwards it to the API for rate limits.
      { name = "ADDRESS_HEADER", value = "X-Forwarded-For" },
      { name = "XFF_DEPTH", value = "1" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["web"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "web"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.api.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

resource "aws_ecs_service" "web" {
  name            = "web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.web.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}
