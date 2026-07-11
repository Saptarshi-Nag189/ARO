# AWS Deployment Runbook

The AWS layer is **pluggable and entirely optional**. ARO runs fully
featured on a laptop (SQLite checkpoints, local Docker). When you want a
public deployment, this runbook takes you from zero to a live URL in
~20 minutes, and back to zero cost with one command.

## What gets provisioned

```
                        ┌──────────────────────────── AWS (ap-south-1) ─┐
   you / recruiters ──▶ │  ALB :80  ──▶ ECS Fargate: aro-web  (Flask+UI)│
   Claude / Cursor  ──▶ │  ALB :8001 ─▶ ECS Fargate: aro-mcp  (MCP HTTP)│
                        │                    │                          │
                        │                    ├─▶ RDS Postgres 16        │
                        │                    │   (LangGraph checkpoints │
                        │                    │    = durable runs)       │
                        │                    ├─▶ S3 reports bucket      │
                        │                    └─▶ Secrets Manager        │
                        │  CloudWatch: logs, dashboard, CPU alarm       │
                        │  ECR: container registry (10-image lifecycle) │
                        └───────────────────────────────────────────────┘
```

Design choices that keep the bill small:

| Choice | Saving |
|---|---|
| No NAT gateway (public subnets + security groups) | ~$32/mo |
| `db.t4g.micro` RDS (free-tier eligible 12 mo) | ~$12/mo |
| Fargate 0.5 vCPU web + 0.25 vCPU MCP | baseline ~$18/mo |
| `terraform destroy` when idle | everything |

**Estimated running cost: ~$25–40/month** (ALB is the floor at ~$16/mo).
Within the AWS free tier, closer to ~$20/mo. Destroy when not demoing.

## Prerequisites

- An AWS account + IAM user with admin (or scoped) credentials
- `aws` CLI configured (`aws configure`)
- Terraform ≥ 1.5
- Docker

## 1. Provision the infrastructure

```bash
cd infra/terraform
terraform init
terraform plan          # review what will be created
terraform apply         # ~10 min (RDS is the slow part)
```

Outputs to note:

```
web_url        = http://aro-alb-xxxx.ap-south-1.elb.amazonaws.com
mcp_url        = http://aro-alb-xxxx.ap-south-1.elb.amazonaws.com:8001/mcp
ecr_repository = <acct>.dkr.ecr.ap-south-1.amazonaws.com/aro
```

## 2. Set the API-key secrets (one time)

Terraform creates the secrets *empty* so keys never touch state files:

```bash
aws secretsmanager put-secret-value \
  --secret-id aro/openrouter-api-key --secret-string 'sk-or-v1-...'
aws secretsmanager put-secret-value \
  --secret-id aro/langsmith-api-key --secret-string 'lsv2_...'
```

(`aro/checkpoint-uri` is populated automatically from the RDS instance.)

## 3. Push the first image

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-south-1
aws ecr get-login-password --region $REGION |
  docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker build -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/aro:latest .
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/aro:latest

aws ecs update-service --cluster aro-cluster --service aro-web  --force-new-deployment --region $REGION
aws ecs update-service --cluster aro-cluster --service aro-mcp --force-new-deployment --region $REGION
```

## 4. Wire up continuous deployment

Add these to the GitHub repository:

- **Secrets:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- **Variables (optional overrides):** `AWS_REGION`, `ECR_REPOSITORY`,
  `ECS_CLUSTER`, `ECS_SERVICE`

From then on `.github/workflows/deploy.yml` builds → pushes → rolls the
service on every merge to `main`. Until the secrets exist, the workflow
self-skips — nothing breaks.

## 5. Connect an MCP client to the deployed engine

```bash
claude mcp add --transport http aro http://<alb-dns>:8001/mcp
```

Then, in any Claude session: *"use the aro tools to deep-research X"*.

## Durable runs in production

`ARO_CHECKPOINT_URI` is injected from Secrets Manager, so every research
run checkpoints to Postgres after each graph node. If a task is killed
mid-run (deploy, spot interruption, crash), re-invoking with the same
session id resumes from the last completed node:

```bash
python main.py -o "same objective" -m autonomous -s session_<id> --resume
```

## Verify the deployment

```bash
curl http://<alb-dns>/api/health          # {"status":"ok","version":"3.0.0",...}
curl -X POST http://<alb-dns>/api/run \
  -H 'Content-Type: application/json' \
  -d '{"objective":"What is epoch folding?","mode":"fast"}'
```

CloudWatch → Dashboards → `aro-overview` for CPU/memory/requests/5xx.

## Teardown (back to $0)

```bash
cd infra/terraform
terraform destroy
```

Everything including the RDS instance and S3 bucket is destroyed
(`force_destroy`/`skip_final_snapshot` are set — this stack treats cloud
state as disposable; durable knowledge lives in git and LangSmith).

## Deliberate scope cuts (documented, not forgotten)

- **HTTPS**: the ALB listens on plain HTTP. Add an ACM certificate + a
  443 listener when you attach a domain (Route53 + `aws_acm_certificate`
  is ~20 lines — left out to keep the demo stack domain-free).
- **SQS job queue + autoscaling workers**: the natural next step for
  long research jobs (the web tier currently runs them in-process,
  capped by `ARO_MAX_CONCURRENT`). Requires a small queue-consumer
  entrypoint first — infra without code is decoration.
- **Auth**: set `ARO_API_KEY` in the task definition to require
  `X-API-Key` on the API if you leave the stack up unattended.
