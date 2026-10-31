# Orbit — Instagram + WhatsApp auto-reply assistant

Orbit is a production-style customer-service assistant for Instagram DMs and WhatsApp. It answers common questions from a verified knowledge base, looks up order status, detects frustration, and hands the conversation to a human when it should not guess.

This repository is a complete stack: FastAPI backend, PyTorch intent/entity NLU, grounded FAQ retrieval (RAG), Celery workers, PostgreSQL/Redis, a React + Tailwind operations dashboard, and a Terraform deployment for **AWS ECS Fargate + RDS + ElastiCache**. Reply rewriting is wired for **Anthropic Claude**, disabled unless `LLM_PROVIDER=anthropic` and a key is present; the default remains grounded templates, so the bot never depends on a vendor to answer safely.

The demo brand is **Aurora Living**. “Orbit” is the assistant/console.

---

## What it does

- Receives Meta webhooks at `/webhook/whatsapp` and `/webhook/instagram`, verifies `X-Hub-Signature-256`, normalizes the payload, deduplicates message IDs, and returns `200` immediately after enqueueing.
- Classifies 9 intents in English and Hinglish: `greeting`, `order_status`, `return_refund`, `product_info`, `pricing`, `complaint`, `human_agent`, `goodbye`, `other`.
- Extracts `ORDER_ID`, `PRODUCT`, and `DATE` entities with a BIO token head, backed by deterministic regex/catalog extraction for order IDs and SKUs.
- Answers FAQs only from `ml/data/faqs.jsonl`; prices are answered only when a product-specific price chunk matches. Otherwise it says it cannot verify the price and hands off.
- Looks up orders through an internal orders API, with a local fixture-based mock for demos.
- Pauses automation and creates a handoff on low confidence, frustration, complaints, explicit human requests, knowledge gaps, missing order IDs, or repeated out-of-scope messages.
- Sends Slack/email notifications and exposes the queue in the dashboard.
- Records every prediction for analytics, confidence monitoring, drift detection, and agent corrections.
- Discloses automation on the first bot turn and prefixes later bot replies if needed.
- Supports WhatsApp’s 24-hour service window with approved templates, and fails closed on Instagram outside its window.
- Provides a deletion endpoint for customer data and a daily retention purge.
- Ships a multi-tenant **customer portal** where a business signs in with phone/email + password to activate automation, verify its notification number, connect Meta channels through OAuth, and receive login/assignment notifications.

---

## Architecture

```text
Meta (WhatsApp Cloud API / Instagram Messaging)
        │  POST /webhook/{channel}  + X-Hub-Signature-256
        ▼
FastAPI webhook ── verify signature ── normalize ── dedupe ── enqueue
        │                                              │
        │ 200 immediately                              ▼
        │                                   Celery + Redis (or inline)
        │                                              │
        │                                              ▼
        │                                   Orchestrator + DialogueManager
        │                                     │        │          │
        │                              NLU (ONNX →    RAG FAQ    Orders
        │                               Torch →       (semantic  service /
        │                               rules)         or TF-IDF) fixtures
        │                                     │
        │                                     ├── answer → channel sender
        │                                     │      (retries, 24h window)
        │                                     └── handoff → pause bot,
        │                                            Slack/email + dashboard
        ▼
PostgreSQL (conversations, messages, predictions, handoffs, feedback)
Redis (task broker, sessions, idempotency)
```

Key behavior:

- **Webhook acknowledgement is fast.** The route only verifies, parses, and queues. With `QUEUE_BACKEND=inline` (local default) processing is synchronous; Compose uses Celery.
- **The bot stays paused after handoff.** Inbound messages are still stored and classified for the agent, but no automatic reply is sent until the conversation is resolved/reopened in the dashboard.
- **Grounded answers only.** The answer path never invents prices, refund outcomes, or order details. Missing evidence becomes a handoff.
- **Fallback-first NLU.** The service loads ONNX, then a Torch checkpoint, then deterministic rules. Rules and lexical RAG work without the heavy ML dependencies.

---

## Repository layout

```text
backend/
  app/
    api/               conversations, handoffs, analytics, feedback, privacy, health, portal
    dialogue/          dialogue manager, handlers, session state
    llm/               provider interface; Claude rewrite with template fallback
    nlu/               rules, transformer/ONNX inference, entities, sentiment
    portal/            accounts, sessions, OAuth state, token encryption, activation
    rag/               FAQ store with semantic + lexical retrieval
    senders/           WhatsApp and Instagram Graph API clients with retries
    services/          orchestrator, handoff, notifier, orders, outbound safety
    webhooks/          Meta signature checks, payload parsers, routes
    worker/            Celery app and scheduled retention task
  tests/               52 backend tests (portal, webhook E2E, routing, handoff, health, signatures)
ml/
  data/                FAQs, order fixtures, generated train/val/test splits
  scripts/             dataset generation, training, evaluation, ONNX export
dashboard/             React 18 + TypeScript + Vite + Tailwind console
deploy/aws/            Terraform: ECS Fargate, RDS, ElastiCache, ALB, ECR, Secrets Manager
shared/                labels, catalog, BIO alignment, model definition
scripts/demo_webhook.py  signed local webhook sender + conversation printer
```

---

## Quickstart — local development

Requirements: Python 3.11, Node.js 20+, npm. Docker is optional.

```bash
cp .env.example .env

make install            # creates .venv, installs backend + dev dependencies
make dataset            # regenerates ml/data/splits (13,500 rows)
(cd dashboard && npm install)

# terminal 1 — API with inline queue and rules/lexical fallbacks
make dev                # http://localhost:8000  (docs at /docs)

# terminal 2 — dashboard
make dashboard          # http://localhost:5173
```

With the default `.env.example`, no Meta credentials are needed:

- `OUTBOUND_MODE=auto` falls back to the mock sender when tokens are absent.
- `ALLOW_UNSIGNED_WEBHOOKS=true` accepts local unsigned webhooks.
- `QUEUE_BACKEND=inline` processes messages in the API process.
- `NLU_BACKEND=auto` uses rules because no trained artifact is present.
- `RAG_BACKEND=auto` uses TF-IDF lexical retrieval without sentence-transformers.

Send a real end-to-end demo message:

```bash
make demo
make demo ARGS='--text "I want a refund for ORD-1042"'
make demo ARGS='--channel instagram --text "Do you deliver to Pune?"'
```

The script signs the payload with `APP_SECRET` from `.env`, posts it, then prints the conversation, intent, confidence, reply, and any handoff. With Compose it waits for the Celery worker.

Run the checks:

```bash
make check              # ruff + 52 backend tests + dashboard typecheck
cd dashboard && npm run build
```

---

## Docker Compose

```bash
cp .env.example .env
make up                 # Postgres, Redis, API, Celery worker + beat, dashboard
```

Open:

- Dashboard: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz> · readiness: <http://localhost:8000/readyz>

Compose forces PostgreSQL, Redis, and the Celery queue. The API image installs only inference-light dependencies by default, so it runs **rules + lexical RAG**. To serve a trained Transformer/ONNX artifact, either build with ML dependencies:

```bash
make up-ml              # INSTALL_ML=true
```

or keep the default image and set `NLU_BACKEND=rules` / `RAG_BACKEND=lexical` explicitly. The model artifacts and data are mounted from `./ml` into `/app/ml`, so training on the host is visible to containers immediately.

Useful commands:

```bash
make ps
make logs
make down
docker compose config  # validate interpolation and schema
```

### Optional public tunnel for Meta testing

```bash
# set NGROK_AUTHTOKEN in .env
make tunnel
```

This starts the `ngrok` profile. Use the HTTPS forwarding URL shown at <http://localhost:4040> as the Meta callback base.

---

## AWS deployment

`deploy/aws/` is a Terraform stack for **ECS Fargate + RDS PostgreSQL + ElastiCache Redis**, fronted by an ALB with ECR, Secrets Manager, and CloudWatch Logs. The ALB routes API/webhook/docs paths to the API target group and everything else to the dashboard, so the browser uses one origin.

```bash
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars   # fill in Meta credentials, cert, sizing
terraform init
terraform apply -target=aws_ecr_repository.repos \
  -target=aws_ecr_lifecycle_policy.repos \
  -var='api_image=placeholder' -var='dashboard_image=placeholder' \
  -var='app_secret=...' -var='verify_token=...'
AWS_REGION=us-east-1 TAG=v1 ../../deploy/aws/build_and_push.sh
terraform apply -var='api_image=<printed>' -var='dashboard_image=<printed>'
```

The API image can be built with `INSTALL_ONNX=true` (onnxruntime + tokenizer, no torch) so it serves the trained artifact without the training stack. Full setup, operations, cost notes, and the security gap list are in [`deploy/aws/README.md`](deploy/aws/README.md). The stack is production-shaped but not turnkey: add WAF, alarms, migrations, and remote Terraform state before real traffic.

---

## Connecting Meta

### 1. App credentials

In the Meta developer dashboard, create an app with WhatsApp and Instagram products, then set in `.env`:

```dotenv
APP_SECRET=...                 # used to verify X-Hub-Signature-256
VERIFY_TOKEN=...               # any long random string you choose
ALLOW_UNSIGNED_WEBHOOKS=false  # required outside local demos
PUBLIC_BASE_URL=https://your-public-host

WHATSAPP_TOKEN=...
PHONE_NUMBER_ID=...
WHATSAPP_BUSINESS_ACCOUNT_ID=...
WHATSAPP_TEMPLATE_NAME=agent_handoff
WHATSAPP_TEMPLATE_LANGUAGE=en_US

IG_PAGE_TOKEN=...
IG_BUSINESS_ACCOUNT_ID=...
```

Restart the API after changing environment values.

### 2. Webhook subscriptions

| Channel | Callback URL | Verify token |
| --- | --- | --- |
| WhatsApp | `https://<host>/webhook/whatsapp` | `VERIFY_TOKEN` |
| Instagram | `https://<host>/webhook/instagram` | `VERIFY_TOKEN` |

Subscribe WhatsApp to `messages` events. For Instagram, subscribe to messaging/message events (and postbacks if you use them). The GET handshake returns `hub.challenge` only when `hub.mode=subscribe` and the token matches.

Meta signs the exact request body. If a reverse proxy rewrites or re-encodes the JSON, signatures will fail; forward the raw body unchanged.

### 3. Service windows and templates

WhatsApp free-form replies are allowed only inside the 24-hour customer service window. Outside it, Orbit sends the approved template named by `WHATSAPP_TEMPLATE_NAME` (language `WHATSAPP_TEMPLATE_LANGUAGE`, body parameter: brand name). Create and get that template approved in WhatsApp Manager before relying on proactive messages; otherwise delivery fails and the failure is recorded.

Instagram has no equivalent template path here. Replies outside `INSTAGRAM_WINDOW_HOURS` fail closed and are visible in the dashboard; resolve the thread manually through an appropriate channel.

### 4. Permissions and review

Use development/test recipients while building. Production access requires Meta app review for the relevant messaging permissions, a verified business, and compliant opt-in. Only reply to users who messaged you first; the service marks inbound users as opted in and refuses outbound sends to customers without opt-in.

---

## NLU, training, and evaluation

The model is a shared DistilBERT encoder with two heads:

- intent classification over 9 labels,
- BIO token classification over `O`, `ORDER_ID`, `PRODUCT`, `DATE`.

Default recipe: AdamW, lr `2e-5`, batch `32`, 3–5 epochs, early stopping on validation macro-F1, stratified 80/10/10 splits, temperature scaling on the validation set, then ONNX export with a numerical parity gate.

```bash
make install-ml         # torch, transformers, sklearn, FAISS, ONNX Runtime (large)
make dataset            # 1,500 utterances/intent, seed 42
make train              # writes ml/artifacts/intent-model/
make export             # ONNX + Torch parity check
make eval               # writes ml/artifacts/evaluation/
make eval-strict        # fails if test macro-F1 < 0.90
```

Artifacts:

```text
ml/artifacts/intent-model/
  pytorch_model.pt
  model.onnx
  model_config.json        # labels, hyperparameters, history, calibration
  calibration.json         # temperature, NLL/ECE before and after
  training_curves.png
ml/artifacts/evaluation/
  evaluation.json          # machine-readable metrics + handoff simulation
  report.md                # per-intent table and confusion matrix summary
  confusion_matrix.png
```

Useful options:

```bash
.venv/bin/python ml/scripts/train_intent.py --help
.venv/bin/python ml/scripts/train_intent.py --device cpu --epochs 3
.venv/bin/python ml/scripts/evaluate.py --backend torch
.venv/bin/python ml/scripts/evaluate.py --fail-under 0.90
```

The API exposes the latest report at `GET /api/model/evaluation` for the dashboard’s **Model & learning** page. If no report exists yet, it returns `available: false` instead of inventing numbers.

### Reference run (this checkout)

The artifacts in `ml/artifacts/` come from a full local run on Apple MPS:

| Stage | Result |
| --- | --- |
| Training | DistilBERT, 10,800 train / 1,350 val, early stop after 3 epochs (best epoch 1) |
| Validation | macro-F1 `1.0000`, entity-F1 `0.9917 → 1.0000` |
| Calibration | temperature `0.5`, ECE `0.0029 → 0.0000` |
| ONNX parity | intent max │Δ│ `8.6e-06`, entity max │Δ│ `1.6e-05`, 100% argmax agreement |
| Test (1,350 rows) | macro-F1 `1.0000`, accuracy `1.0000`, entity-F1 `0.9975` |

These numbers are **not** a production quality signal: the seed data is templated and leaks phrasing across splits. A temperature of `0.5` (below the neutral `1.0`) also signals an over-separated, overconfident model, so expected production confidences will be higher than warranted until you retrain on real data. Use the numbers to confirm the pipeline is wired end to end, not to justify launch.

With artifacts present, `make dev` reports the loaded model at `/readyz` (`"nlu": "intent-<version>"`), and replies use the calibrated transformer with regex/catalog guards for order IDs and SKUs.

### Synthetic data warning

`ml/scripts/generate_dataset.py` produces a reproducible **templated seed set** with English/Hinglish variants. It is useful for wiring the pipeline and CI, but it is not a substitute for consented, anonymized production utterances. Template families can appear across splits, so held-out scores are optimistic. Replace or augment the data with real logs before treating macro-F1 as evidence of production quality. The trainer prints a warning when validation macro-F1 is below `0.90`.

### Feedback loop and drift

Agent corrections in the dashboard create `FeedbackRecord` rows and update the audited `PredictionLog`. The retraining queue is exported as JSONL:

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" \
  http://localhost:8000/api/feedback/export > retraining-queue.jsonl
```

Then mark exported:
`POST /api/feedback/{feedback_id}/mark-exported`.

Exporting does **not** retrain automatically. Merge the JSONL into the training data, rerun training/evaluation, and ship the new artifact deliberately. Drift monitoring compares the last 7 days with the prior 7 days using total variation distance over predicted intents (threshold `0.20`) and average-confidence change (threshold `0.10`), with at least 30 predictions per window. Results appear at `GET /api/analytics/drift` and in the dashboard.

---

## Reply rewriting with Claude

Anthropic Claude is the selected rewrite provider. It is **off by default** and never required for correctness:

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-5     # verify the current model ID before deploying
```

With `LLM_PROVIDER=template` (default) or a missing key, the bot sends the verified answer verbatim. With Anthropic configured, Claude only rephrases answers that already passed grounding — it does not choose facts, look up orders, or decide handoffs.

Guardrails in `backend/app/llm/anthropic.py`:

- The system prompt contains the verified answer and its source IDs, and treats the customer message as untrusted data.
- Every rewrite passes `is_grounded_reply`: any number or URL not present in the verified answer is rejected, as is prompt leakage or an overlong reply.
- Rejected output, timeouts, and non-2xx responses fall back to the template answer. The conversation still gets a correct, grounded reply.
- Handoffs, clarifications, and safety messages never call the model.

Data sent per rewrite: the customer message (truncated to 1,000 characters), detected intent, verified answer, and source IDs. Full transcripts, stored names, and channel IDs are not sent, but the message itself may contain PII the customer typed. Review Anthropic’s data-processing terms and retention settings before production use; the request does not opt into training by default.

Operational considerations: this adds one vendor call of latency and cost per grounded answer, and creates a new data processor in your privacy map. There is no response cache yet; add one keyed by answer + intent if volume makes it worthwhile. Readiness at `/readyz` reports `"llm"` so you can confirm which provider is active.

---

## Handoff rules

The bot pauses and creates a handoff when any of these occurs:

| Trigger | Reason code | Priority |
| --- | --- | --- |
| NLU confidence below `INTENT_CONFIDENCE_THRESHOLD` (default `0.80`) | `low_confidence` | normal |
| Frustration/anger cues | `customer_frustrated` | high |
| Complaint intent | `complaint` | high |
| Explicit request for a human | `customer_requested_human` | high |
| No verified FAQ answer | `knowledge_gap` | normal |
| Price cannot be verified for the product | `unverified_pricing` | normal |
| Return/refund on a real order | `return_refund_request` | normal/high |
| Missing or unknown order ID after retries | `missing_order_id` / `order_not_found` | normal |
| Orders service unavailable | `orders_api_unavailable` | normal |
| Repeated out-of-scope messages | `out_of_scope` | normal |
| Repeated non-text messages | `repeated_non_text` | high |
| Internal pipeline exception | `pipeline_error` | high |

On handoff, the conversation status becomes `needs_human`; the bot does not answer again until an agent resolves or reopens it. Notifications are sent to Slack (`SLACK_WEBHOOK_URL`) and/or email (`SMTP_*`, `HANDOFF_EMAIL_TO`) when configured.

Agent workflow in the dashboard:

1. **Handoffs** lists open/assigned work with channel, priority, reason, last message, and customer.
2. Assign to an agent, open the thread, reply manually, then resolve with an optional note.
3. Resolving closes the handoff and marks the conversation resolved. **Reopen** returns it to bot handling and closes active handoffs.
4. **Inbox** shows all conversations and message history; agent replies bypass the bot and are sent through the same channel sender.

---

## API overview

Protected routes require `X-API-Key` when `ADMIN_API_KEY` is set. Leave it blank for local-only use, and set a long random value anywhere the dashboard is reachable by others.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthz`, `/health`, `/readyz` | Liveness, compatibility alias, dependency/capability readiness |
| `GET` | `/webhook/{channel}` | Meta subscription handshake |
| `POST` | `/webhook/{channel}` | Signed inbound webhook |
| `GET` | `/api/conversations` | List/search conversations (`status`, `channel`, `q`, paging) |
| `GET` | `/api/conversations/{id}` | Full thread + open handoff |
| `POST` | `/api/conversations/{id}/reply` | Agent reply through the channel |
| `POST` | `/api/conversations/{id}/handoff` | Manual escalation |
| `POST` | `/api/conversations/{id}/assign` | Assign agent |
| `POST` | `/api/conversations/{id}/resolve` | Resolve and close handoffs |
| `POST` | `/api/conversations/{id}/reopen` | Return to bot control |
| `GET` | `/api/handoffs` | Open/assigned queue |
| `POST` | `/api/handoffs/{id}/assign`, `/resolve` | Queue actions |
| `GET` | `/api/analytics/overview` | Volume, resolution, handoff, confidence |
| `GET` | `/api/analytics/intents`, `/confidence`, `/volume`, `/drift` | Charts and monitoring |
| `POST` | `/api/messages/{id}/feedback` | Correct the latest intent prediction |
| `GET` | `/api/feedback`, `/api/feedback/export` | Retraining queue and JSONL export |
| `GET` | `/api/model/evaluation` | Latest evaluation artifact |
| `GET` | `/api/portal/config` | Portal capability/config summary (public) |
| `POST` | `/api/portal/auth/register`, `/login`, `/logout` | Workspace signup, sign-in, session revoke |
| `GET` | `/api/portal/me`, `/activity` | Workspace, channels, and audit timeline |
| `POST` | `/api/portal/phone`, `/phone/verification/request`, `/phone/verification/confirm` | Attach a number, send/confirm an OTP |
| `GET` | `/api/portal/channels/oauth-url` | Signed Meta OAuth URL per channel |
| `POST` | `/api/portal/channels/{channel}/connect`, `/disconnect` | Connect via OAuth (or local demo), disconnect |
| `POST` | `/api/privacy/delete` | Hard-delete a customer (`confirm: true`) |
| `GET` | `/internal/orders/{id}` | Local mock orders service (disable in production) |

Interactive docs: <http://localhost:8000/docs>.

### Webhook example

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H 'Content-Type: application/json' \
  -H "X-Hub-Signature-256: sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$APP_SECRET" | awk '{print $2}')" \
  --data "$BODY"
```

`make demo` does this for you with a correct payload and signature.

---

## Dashboard

React 18 + TypeScript + Vite + Tailwind, designed as an operations console rather than a generic admin template.

- **Overview** — volume, bot resolution/handoff rates, average confidence, intent mix, confidence distribution, drift banner.
- **Inbox** — searchable conversations, channel/status filters, full transcript with intent/confidence/entities, agent reply, assign/resolve/reopen, manual handoff.
- **Handoffs** — open/assigned queue, priority, reason, assign and resolve.
- **Model & learning** — latest evaluation report, per-intent metrics, calibration, drift, pending agent corrections, intent correction editor, JSONL export.
- **Settings** — readiness, webhook URLs from `PUBLIC_BASE_URL`, API key storage, privacy deletion, environment facts.
- **Customer portal** — `/portal/login`, `/portal/register`, and `/portal` for workspace owners: automation status, channel connections, phone verification, and an audit timeline. The ops console sidebar links to it.

In development, Vite proxies `/api`, `/healthz`, and `/readyz` to `localhost:8000`. In Compose, nginx proxies the same paths and `/webhook/` to the API service. The dashboard stores the optional admin key in `localStorage` under `orbit.apiKey`; it is not a multi-user auth system. The portal uses its own signed session (httpOnly cookie plus bearer token) and never grants admin access.

---

## Customer portal

The portal is a multi-tenant SaaS layer on top of the same assistant. Each workspace (`Tenant`) has its own portal users, channel connections, conversations, and audit events.

**Signup and sign-in**

- Register with a business name, owner name, and either an email or an international phone number. Either identifier can be used to sign in later; passwords are PBKDF2-SHA256 with 600k iterations.
- Signing in sets `automation_enabled=true` for the workspace and records `automation_activated`. Before that, inbound messages are stored and classified but no automatic reply is sent.
- Sessions are random 256-bit tokens stored as SHA-256 hashes, valid for `PORTAL_SESSION_HOURS`, and revocable on logout. Login attempts are rate-limited per identifier.
- An email-only account can attach a phone later with `POST /api/portal/phone` (current password required). Changing the number always resets verification.

**Login confirmation and consent**

- The confirmation is sent to the workspace owner’s number, not to end customers, using `PORTAL_WELCOME_TEMPLATE_NAME` (approved in Meta).
- It is sent only when all of these are true: the owner opted in at signup, the phone is verified, a WhatsApp connection exists, and a template is configured. Otherwise the attempt is recorded as `blocked` with a reason such as `phone_not_verified` or `welcome_opt_in_required`.
- Assignment notifications use `PORTAL_ASSIGNMENT_TEMPLATE_NAME` and the same consent/verification gate. They are matched to a portal user in the conversation’s workspace by full name, email, or phone.

**Connecting channels**

- Clicking Connect starts Meta OAuth with a signed, expiring `state` bound to the user, workspace, and channel. Orbit exchanges the code for a scoped token and verifies the account against Graph.
- Tokens are encrypted at rest with Fernet (`PORTAL_ENCRYPTION_KEY`, derived from a hash of the configured secret). They are never returned by the API. Orbit **never collects Instagram or WhatsApp passwords**—only Meta OAuth grants.
- `PORTAL_ALLOW_MOCK_CHANNEL_CONNECT=true` enables a local demo connection outside production. Demo connections use the mock sender and never contact Meta; set it to `false` for staging/production.
- Tenant traffic fails closed: if a workspace has no connected channel, replies are marked failed instead of falling back to deployment-wide credentials.

**Phone verification**

- `PORTAL_OTP_DELIVERY=dev` returns the one-time code in the API response and is only intended for local development (the dashboard shows it in the verification dialog).
- `webhook` POSTs `{phone, code, purpose}` to `PORTAL_OTP_WEBHOOK_URL`; wire that to your SMS/WhatsApp gateway. `disabled` turns verification off.
- Codes expire after `PORTAL_OTP_TTL_SECONDS` and lock after `PORTAL_OTP_MAX_ATTEMPTS`. Only a hash is stored.

To enable real connections, create a Meta app, add the WhatsApp Business and Instagram products, set `PORTAL_META_APP_ID`, `PORTAL_META_APP_SECRET`, and the exact `PORTAL_OAUTH_REDIRECT_URI`, then approve both templates in the WhatsApp Manager. `PORTAL_META_CONFIG_ID` switches the flow to Meta’s Embedded Signup when configured.

---

## Compliance and privacy

Implemented controls:

- **Opt-in only:** outbound sends are refused when a customer is not opted in; inbound messagers are recorded as opted in.
- **Minimum PII:** the schema stores channel IDs, display name, message text, intent/confidence, and operational metadata. No payment data or credentials are stored in conversation rows.
- **Secrets:** Meta/SMTP tokens come from environment variables and are never written to the database or returned by the API, with one deliberate exception: portal channel tokens are stored encrypted (Fernet) so each workspace can send with its own credentials. Use your platform's secret manager in production and set a dedicated `PORTAL_ENCRYPTION_KEY`.
- **Automation disclosure:** the first bot turn includes “automated”; a safety prefix is applied if a generated reply does not disclose in the first 12 words.
- **Deletion:** `POST /api/privacy/delete` hard-deletes a customer, conversations, messages, predictions, and cached session state after `confirm: true`.
- **Retention:** Celery Beat runs a daily purge for conversations older than `DATA_RETENTION_DAYS` (default 180) and removes orphaned customers/predictions.
- **Auditability:** request IDs, prediction logs, order lookup events, handoff records, feedback records, and delivery metadata.

Operational notes:

- The deletion endpoint is authenticated by the shared admin key; protect it and log access in production.
- Database backups and provider-side retention are outside this repository’s control.
- Review Meta’s platform terms, messaging policies, and local privacy law before production use.

---

## Configuration

Copy `.env.example` to `.env`. The most important switches:

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Use `production` in deployed environments |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used for webhook URLs shown in the dashboard |
| `ADMIN_API_KEY` | empty | Enables `X-API-Key` protection when set |
| `DATABASE_URL` | SQLite file | Compose overrides with PostgreSQL |
| `REDIS_URL` | localhost Redis | Cache/session fallback is in-memory if unavailable |
| `QUEUE_BACKEND` | `inline` | Compose forces `celery` |
| `ALLOW_UNSIGNED_WEBHOOKS` | `true` in example | Must be `false` in production |
| `APP_SECRET`, `VERIFY_TOKEN` | placeholders | Required for real Meta webhooks |
| `OUTBOUND_MODE` | `auto` | `mock` never calls Meta |
| `NLU_BACKEND` | `auto` | `auto` → ONNX → Torch → rules |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.80` | Below this, hand off |
| `RAG_BACKEND` | `auto` | Semantic if deps available, else lexical |
| `LLM_PROVIDER` | `template` | `none`, `template`, or `anthropic` |
| `LLM_MODEL` | `claude-sonnet-4-5` | Model ID for the Anthropic provider |
| `LLM_API_KEY` | empty | Anthropic key; missing key forces template fallback |
| `DATA_RETENTION_DAYS` | `180` | Daily purge cutoff |
| `INSTALL_ML` | `false` | Compose build arg for the full training/inference stack |
| `INSTALL_ONNX` | `false` | Compose/AWS build arg for ONNX-only inference (no torch) |
| `PORTAL_ENABLED` | `true` | Set `false` to hide the customer portal |
| `PORTAL_PUBLIC_URL` | `http://localhost:5173` | Portal origin; used for the OAuth redirect fallback |
| `PORTAL_SESSION_HOURS` | `12` | Portal session lifetime |
| `PORTAL_ENCRYPTION_KEY` | empty | Fernet key material for channel tokens; set a dedicated random value |
| `PORTAL_META_APP_ID`, `PORTAL_META_APP_SECRET` | empty | Meta app for OAuth / Embedded Signup |
| `PORTAL_OAUTH_REDIRECT_URI` | `http://localhost:5173/portal` | Must match the Meta app’s allowed redirect |
| `PORTAL_WELCOME_TEMPLATE_NAME`, `PORTAL_ASSIGNMENT_TEMPLATE_NAME` | see example | Approved Meta templates for proactive messages |
| `PORTAL_OTP_DELIVERY` | `dev` | `dev`, `webhook`, or `disabled`; use `webhook` in production |
| `PORTAL_OTP_WEBHOOK_URL` | empty | SMS/WhatsApp gateway that delivers the one-time code |
| `PORTAL_ALLOW_MOCK_CHANNEL_CONNECT` | `true` in example | Demo connections outside production only |

No Anthropic key or AWS account is required for local use; without them the bot runs grounded templates on Docker Compose.

---

## Testing and quality

```bash
make lint               # ruff
make test               # PYTHONPATH=backend:. pytest backend/tests -q
make check              # lint + tests + dashboard typecheck
cd dashboard && npm run build
docker compose config
make tf-check           # terraform init -backend=false + validate
```

The suite covers signature verification, webhook parsing, end-to-end WhatsApp/Instagram flows, deduplication, routing, RAG grounding, handoff rules, agent correction, evaluation endpoint, health/readiness, privacy deletion, portal registration/login, OTP verification, token encryption, tenant gating, assignment notifications, and Claude prompt/grounding/fallback behavior. The ML scripts were additionally exercised end to end on this checkout (dataset → DistilBERT training → ONNX export with parity → evaluation); see **Reference run** above. `make check` itself stays light and does not require torch; the Terraform stack is validated with `terraform validate`.

---

## Limitations and production checklist

- **Anthropic rewriting is optional and unverified against your data.** The grounding gate blocks invented numbers/links, but it cannot prove tone or policy compliance. Review prompts and sampled outputs before enabling it; without a key the bot falls back to templates.
- **AWS is a baseline, not a hardened platform.** The Terraform stack lacks WAF, alarms, migrations as a job, remote state, CMK policies, and restore drills; see `deploy/aws/README.md`.
- **Synthetic training data** is seed data. Collect consented, anonymized real utterances, de-duplicate template families across splits, and re-evaluate before trusting metrics.
- **No database migrations.** `create_all` plus an additive startup column check is used for the starter. Add Alembic before evolving a live schema.
- **Retraining is manual.** Feedback export is implemented; automatic retraining/deployment is not.
- **Single shared dashboard key**, not SSO/RBAC. The customer portal adds tenant-scoped sessions, but the ops console still uses one shared `ADMIN_API_KEY` with no fine-grained authorization.
- **In-memory Redis fallback** is only for dev; use Redis in production so sessions and dedupe keys survive restarts and are shared by workers.
- **Portal OTP delivery is a stub outside development.** Production requires `PORTAL_OTP_DELIVERY=webhook` and a real SMS/WhatsApp gateway; the `dev` code is never returned in production.
- **Portal rate limiting is in-process.** Run one API replica or move the limiter to Redis before horizontal scaling.
- **Media is not inspected.** Images/documents are acknowledged with a text request or handed off after repeats.
- **Instagram has no template fallback**; outside the messaging window the send fails closed.
- **Local Compose and the AWS stack are not turnkey hardened deployments.** Compose has no TLS by default; AWS has no WAF, alarms, or migration job. Add those plus backups, monitoring, and rate limiting before real traffic.
- **Template approval and Meta app review are external prerequisites.**
- Set `ALLOW_UNSIGNED_WEBHOOKS=false`, `OUTBOUND_MODE=auto` with real tokens, a strong `ADMIN_API_KEY`, and `ENVIRONMENT=production` before exposing the service.
- Disable the mock orders route (`ENABLE_MOCK_ORDERS_API=false`) and point `ORDERS_API_URL` at the real internal service.
- Verify the privacy deletion path against your actual data map (including backups) before launch.

---

## License / provenance

This is a starter implementation built for the Aurora Living demo. Product names, FAQs, and orders in `ml/data/` are fictional fixtures. Replace them with verified business facts and real integrations before using it with customers.
