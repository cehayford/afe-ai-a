# Free development server

Afe on one free server (Oracle Cloud Always Free ARM, or any Linux server with Docker): PostgreSQL, the API,
the worker (including the daily jobs), the website, Caddy for HTTPS (or Cloudflare Tunnel), and nightly database
backups to Cloudflare R2. Files are stored in R2 and email goes through Resend or any SMTP service.

| File | What it is |
|---|---|
| `compose.yml` | Every service. `docker compose up -d --build` |
| `.env.example` | Settings to copy to `.env` (never commit `.env`) |
| `Caddyfile` | HTTPS, and which paths reach the API directly (partner webhooks) |
| `backup.sh` | Nightly backups; also `now`, `list` and `restore FILE` |

The step-by-step setup guide, the free services used and how to move to AWS at beta are in
[docs/Deployment_Level_AWS.md](../../docs/Deployment_Level_AWS.md), "Development level: the free setup".

Only demo and test data on this server: real personal data waits for beta on AWS.
