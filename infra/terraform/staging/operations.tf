# Operations: scheduled jobs, alarms and outbound email.

# --- Scheduled jobs -----------------------------------------------------------------------------
# Frequent jobs (every minute or 5 minutes) run in one always-on worker task: `python -m app.cli
# worker` (backend/app/worker.py). Starting a task per run cost more than the work itself.
# Daily jobs are `python -m app.cli <command>` in a small task with the API's image, settings and
# secrets, but without the ClamAV sidecar. EventBridge Scheduler starts it on ECS.

locals {
  jobs = {
    "reconcile"       = "cron(0 2 * * ? *)"   # ledger vs the partner's statement, 02:00 Accra (UTC+0)
    "detect-graph"    = "cron(0 3 * * ? *)"   # linked-account graph, 03:00
    "reverify"        = "cron(0 4 * * ? *)"   # expiry warnings, pause lapsed listings, 04:00
    "rent-reminders"  = "cron(0 7 * * ? *)"   # landlord tools: rent due and overdue, 07:00
    "pilot-report"    = "cron(0 8 * * ? *)"   # founder money report while payments are on, 08:00
    "weekly-models"   = "cron(0 5 ? * MON *)" # weekly model report and shadow retraining, Mondays 05:00
    "whatsapp-health" = "cron(0 6 * * ? *)"   # WhatsApp templates that keep failing, 06:00
  }
}

resource "aws_ecs_task_definition" "jobs" {
  family                   = "${local.name}-jobs"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn
  container_definitions = jsonencode([{
    name        = "job"
    image       = var.api_image
    essential   = true
    command     = ["python", "-m", "app.cli", "--help"] # replaced per schedule
    environment = local.api_environment
    secrets     = local.api_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["api"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "jobs"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn
  container_definitions = jsonencode([{
    name        = "worker"
    image       = var.api_image
    essential   = true
    command     = ["python", "-m", "app.cli", "worker"]
    environment = local.api_environment
    secrets     = local.api_secrets
    stopTimeout = 60 # finish the current job after SIGTERM
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["api"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1 # exactly one: the jobs are safe to repeat, but not designed to run in parallel
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.api.id]
  }
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
}

# A frequent job that fails logs "worker_job_failed" (the worker keeps going).
resource "aws_cloudwatch_log_metric_filter" "worker_job_failed" {
  name           = "${local.name}-worker-job-failed"
  log_group_name = aws_cloudwatch_log_group.this["api"].name
  pattern        = "\"worker_job_failed\""
  metric_transformation {
    name      = "WorkerJobFailures"
    namespace = "Afe/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_job_failed" {
  alarm_name          = "${local.name}-worker-job-failed"
  alarm_description   = "A frequent job failed 3 times in 15 minutes. Search the api log group for worker_job_failed."
  namespace           = "Afe/${var.environment}"
  metric_name         = "WorkerJobFailures"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  threshold           = 2
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = ["${replace(aws_ecs_task_definition.jobs.arn, "/:\\d+$/", "")}:*"]
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.api_task.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "jobs" {
  for_each            = local.jobs
  name                = "${local.name}-${each.key}"
  schedule_expression = each.value
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.jobs.arn
      launch_type         = "FARGATE"
      group               = "scheduled"
      network_configuration {
        subnets         = module.vpc.private_subnets
        security_groups = [aws_security_group.api.id]
      }
    }
    input = jsonencode({
      containerOverrides = [{ name = "job", command = ["python", "-m", "app.cli", each.key] }]
    })
    retry_policy {
      maximum_retry_attempts = 1
    }
  }
}

# --- Alarms --------------------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "aws_iam_policy_document" "alerts" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "cloudwatch.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

# A scheduled job that exits with an error (reconcile exits 1 on any difference).
resource "aws_cloudwatch_event_rule" "job_failed" {
  name = "${local.name}-job-failed"
  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.main.arn]
      group      = ["scheduled"]
      lastStatus = ["STOPPED"]
      containers = { exitCode = [{ "anything-but" = 0 }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "job_failed" {
  rule = aws_cloudwatch_event_rule.job_failed.name
  arn  = aws_sns_topic.alerts.arn
}

resource "aws_cloudwatch_metric_alarm" "server_errors" {
  alarm_name          = "${local.name}-5xx"
  alarm_description   = "The web app or API is returning server errors."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "slow_pages" {
  alarm_name          = "${local.name}-slow"
  alarm_description   = "Pages are slow: p95 response time over 2 seconds for 15 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 2
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "service_down" {
  for_each            = { api = aws_ecs_service.api.name, web = aws_ecs_service.web.name, worker = aws_ecs_service.worker.name }
  alarm_name          = "${local.name}-${each.key}-down"
  alarm_description   = "No running ${each.key} tasks."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  dimensions          = { ClusterName = aws_ecs_cluster.main.name, ServiceName = each.value }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "database_storage" {
  alarm_name          = "${local.name}-db-storage"
  alarm_description   = "Database free storage under 5 GB."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.main.identifier }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5 * 1024 * 1024 * 1024
  comparison_operator = "LessThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# --- Email (Amazon SES) -----------------------------------------------------------------------------
# Add the TXT and three DKIM CNAME records (outputs) at the domain's DNS host.

resource "aws_ses_domain_identity" "mail" {
  count  = var.email_domain == "" ? 0 : 1
  domain = var.email_domain
}

resource "aws_ses_domain_dkim" "mail" {
  count  = var.email_domain == "" ? 0 : 1
  domain = aws_ses_domain_identity.mail[0].domain
}

# Unexpected errors in the API: each is one log line with "unhandled_error" and a reference.
resource "aws_cloudwatch_log_metric_filter" "unhandled_errors" {
  name           = "${local.name}-unhandled-errors"
  log_group_name = aws_cloudwatch_log_group.this["api"].name
  pattern        = "\"unhandled_error\""
  metric_transformation {
    name      = "UnhandledErrors"
    namespace = "Afe/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "unhandled_errors" {
  alarm_name          = "${local.name}-unhandled-errors"
  alarm_description   = "The API hit unexpected errors. Search the api log group for the reference."
  namespace           = "Afe/${var.environment}"
  metric_name         = "UnhandledErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
