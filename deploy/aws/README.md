# Deploying Orbit on AWS

Terraform stack for the selected target: **ECS Fargate + RDS PostgreSQL + ElastiCache Redis**, with an Application Load Balancer, ECR, Secrets Manager, and CloudWatch Logs. The dashboard is served by the same ALB, which routes `/api/*`, `/webhook/*`, `/health*`, `/docs*` to the API and everything else to the dashboard container.

```text
Internet
   │  HTTPS (ACM cert)
   ▼
ALB (public subnets)
   ├── /api/*, /webhook/*, /health*, /docs*  → API target group :8000
   └── /*                                     → dashboard target group :80
                                                    │
                ┌───────────────────────────────────┘
                ▼
        ECS Fargate (private subnets)
          api × N, worker, beat, dashboard
             │                 │
             ▼                 ▼
       RDS PostgreSQL     ElastiCache Redis (TLS + AUTH)
```

This is production-shaped, not a fully hardened platform. Read the gaps at the end before handling real customer traffic.

---

## Prerequisites

- Terraform >= 1.7 (validated with 1.9.8 and AWS provider 5.100)
- AWS CLI v2 with credentials that can create VPC/ECS/RDS/ElastiCache/IAM/ALB/ECR resources
- Docker with buildx (images must be `linux/amd64`)
- An ACM certificate in the same region for your domain, if you want HTTPS. Meta webhooks require HTTPS in production.
- Meta app secret, verify token, page/WhatsApp tokens, and (optionally) an Anthropic API key

---

## 1. Create the ECR repositories

```bash
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars   # fill in secrets and settings
terraform init
terraform apply \
  -target=aws_ecr_repository.repos \
  -target=aws_ecr_lifecycle_policy.repos \
  -var='api_image=placeholder' \
  -var='dashboard_image=placeholder' \
  -var='app_secret=placeholder-secret' \
  -var='verify_token=placeholder-token'
```

`api_image` and `dashboard_image` are required variables, so placeholder values keep the targeted apply moving. Nothing else is created by this step except the two repositories and their lifecycle policies.

## 2. Build and push images

From the repository root:

```bash
AWS_REGION=us-east-1 TAG=v1 ./deploy/aws/build_and_push.sh
```

The script logs in to ECR, builds both images for `linux/amd64`, and prints the Terraform command with the resulting image URIs. It builds the API image with `INSTALL_ONNX=true` by default: onnxruntime + tokenizer only, no torch. Use `INSTALL_ONNX=false` for a small rules-only image.

Why ONNX-only matters: the trained artifact is baked into the image from `ml/artifacts/` (the `.dockerignore` no longer excludes it). If you have not trained/exported a model, the API starts in rules mode and serves fine; build with `INSTALL_ONNX=false` in that case.

## 3. Apply the full stack

```bash
cd deploy/aws
terraform apply \
  -var='api_image=<from step 2>' \
  -var='dashboard_image=<from step 2>'
```

Outputs include the ALB DNS name, public base URL, webhook URLs, ECR URLs, and secret ARN. If `public_base_url` is empty, the stack uses `http(s)://<alb-dns>`. Set it to your HTTPS domain once DNS points at the ALB.

The API runs `create_all` on startup, so the schema is created by the first task. There are no migrations (see gaps).

## 4. Retrieve the admin key

If `admin_api_key` was left empty, Terraform generated one into Secrets Manager:

```bash
aws secretsmanager get-secret-value \
  --secret-id orbit/production/app \
  --query SecretString --output text | jq -r .ADMIN_API_KEY
```

Store it in your password manager. The dashboard keeps it in browser localStorage only; it is not a multi-user identity system.

## 5. Point Meta at the ALB

| Channel | Callback URL | Verify token |
| --- | --- | --- |
| WhatsApp | `https://<domain>/webhook/whatsapp` | `verify_token` |
| Instagram | `https://<domain>/webhook/instagram` | `verify_token` |

Subscribe WhatsApp to `messages`; subscribe Instagram to messaging events. If signatures fail, check that the ALB forwards the raw body unchanged (it does by default) and that `APP_SECRET` matches the Meta app.

---

## Operations

```bash
# Logs
aws logs tail /ecs/orbit-production/api --follow
aws logs tail /ecs/orbit-production/worker --follow

# Force a new deployment after pushing a tag
aws ecs update-service --cluster orbit-production --service api \
  --task-definition orbit-production-api --force-new-deployment
```

`terraform apply` with new `api_image`/`dashboard_image` values updates the task definitions and rolls the services. ECS deployment circuit breaker rolls back a failed release.

Scaling:

- API: target-tracking on 60% average CPU, 2–6 tasks by default.
- Worker: target-tracking on 70% CPU, 1–4 tasks. For real workloads, scale on Celery queue depth via a custom CloudWatch metric instead.
- Beat: exactly one task. Do not scale it.

Secrets rotation: update the secret version in Secrets Manager, then force a new deployment so tasks pick it up. Rotating the RDS password requires updating both the DB and `DATABASE_URL`; this stack does not automate that.

Costs (order of magnitude, us-east-1, list price): ALB ~$18/month, 2 API tasks + worker + beat + dashboard ~$90–140/month, RDS `db.t4g.medium` ~$50–100/month plus storage, one NAT gateway ~$32/month, ElastiCache `cache.t4g.micro` ~$13/month. Use `single_nat_gateway=false`, `db_multi_az=true`, and `redis_num_cache_clusters=2` for a resilient production setup; both add cost.

---

## Security notes and gaps

Already in the stack:

- ECS and data stores in private subnets; only the ALB is public.
- Security groups restrict Postgres/Redis to ECS tasks.
- RDS storage encrypted, TLS enforced (`rds.force_ssl=1`, `sslmode=require`).
- Redis in-transit TLS with AUTH, at-rest encryption.
- Secrets in Secrets Manager, injected by ECS; no secrets in task definitions or user data.
- ECR scan-on-push and a 15-image retention policy.
- CloudWatch log retention (30 days by default).
- HTTP→HTTPS redirect when a certificate is configured.

Not included, and required before real customer traffic:

- **WAF / rate limiting.** The ALB is directly exposed. Add AWS WAF managed rules and rate-based rules.
- **Custom domain automation.** Create the ACM certificate and Route 53 alias separately (or add them here).
- **Database migrations.** `create_all` only. Add Alembic before evolving a live schema, and run it as a one-off ECS task.
- **Automated backups verification / PITR drills.** RDS backups are enabled, but restores are untested here.
- **CMK encryption and key policy.** This stack uses AWS-managed keys. Use customer-managed KMS keys for stricter policy control.
- **Blue/green or canary deploys.** ECS rolling deployment with circuit breaker only.
- **Alerting.** No CloudWatch alarms for 5xx, queue depth, handoff backlog, or task restarts.
- **Queue-depth autoscaling and worker right-sizing.**
- **Beat HA.** One beat task is correct for Celery, but a task restart loses the local schedule file (it is recreated; schedules are code-defined).
- **Log/trace aggregation beyond CloudWatch.**
- **Terraform state.** Configure the S3 + DynamoDB backend in `versions.tf`; local state is not team-safe.
- **Meta app review, template approval, and opt-in compliance** are external prerequisites.

Teardown is intentionally awkward: `db_deletion_protection = true` and `enable_deletion_protection` on the ALB both block `terraform destroy`. Set the DB protection variables to `false`, apply, then destroy. Final snapshot behavior is controlled by `db_skip_final_snapshot`.
