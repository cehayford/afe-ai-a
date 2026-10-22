terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # State lives in a separate, versioned S3 bucket with a DynamoDB lock table. Create those
  # once by hand (or in a bootstrap stack), then uncomment:
  # backend "s3" {
  #   bucket         = "afe-terraform-state"
  #   key            = "staging/terraform.tfstate"
  #   region         = "af-south-1"
  #   dynamodb_table = "afe-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "afe", Environment = var.environment, ManagedBy = "terraform" }
  }
}

# Backup copies go to a second region (Statement §8.7, decision D20).
provider "aws" {
  alias  = "backup"
  region = var.backup_region
}
