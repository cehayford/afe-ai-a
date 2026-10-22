variable "environment" {
  type    = string
  default = "staging"
}

variable "region" {
  description = "Primary region. Decision B11/D2: af-south-1 (Cape Town) or eu-west-1 (Ireland); af-south-1 must be enabled on the account first."
  type        = string
  default     = "af-south-1"
}

variable "backup_region" {
  description = "Second region for backup copies (decision D20)."
  type        = string
  default     = "eu-west-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "api_image" {
  description = "API container image (ECR URI with tag). Pushed by CI."
  type        = string
  default     = ""
}

variable "web_image" {
  description = "Frontend container image (ECR URI with tag). Pushed by CI."
  type        = string
  default     = ""
}

variable "web_domain" {
  description = "Public hostname of the site, e.g. staging.afe.example. Used for ORIGIN and payment returns."
  type        = string
  default     = "staging.afe.example"
}

variable "api_domain" {
  description = "Public hostname of the API for the mobile apps, e.g. api.staging.afe.example. It must be on certificate_arn. Empty = the API stays private (website only)."
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate for web_domain in the primary region. Empty = HTTP only (not for real users)."
  type        = string
  default     = ""
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "api_desired_count" {
  type    = number
  default = 2
}

variable "web_desired_count" {
  type    = number
  default = 2
}

variable "alert_email" {
  description = "Where alarms go (confirm the SNS subscription email). Empty = no email subscription."
  type        = string
  default     = ""
}

variable "email_domain" {
  description = "Domain Afe sends email from (verified in SES with DKIM), e.g. afe.com.gh."
  type        = string
  default     = ""
}

variable "whatsapp_phone_number_id" {
  description = "WhatsApp Business phone number ID from Meta (not secret)."
  type        = string
  default     = ""
}

variable "whatsapp_business_account_id" {
  description = "WhatsApp Business Account ID from Meta (not secret); used to submit message templates."
  type        = string
  default     = ""
}

variable "allow_fake_providers" {
  description = "Staging only, until B5 picks the KYC partner: lets the API start with the fake KYC check. Never in production."
  type        = bool
  default     = false
}

variable "gitlab_project_path" {
  description = "The GitLab project whose pipelines may push images (group/project)."
  type        = string
  default     = "cehayford/afe-ai"
}

variable "ci_branches" {
  description = "Branches whose pipelines may push images. Protect them in GitLab."
  type        = list(string)
  default     = ["staging", "main"]
}

variable "gitlab_oidc_provider_arn" {
  description = "An existing GitLab OIDC provider in this AWS account (another stack created it). Empty: create one."
  type        = string
  default     = ""
}
