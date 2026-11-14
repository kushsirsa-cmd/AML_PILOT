# Deployment guide

> **Status note.** The application, the single-container runtime layout (`docker/start.sh` + Next standalone + SQLite, booted from an empty DB) and the Postgres path are tested.
> The `Dockerfile`s and cloud configs below were written to standard platform conventions but **have not been built on a real Docker daemon or deployed to each cloud** by the author — the first CI run (`.github/workflows/ci.yml` builds the image and smoke-tests it) is your confirmation. Cloud console labels change; follow the platform's current docs where they differ.

## Which option?

| Goal | Use | Time | Cost |
|---|---|---|---|
| Share a URL **right now** from your laptop | Cloudflare quick tunnel / ngrok (§2) | ~2 min | free |
| A stable URL for teammates, no laptop needed | **Render free web service** (§3) | ~10 min | free |
| Investor/customer pilot, always-on | Railway, Azure Container Apps, AWS App Runner (§4–6) | 15–30 min | small monthly |

All hosted options run the **single-container image** (root `Dockerfile`): UI + API + SQLite on one port, demo data seeded at boot.
Free tiers sleep when idle and have ephemeral disks, so after a restart the dataset is simply **re-seeded** (≈20 s) — that's fine for demos; Admin → *Reset demo data* does the same on demand.

**Before sharing any public URL:** set `DEMO_PASSWORD` (default `demo1234` is printed on the login page) and `AUTH_SECRET`. All data is synthetic, but the app is open to anyone with the link and password.

## 1. Localhost
```bash
git clone <your-repo> && cd aml-copilot
./setup.sh            # Docker: Postgres + API + UI  → http://localhost:3000
./setup.sh --local    # no Docker (Python 3.12 + Node 20, SQLite)
make single           # single container             → http://localhost:8080
```
Stop: `docker compose down` (add `-v` to wipe the database). Optional: copy `.env.example` → `.env` and add `ANTHROPIC_API_KEY` for Claude-written narratives.

## 2. Fastest shareable URL (no cloud account)
Run locally, then expose the port:
```bash
./setup.sh                                   # app on :3000
# Option A — Cloudflare quick tunnel (no signup)
cloudflared tunnel --url http://localhost:3000     # prints https://<random>.trycloudflare.com
# Option B — ngrok (free account)
ngrok http 3000
```
Teammates open the printed https URL. It lives only while your laptop and the tunnel run — ideal for a same-day review, not for leaving up.

## 3. Render (recommended free, stable URL)
1. Push this repo to GitHub (see §7).
2. Render dashboard → **New + → Blueprint** → select the repo. `render.yaml` provisions a free Docker web service (`healthCheckPath: /api/health`, random `AUTH_SECRET`).
3. Set `DEMO_PASSWORD` (and optionally `ANTHROPIC_API_KEY`) in the service's Environment tab.
4. First build takes several minutes; you get `https://aml-copilot-xxxx.onrender.com`.

Free-plan behaviour: the service **spins down after ~15 min idle** and takes ~1 min to wake (plus a re-seed). Open the URL a minute before a meeting. A paid instance removes the sleep.

## 4. Railway
1. **New Project → Deploy from GitHub repo.** `railway.json` selects the root `Dockerfile` and `/api/health`.
2. *Settings → Networking → Generate Domain* (target port = the `PORT` Railway injects; the image honours it).
3. Variables: `DEMO_PASSWORD`, `AUTH_SECRET`, optional `ANTHROPIC_API_KEY`.
4. For persistence across deploys, add a Volume mounted at `/data` (the image stores SQLite at `/data/aml.db`). Railway's free allowance is trial credit, not unlimited.

## 5. Azure
**Container Apps (simplest):**
```bash
az group create -n aml-demo -l westeurope
az containerapp up -n aml-copilot -g aml-demo --source . --ingress external --target-port 8080 \
  --env-vars DEMO_PASSWORD=<pw> AUTH_SECRET=<random> SEED_SIZE=full
```
`az containerapp up --source .` builds the root `Dockerfile` in the cloud and prints the app URL.
For a durable DB use **Azure Database for PostgreSQL – Flexible Server** and set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/aml` (tables are created on first start). Alternatively App Service for Containers with an image from Azure Container Registry.

## 6. AWS
**App Runner (simplest):** push the image to ECR, then create a service from that image, port **8080**, health check path `/api/health`, env vars as above.
```bash
aws ecr create-repository --repository-name aml-copilot
docker build -t aml-copilot . && docker tag aml-copilot <acct>.dkr.ecr.<region>.amazonaws.com/aml-copilot:latest
aws ecr get-login-password | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
docker push <acct>.dkr.ecr.<region>.amazonaws.com/aml-copilot:latest
```
Other routes: **ECS Fargate** behind an ALB (use RDS PostgreSQL for `DATABASE_URL`), or **Lightsail Container Service** for a flat-priced small deployment.

## 7. Publish to GitHub
```bash
cd aml-copilot            # the project folder (already `git init`-ed in the zip)
git remote add origin git@github.com:<you>/aml-copilot.git
git push -u origin main
```
Or with the GitHub CLI: `gh repo create aml-copilot --private --source . --push`. CI then runs tests, the frontend build and a Docker smoke test.

## Environment variables
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | SQLite file (single container) / Postgres (compose) | Any SQLAlchemy URL; `postgresql+psycopg://…` for Postgres |
| `DEMO_PASSWORD` | `demo1234` | Shared by all five personas — change for public URLs |
| `AUTH_SECRET` | `change-me-in-production` | Signs login tokens |
| `DEMO_OPEN_ACCESS` | `true` | `false` = every API call needs a login token |
| `SEED_ON_STARTUP` / `SEED_SIZE` | `true` / `full` | `small` = 11 customers + 5 corporates |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `LLM_ENABLED` | empty / `claude-sonnet-5-5` / `true` | Key enables Claude-written narratives |
| `PORT` | `8080` (image) | Public port; honoured by Render/Railway/Cloud Run |

## Troubleshooting
* *Blank page / 502 right after deploy* — first boot seeds the DB; wait ~20–60 s.
* *Login says invalid* — you changed `DEMO_PASSWORD`; the login page prints the password in use.
* *Data vanished after a redeploy* — ephemeral disk by design; mount `/data` or use Postgres.
* *Compose: UI loads but API calls fail* — rebuild the frontend (`docker compose build frontend`); the API address is baked in at build time (`BACKEND_URL`).
