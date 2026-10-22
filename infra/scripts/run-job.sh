#!/usr/bin/env sh
# Run one command as a one-off ECS task with the jobs task definition (the API image, settings and secrets), wait for
# it to finish, and exit with its exit code. Its output is in CloudWatch: log group /afe/<environment>/api, stream
# jobs/job/<task id>.
#
# Run from the Terraform directory, with AWS credentials for the account:
#   cd infra/terraform/staging
#   ../../scripts/run-job.sh python -m app.preflight
#   ../../scripts/run-job.sh alembic upgrade head
#
# Arguments are passed as they are; none may contain a double quote.
set -eu

if [ "$#" -eq 0 ]; then
  echo "Usage: run-job.sh <command> [args...]" >&2
  exit 2
fi

cluster=$(terraform output -raw ecs_cluster)
task_definition=$(terraform output -raw jobs_task_definition)
subnets=$(terraform output -raw task_subnets)
security_group=$(terraform output -raw task_security_group)

command_json=$(printf '"%s",' "$@")
command_json="[${command_json%,}]"

task=$(aws ecs run-task \
  --cluster "$cluster" \
  --task-definition "$task_definition" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=DISABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"job\",\"command\":$command_json}]}" \
  --query 'tasks[0].taskArn' --output text)

echo "Started $task: $*"
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"

code=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0].containers[0].exitCode' --output text)
echo "Logs: stream jobs/job/${task##*/}"
if [ "$code" = "None" ]; then
  reason=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0].stoppedReason' --output text)
  echo "The task stopped before the command ran: $reason" >&2
  exit 1
fi
echo "Exit code $code"
exit "$code"
