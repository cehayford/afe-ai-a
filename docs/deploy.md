# Deploying Afe

How Afe's code reaches AWS: once, to set staging up, and then for every release. It follows
`infra/terraform/staging/` (what exists) and `.gitlab-ci.yml` (how images are built).

**What a release is:** two images built by CI from one commit (the API, which also runs the worker and the
scheduled jobs, and the web app), any new database migrations, and a `terraform apply` that points the services at
the new images.

**The order that keeps it safe:** check first (`preflight`), then the database (migrations), then the code (apply).
Migrations only add (see "Writing migrations" below), so the code running at the time keeps working on the newer
database, and a rollback stays possible.

Commands run from `infra/terraform/staging/` with AWS credentials for the account. One-off commands run as an ECS
task with the jobs task definition, through `../../scripts/run-job.sh`: it waits, prints where the logs are, and exits
with the command's exit code.

---

## Once: setting staging up

1. **Choose the account and region** (decision B11) and fill a `terraform.tfvars` (not committed): `region`,
   `web_domain`, `certificate_arn`, `alert_email`, `email_domain`, `whatsapp_phone_number_id`,
   `whatsapp_business_account_id`, and `allow_fake_providers = true` until the KYC partner is chosen (B5).

2. **Make the state bucket and lock table** (once per account), then turn on the `backend "s3"` block in
   `versions.tf` and run `terraform init`:

   ```sh
   aws s3api create-bucket --bucket afe-terraform-state --region af-south-1 \
     --create-bucket-configuration LocationConstraint=af-south-1
   aws s3api put-bucket-versioning --bucket afe-terraform-state --versioning-configuration Status=Enabled
   aws s3api put-public-access-block --bucket afe-terraform-state --public-access-block-configuration \
     BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
   aws dynamodb create-table --table-name afe-terraform-locks --region af-south-1 --billing-mode PAY_PER_REQUEST \
     --attribute-definitions AttributeName=LockID,AttributeType=S --key-schema AttributeName=LockID,KeyType=HASH
   ```

3. **Create what CI needs first:** the image repositories and CI's role. The services can't be created before an
   image exists.

   ```sh
   terraform apply -target=aws_ecr_repository.this -target=aws_iam_openid_connect_provider.gitlab \
     -target=aws_iam_role.ci -target=aws_iam_role_policy.ci_push
   terraform output ci_role_arn ecr_registry
   ```

4. **Set up GitLab** (Settings → CI/CD → Variables, and Settings → Repository → Protected branches):
   - `AWS_ROLE_ARN` = `ci_role_arn`, `ECR_REGISTRY` = `ecr_registry`, `AWS_REGION` = the region, each scoped to
     the environment `staging`.
   - `PUSH_IMAGES` = `true` (all environments). Until it's set, pipelines skip the image build.
   - Protect `staging` and `main`, so only maintainers can push to the branches whose pipelines can push images.

5. **Build the first images:** re-run the latest `staging` pipeline. The `build-images` job pushes both images,
   tagged with the commit, and keeps `images.auto.tfvars` as its artifact. Download it into
   `infra/terraform/staging/`.

6. **Apply everything:** `terraform apply`. The services start and keep restarting until steps 7 and 8 are done;
   that's expected.

7. **Fill the secrets** Terraform created empty (the table in `infra/terraform/staging/README.md`).

8. **Check, then migrate:**

   ```sh
   ../../scripts/run-job.sh python -m app.preflight     # settings, secrets, database, migrations
   ../../scripts/run-job.sh alembic upgrade head
   ../../scripts/run-job.sh python -m app.preflight     # migrations now "ok"
   ```

   On the first run, `preflight` warns that every migration is still to apply: step 2 of this block does that.
   It warns, too, about provider secrets not set yet (WhatsApp, Hubtel, Paystack): the site works without them, with
   those channels off. It fails on settings that don't load, on `AFE_DEBUG`, and on a database it can't reach.

9. **Restart the services** so they start with the secrets:

   ```sh
   for s in api web worker; do aws ecs update-service --cluster "$(terraform output -raw ecs_cluster)" \
     --service "$s" --force-new-deployment >/dev/null; done
   ```

10. **Check it works:** see "After every deploy" below.

---

## Every release

1. **Merge to `staging`.** The pipeline tests the commit, then builds and pushes both images. Download the
   `build-images` job's `images.auto.tfvars` into `infra/terraform/staging/`, replacing the last one. Keep the old one
   (rename it) in case you roll back.

2. **Read the release's migrations** (`backend/migrations/versions/`, new since the last release). Each must only
   add: new tables, new columns that are nullable or have a default, new indexes. Anything that renames or removes
   is split across two releases (see "Writing migrations").

3. **Point the jobs task at the new image, check, and migrate:**

   ```sh
   terraform apply -target=aws_ecs_task_definition.jobs
   ../../scripts/run-job.sh python -m app.preflight
   ../../scripts/run-job.sh alembic upgrade head
   ```

   Stop here if `preflight` fails. Warnings: read them; "N to apply" is what the migration step is for.

4. **Deploy the code:** `terraform apply` (review the plan: it should change task definitions and services, and
   nothing else unless the release changed Terraform). ECS starts new tasks, waits for them to pass health checks,
   then stops the old ones.

5. **After every deploy:**
   - The services are steady: `aws ecs describe-services --cluster "$(terraform output -raw ecs_cluster)"
     --services api web worker --query 'services[].[serviceName,runningCount,desiredCount]'` shows each running
     its desired count. (The load balancer checks the API's `/healthz` itself; from outside, only webhooks reach
     the API.)
   - `https://<web_domain>/` loads, and a search for homes returns results (the web app reaching the API).
   - Sign in as a reviewer; the review queue loads.
   - CloudWatch: no new `unhandled_error` lines in `/afe/staging/api` for 15 minutes, and the worker logs
     `worker_started`.
   - No alarm emails.

## Rolling back

Put the previous `images.auto.tfvars` back and repeat steps 3 and 4 of "Every release", without the migration.
`preflight` will fail on migrations ("newer than this image"): that's expected for a rollback. If every migration in
the release only added tables or columns, the old code runs fine on them, so go ahead. If one didn't, don't roll
back: fix forward with a new release.

Migrations are never rolled back in a running environment: `alembic downgrade` drops tables and columns, and
the data in them.

## Writing migrations

- **Add, don't change.** New tables, nullable columns, columns with a server default, new indexes.
- **Renaming or removing takes two releases:** first add the new column and write to both; once that release is
  out and the data copied, a later release stops using the old one and drops it.
- **Two branches, two migrations on the same parent:** the second to merge adds a merge migration
  (`alembic merge -m "merge ..." heads`), as `20261002_71335203e3dd` does.
- `alembic check` in CI fails when the models changed without a migration.

## Production

Not built yet. The same steps apply to a production stack (its own Terraform directory and state, `main` instead of
`staging`, CI variables scoped to `production`), with two additions: a second person approves the plan before
`terraform apply`, and deploys stay off Fridays and before public holidays.
