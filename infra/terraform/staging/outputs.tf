output "load_balancer_dns" {
  description = "Point web_domain's DNS (CNAME/alias) here."
  value       = aws_lb.main.dns_name
}

output "media_cdn" {
  description = "AFE_MEDIA_URL for the API."
  value       = "https://${aws_cloudfront_distribution.media.domain_name}"
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "database_endpoint" {
  value = aws_db_instance.main.address
}

output "db_master_secret_arn" {
  description = "Secrets Manager secret holding the RDS master password (build AFE_DATABASE_URL from it)."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "ses_dns_records" {
  description = "DNS records to add so SES can send as the email domain."
  value = var.email_domain == "" ? null : {
    verification_txt = { name = "_amazonses.${var.email_domain}", value = aws_ses_domain_identity.mail[0].verification_token }
    dkim_cnames      = [for t in aws_ses_domain_dkim.mail[0].dkim_tokens : "${t}._domainkey.${var.email_domain} -> ${t}.dkim.amazonses.com"]
  }
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "ci_role_arn" {
  description = "GitLab CI/CD variable AWS_ROLE_ARN: the role pipelines take to push images."
  value       = aws_iam_role.ci.arn
}

output "ecr_registry" {
  description = "GitLab CI/CD variable ECR_REGISTRY: the registry host the images are pushed to."
  value       = split("/", aws_ecr_repository.this["api"].repository_url)[0]
}

# For one-off tasks (preflight, migrations, commands): infra/scripts/run-job.sh reads these.
output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "jobs_task_definition" {
  description = "The jobs task definition, at the revision with the current api_image."
  value       = aws_ecs_task_definition.jobs.arn
}

output "task_subnets" {
  value = join(",", module.vpc.private_subnets)
}

output "task_security_group" {
  value = aws_security_group.api.id
}
