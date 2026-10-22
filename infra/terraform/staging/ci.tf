# CI's access to AWS. GitLab pipelines exchange GitLab's identity token (OIDC) for short-lived credentials, so no
# long-lived AWS keys are stored in GitLab. The role can push images to the two Afe repositories and nothing else:
# deploys stay a manual step (docs/deploy.md).

# AWS allows one OIDC provider per URL in an account. The first stack creates it; any other stack in the same account
# (production) passes its ARN in gitlab_oidc_provider_arn instead.
resource "aws_iam_openid_connect_provider" "gitlab" {
  count          = var.gitlab_oidc_provider_arn == "" ? 1 : 0
  url            = "https://gitlab.com"
  client_id_list = ["https://gitlab.com"]
}

locals {
  gitlab_oidc_provider_arn = (var.gitlab_oidc_provider_arn != "" ? var.gitlab_oidc_provider_arn
  : aws_iam_openid_connect_provider.gitlab[0].arn)
}

# Only pipelines of this project, on these branches, can take the role. Protect the branches in GitLab, so only
# maintainers can push to them.
data "aws_iam_policy_document" "ci_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.gitlab_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "gitlab.com:aud"
      values   = ["https://gitlab.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "gitlab.com:sub"
      values   = [for branch in var.ci_branches : "project_path:${var.gitlab_project_path}:ref_type:branch:ref:${branch}"]
    }
  }
}

resource "aws_iam_role" "ci" {
  name                 = "${local.name}-ci-push"
  description          = "GitLab CI: push the API and web images to ECR. Nothing else."
  assume_role_policy   = data.aws_iam_policy_document.ci_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ci_push" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # AWS doesn't scope this action to a repository
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload", "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [for repository in aws_ecr_repository.this : repository.arn]
  }
}

resource "aws_iam_role_policy" "ci_push" {
  name   = "push-images"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci_push.json
}
