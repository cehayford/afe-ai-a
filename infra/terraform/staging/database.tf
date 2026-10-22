# PostgreSQL with point-in-time recovery (RPO minutes) and daily copies to a second
# region (Statement §8.7). Restore drills: before launch and every quarter.

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.name}-pg16"
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 200
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name                     = "afe"
  username                    = "afe"
  manage_master_user_password = true # password in Secrets Manager, rotated by AWS

  multi_az               = true
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name
  publicly_accessible    = false

  backup_retention_period   = 35
  backup_window             = "02:00-03:00" # Accra is UTC+0
  maintenance_window        = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot     = true
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-final"

  performance_insights_enabled = true
}

# --- AWS Backup: daily snapshot copied to the second region ------------------------------

resource "aws_backup_vault" "primary" {
  name = "${local.name}-primary"
}

resource "aws_backup_vault" "copy" {
  provider = aws.backup
  name     = "${local.name}-copy"
}

resource "aws_backup_plan" "daily" {
  name = "${local.name}-daily"
  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 3 * * ? *)"
    lifecycle {
      delete_after = 35
    }
    copy_action {
      destination_vault_arn = aws_backup_vault.copy.arn
      lifecycle {
        delete_after = 35
      }
    }
  }
  rule {
    rule_name         = "monthly"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 4 1 * ? *)"
    lifecycle {
      delete_after = 365
    }
    copy_action {
      destination_vault_arn = aws_backup_vault.copy.arn
      lifecycle {
        delete_after = 365
      }
    }
  }
}

data "aws_iam_policy_document" "backup_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name               = "${local.name}-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_assume.json
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "database" {
  name         = "${local.name}-database"
  plan_id      = aws_backup_plan.daily.id
  iam_role_arn = aws_iam_role.backup.arn
  resources    = [aws_db_instance.main.arn]
}
