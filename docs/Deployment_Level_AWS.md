# Afe deployment level: free now, AWS at beta and in production

**Date:** 24 September 2026 · **Prices:** AWS Price List API, fetched 24 Sep 2026 · **Exchange rate:** $1 = GHS 11.544 (Bank of Ghana, 18 Sep 2026)

This document covers four things:
- the free setup Afe runs on while we build it, with a step-by-step guide;
- the AWS Free Tier fallback;
- what beta (staging) costs;
- a line-by-line cost sheet for production, with the services outside AWS that production also needs.

All prices are list prices in US dollars, before tax, and assume a 730-hour month. Check them in the [AWS Pricing Calculator](https://calculator.aws/) before committing to a budget. Figures marked "estimate" are ranges from vendors' published rates, to confirm with each vendor.

## Where we are

| Stage | Where it runs | Database | Providers | Status |
|---|---|---|---|---|
| **Local** | Each developer's laptop | SQLite (or PostgreSQL in `docker-compose.yml`) | Fakes: test ID checks, SMS, payments | In use now |
| **Development (free)** | One free server (Oracle Cloud) with Cloudflare, Resend and GitHub, from `deploy/free-server` | PostgreSQL | Fakes, with real file storage (R2) and email | **Recommended next** |
| **Beta (staging)** | `infra/terraform/staging`: ECS Fargate, RDS, load balancer | PostgreSQL (required) | Real test accounts: Hubtel, WhatsApp, Paystack test mode | Written, not yet applied |
| **Production** | The same Terraform, sized up, in the chosen region | PostgreSQL, Multi-AZ (required) | Real providers (decisions B5 and B7) | From the soft launch, 11 Dec 2026 |

The build plan's rule still holds: SQLite only on laptops, PostgreSQL from beta onwards. The app refuses to start without PostgreSQL once `AFE_DEBUG` is off.

## Development level: the free setup (recommended now)

While we build, Afe runs on free services, not on AWS. It is one server running the same Docker images that will run on AWS, plus free services around it for files, email, domain, monitoring and tests. **Cost: $0 a month.** The only spend is a domain name, about $10–15 a year.

Nothing here is tied to one vendor. The app reads everything from settings, so at beta the same images move to AWS and only the settings change (see "Moving to AWS at beta" below).

### What we use

| Need | Service | Free limit (check when you sign up) | How Afe uses it |
|---|---|---|---|
| Server | **Oracle Cloud "Always Free"** ARM server | Up to 4 CPUs and 24 GB of memory, 200 GB of disk, free for as long as you use it | Runs everything in `deploy/free-server/compose.yml`: PostgreSQL, the API, the worker, the website, Caddy and backups |
| Database | **PostgreSQL 16** in a container on the server | Limited only by the disk | The same major version as RDS at beta |
| Files | **Cloudflare R2** | 10 GB, 1 million writes and 10 million reads a month, no download charges | Listing photos (public bucket), documents (private bucket), database backups. R2 works with S3 tools, so the app's S3 storage works unchanged. |
| Domain, HTTPS, protection | **Cloudflare** free plan, and optionally **Cloudflare Tunnel** | DNS, HTTPS certificates and basic attack protection | Caddy gets a free certificate. Or the Tunnel reaches the server with no open ports. |
| Email | **Resend** (or **Brevo** by SMTP) | Resend: 3,000 a month, 100 a day. Brevo: 300 a day | New providers `ResendEmail` and `SmtpEmail` |
| Tests on every push | **GitHub Actions** | 2,000 minutes a month for private repositories | `.github/workflows/ci.yml`: backend on PostgreSQL, frontend checks, Docker builds |
| Uptime alerts | **UptimeRobot** | 50 monitors, checked every 5 minutes | Email when the site stops answering |
| SMS, ID checks | Test providers built into Afe | Free | Neither has a free tier. Sign-in codes show in the API log: `docker compose logs api` |
| Payments | **Paystack test mode** | Free | Optional: real checkout pages with test cards and test mobile money |
| WhatsApp | **WhatsApp Cloud API test number** | Free for up to 5 test recipients | Optional: FIND, ALERT and reminders on real phones |
| Maps | OpenStreetMap tiles | Light use | Already in the app. Switch to a paid tile provider before launch. |

**Only demo and test data on this server.** It has no data processing agreements with its providers and no support. Real Ghana Card details, real tenants and real money wait for beta on AWS, as the Data Protection Act requires.

### Setup guide

Allow about half a day. Commands run on the server unless it says otherwise.

**1. Accounts**
- **Oracle Cloud:**
  - Sign up at cloud.oracle.com. A card is needed to check who you are, and Always Free resources are never charged.
  - Choose the **home region** carefully, because it can't be changed. **South Africa (Johannesburg)** is closest to Accra. If it has no ARM capacity, UK South (London) or Germany Central (Frankfurt) are good second choices.
  - Once the server runs, upgrade the account to **Pay As You Go**. It stays free within the Always Free limits, and Oracle doesn't reclaim idle servers on paid accounts. Set a budget alert of $1 in Oracle so nothing chargeable goes unnoticed.
- **Cloudflare:** add the domain (buy one at cost through Cloudflare Registrar, or move an existing one). Enabling R2 asks for a card; the free allowance isn't charged.
- **Resend** (or Brevo), and **UptimeRobot**.

**2. Create the server (Oracle Cloud console)**
- Compute > Instances > Create:
  - image **Ubuntu 24.04** (aarch64);
  - shape **VM.Standard.A1.Flex** with **4 OCPUs and 24 GB**;
  - boot volume 100 GB;
  - your SSH public key.
- **If you'll use Caddy with open ports:** in the instance's subnet security list, allow TCP 80 and 443 from anywhere, and TCP 22 only from your own IP address. Oracle's Ubuntu images also block these ports in the server's own firewall, so open them there too:

```bash
sudo iptables -I INPUT 6 -p tcp -m state --state NEW -m multiport --dports 80,443 -j ACCEPT
sudo netfilter-persistent save
```

- **If you'll use Cloudflare Tunnel:** open nothing except SSH from your IP.

**3. Install Docker and Git**

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker
sudo apt-get install -y git
```

**4. Cloudflare R2**
- Create three buckets: `afe-dev-media-public`, `afe-dev-private` and `afe-dev-backups`.
- On `afe-dev-media-public` only, turn on public access: its r2.dev address, or better a custom domain such as `media.dev.afe.example`. That address is `AFE_MEDIA_URL`.
- Create an API token: R2 > Manage API tokens > Object Read & Write, limited to the three buckets. Note the access key, the secret, and the endpoint `https://<account-id>.r2.cloudflarestorage.com`.

**5. Email**
- In Resend, add the domain (e.g. `dev.afe.example`) and add the DNS records it shows (SPF and DKIM) in Cloudflare.
- Create an API key.
- Until the domain is verified, Resend only delivers to your own address.

**6. Address: choose one**
Two addresses: the website (`dev.afe.example`) and the API for the mobile app (`api.dev.afe.example`).
- **Caddy (simplest):**
  - In Cloudflare DNS, add A records `dev` and `api.dev` pointing at the server's public IP, set to *DNS only* (grey cloud).
  - Set `SITE_ADDRESS=dev.afe.example` and `API_ADDRESS=api.dev.afe.example` in `.env`. Caddy gets both certificates on first start.
  - Afterwards you can turn on the orange cloud with SSL mode *Full (strict)*.
- **Cloudflare Tunnel (no open ports):**
  - In Zero Trust > Networks > Tunnels, create a tunnel and copy its token.
  - Add two public hostnames, `dev.afe.example` and `api.dev.afe.example`, both sending traffic to `http://caddy:80`.
  - In `.env`, set `SITE_ADDRESS=http://dev.afe.example`, `API_ADDRESS=http://api.dev.afe.example` and `TUNNEL_TOKEN=...`.
  - Start with `--profile tunnel`.
- Either way, Caddy passes each visitor's real address to the app, so rate limits work per person.

**7. Get the code and fill in the settings**

```bash
git clone https://github.com/<you>/afe-ai.git && cd afe-ai/deploy/free-server
cp .env.example .env
openssl rand -hex 32   # run 3 times: AFE_SECRET_KEY, AFE_PII_HASH_KEY, POSTGRES_PASSWORD
nano .env              # the address, R2, email and backup settings
```

For a private repository, use `gh auth login` or a read-only deploy key.

**8. Start Afe**

```bash
docker compose up -d --build              # the first build on ARM takes 5–10 minutes
# or, with Cloudflare Tunnel:  docker compose --profile tunnel up -d --build
docker compose ps                          # every service "running"; "migrate" exited 0
docker compose logs -f api worker
```

**9. Demo data and a first sign-in**

```bash
docker compose run --rm api python -m app.cli seed-demo --force
# Staff sign in with the demo password, then an authenticator code:
docker compose run --rm -e AFE_DEBUG=1 api python -m app.cli totp reviewer
# Your own admin account:
docker compose run --rm api python -m app.cli create-user <username> --role admin --name "<Your name>" --phone 024XXXXXXX
```

**10. Backups: check them now, not when they're needed**

```bash
docker compose run --rm backup now      # one backup straight away
docker compose run --rm backup list     # it should be in R2
```

Backups then run every night at `BACKUP_HOUR` (01:00 UTC by default) and are kept 30 days.

**Restore drill:** do it once now, and again before beta.

```bash
docker compose stop api worker
docker compose run --rm backup restore afe-20261001-0100.dump
docker compose start api worker
```

**11. Monitoring**
- In UptimeRobot, add an HTTPS monitor for `https://dev.afe.example/`, alerting your email.
- On the server, `docker compose logs api | grep unhandled_error` finds an error by the reference the user was shown.
- Failed jobs log `worker_job_failed`.

**12. The mobile app on this server**
- Build it with `--dart-define=AFE_API_URL=https://api.dev.afe.example --dart-define=AFE_WEB_URL=https://dev.afe.example` (see `mobile/README.md`).
- Testers can install the debug APK that GitHub Actions builds, or a build from `flutter build apk`.

**13. Updating**

```bash
cd ~/afe-ai && git pull && cd deploy/free-server && docker compose up -d --build
```

Migrations run by themselves before the API starts. GitHub Actions has already tested the push.

**Optional:**
- **Real test accounts:** Paystack test keys and the WhatsApp test number, set as in `.env.example`.
- **The ClamAV virus scanner:** `docker compose --profile scan up -d`, and set `AFE_MALWARE_SCANNER=app.modules.media.scan.ClamAvScanner`. The server has the memory for it.

### Moving to AWS at beta

1. **Images:** push the same `afe-api` and `afe-web` images to ECR. The CI workflow already builds them.
2. **Infrastructure:** apply `infra/terraform/staging` and fill in its secrets.
3. **Database:** take a backup (`docker compose run --rm backup now`) and restore it into RDS with `pg_restore --no-owner`. Or start beta clean with only real data.
4. **Files:** copy R2 to S3 with `rclone sync r2:afe-dev-media-public s3:<staging-public-bucket>` (and the same for the private bucket).
5. **Settings:**
   - Email: `ResendEmail` to `SesEmail`.
   - Storage: remove `AFE_S3_ENDPOINT_URL` and the R2 keys (AWS uses the task's IAM role).
   - Turn off `AFE_ALLOW_FAKE_PROVIDERS` once the real providers are in.
6. **Scheduled jobs:** the worker runs without `--with-daily`, because EventBridge runs the daily jobs on AWS.
7. **Keep the free server** as the demo and training site, or switch it off.

### Risks and how we handle them

| Risk | What we do |
|---|---|
| Oracle reclaims an idle Always Free server | Upgrade to Pay As You Go (still free); the worker keeps the server busy; backups are in R2 |
| No ARM capacity in the home region at sign-up | Retry at quiet hours, or start with 2 CPUs and 12 GB; the fallback is AWS below |
| One server, no standby | Fine for development. Nightly backups in R2 and a practised restore; beta on AWS adds Multi-AZ |
| Free-tier limits change | Everything is standard (Docker, PostgreSQL, S3, SMTP), so any provider can be swapped in an hour |
| Personal data on free services | Demo and test data only until beta |

### Fallback: development on AWS

If Oracle's free server isn't available, the same setup runs on one small AWS server, paid from the Free Tier credits. The next two sections cover the AWS Free Tier and that option.

## The AWS Free Tier today

AWS changed its Free Tier on 15 July 2025, and what you get depends on when the account was opened:

- **New accounts (opened after 15 July 2025)** start on a **Free plan**:
  - $100 of credits on sign-up, and up to $100 more for completing the "Explore AWS" activities: **up to $200 in total**.
  - The Free plan lasts **6 months** or until the credits run out, whichever comes first. You are never charged on it; to keep going, upgrade to the Paid plan before it ends. Unused credits carry over and expire 12 months after the account was opened.
  - Some services are not available on the Free plan. Cape Town is an opt-in region that must be enabled first, so build the development environment in Ireland.
- **Older accounts** keep the old 12-month offer: 750 hours a month of a t2/t3.micro server and of a db.t3/t4g.micro database, 20 GB of database storage and 5 GB of S3.
- **Always free, on any plan:**
  - CloudFront: 1 TB and 10 million requests a month.
  - Data out to the internet: 100 GB a month.
  - CloudWatch: 10 metrics, 10 alarms and 5 GB of logs.
  - SNS: 1 million publishes.
  - Lambda: 1 million requests.
  - Systems Manager Parameter Store: standard parameters.
  - AWS Budgets alerts.
- **Never free, and the usual surprise bills:** NAT gateways, load balancers, Multi-AZ databases, public IPv4 addresses (about $3.65 a month each) and anything left running after testing.

## Development on AWS (fallback)

Use this if the free Oracle server isn't available. It is the same setup (`deploy/free-server`) on one AWS server, paid from the Free Tier credits. **Region: Ireland (eu-west-1).** It needs no opt-in and it's the cheapest of the two. Response times from Accra don't matter for testing.

### Option A: one server (recommended)

One EC2 server runs the existing `docker-compose.yml` services: API, website and PostgreSQL. Caddy in front gives free HTTPS through Let's Encrypt.

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| EC2 t4g.small | One server (2 vCPU, 2 GB) running the app with Docker Compose: API, website, Caddy for HTTPS, and PostgreSQL in a container | $16 | $13 |
| EBS disk | 30 GB gp3 disk for the server | $3.15 | $2.64 |
| Public IPv4 address | The server's address (AWS charges for every public IPv4) | $3.65 | $3.65 |
| S3 | Up to 5 GB of photos and documents, replacing MinIO | $0.14 | $0.11 |
| CloudFront | Listing photos over HTTPS; 1 TB and 10 million requests a month are always free | $0 (free) | $0 (free) |
| SES (sandbox) | Email to verified addresses only; a few hundred a month | $0.05 | $0.05 |
| CloudWatch | Basic metrics, 10 alarms and 5 GB of logs are always free | $0 (free) | $0 (free) |
| Parameter Store | Settings and secrets (standard parameters are free) | $0 (free) | $0 (free) |
| AWS Budgets | Email alerts at $1, $10 and $25 | $0 (free) | $0 (free) |
| **Total per month** | | **$23** | **$20** |

At about **$20 a month**, $200 of credits covers the whole 6-month Free plan with room to spare.

### Option B: add a managed database

Use Option B when you want to rehearse RDS before beta. RDS replaces the PostgreSQL container.

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| EC2 t4g.small | One server (2 vCPU, 2 GB) running the app with Docker Compose: API, website, Caddy for HTTPS | $16 | $13 |
| RDS PostgreSQL db.t4g.micro | Managed database, single-AZ, 20 GB, 7-day backups | $18 | $15 |
| EBS disk | 30 GB gp3 disk for the server | $3.15 | $2.64 |
| Public IPv4 address | The server's address (AWS charges for every public IPv4) | $3.65 | $3.65 |
| S3 | Up to 5 GB of photos and documents, replacing MinIO | $0.14 | $0.11 |
| CloudFront | Listing photos over HTTPS; 1 TB and 10 million requests a month are always free | $0 (free) | $0 (free) |
| SES (sandbox) | Email to verified addresses only; a few hundred a month | $0.05 | $0.05 |
| CloudWatch | Basic metrics, 10 alarms and 5 GB of logs are always free | $0 (free) | $0 (free) |
| Parameter Store | Settings and secrets (standard parameters are free) | $0 (free) | $0 (free) |
| AWS Budgets | Email alerts at $1, $10 and $25 | $0 (free) | $0 (free) |
| **Total per month** | | **$41** | **$35** |

About **$35 a month**, which uses up the $200 in about 6 months. Stop the database when nobody's testing. RDS can be stopped for up to 7 days at a time.

### How the development server is set up

- **Server:** `t4g.small`, an ARM (Graviton) server with 2 GB of memory, running Ubuntu 24.04 with Docker. A `t4g.micro` (1 GB) is too small for the API, website and PostgreSQL together.
  - Afe's images build for ARM as they are: the Python and Node base images, and psycopg, all come in ARM versions.
- **Settings:**
  - `AFE_DEBUG=0` with `AFE_ALLOW_FAKE_PROVIDERS=1` (already in `backend/app/config.py`), so the app runs as it will in production but with the test ID-check, SMS and payment providers.
  - `AFE_STORAGE_BACKEND=s3`, pointing at real S3 buckets.
  - `AFE_MALWARE_SCANNER` stays on the fake scanner. ClamAV needs about 1.5 GB of memory of its own.
- **Scheduled jobs:**
  - One `python -m app.cli worker` container runs the every-minute and 5-minute jobs.
  - Cron on the server runs the 5 daily jobs.
- **Security:**
  - The firewall (security group) opens only ports 80 and 443 to everyone, and 22 only to your own IP address. Better still, use Session Manager and open no SSH port at all.
  - Turn on MFA for the root user, and do day-to-day work as a separate IAM user or with IAM Identity Center.
  - The server gets an IAM role for S3 and SES, so there are no access keys on disk.
- **Guard rails:**
  - AWS Budgets alerts at $1, $10 and $25.
  - Free Tier usage alerts.
  - A Cost Anomaly Detection monitor.
  - Never create a NAT gateway or load balancer in the development account.
- **Outside AWS, also free:**
  - GitHub Actions for CI, 2,000 minutes a month for private repositories. Run the backend tests on PostgreSQL there, since they pass on PostgreSQL 17.
  - Sentry's free Developer plan for error tracking.

## Beta (staging): what the Terraform costs

`infra/terraform/staging` builds the production shape at small scale:
- ECS Fargate for the API (with the ClamAV virus scanner beside it), the website and the worker;
- RDS PostgreSQL;
- an Application Load Balancer and one NAT gateway;
- four S3 buckets and CloudFront;
- SES, alarms, and daily backups copied to a second region.

**Two cost fixes are now in the Terraform:**
1. **A free S3 gateway endpoint.** Container images come from S3 and no longer pass through the NAT gateway. Without it, image downloads could have cost $500–1,400 a month.
2. **One always-on worker task** for the frequent jobs, instead of about 120,000 separate task starts a month.

### As written (always on, Multi-AZ database)

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| Fargate: API | 2 tasks × (1 vCPU, 4 GB, including the ClamAV virus scanner) | $115 | $85 |
| Fargate: website | 2 tasks × (0.25 vCPU, 0.5 GB) | $24 | $18 |
| Fargate: worker | 1 task × (0.25 vCPU, 0.5 GB): the every-minute and 5-minute jobs | $12 | $9.01 |
| Fargate: daily jobs | 5 short tasks a day (reconcile, reverify, reports) | $0.13 | $0.10 |
| RDS PostgreSQL | db.t4g.small Multi-AZ (a standby copy), 20 GB | $66 | $55 |
| NAT gateway | 1 gateway, ~20 GB a month (the S3 endpoint keeps image downloads off it) | $43 | $36 |
| Public IPv4 addresses | Load balancer (2) and NAT gateway (1) | $11 | $11 |
| Load balancer | 1 Application Load Balancer, ~1 capacity unit | $29 | $24 |
| CloudWatch | ~5 GB of logs, 12 alarms, Container Insights (~25 metrics) | $13 | $12 |
| Secrets Manager + KMS | 10 secrets and 1 encryption key | $5.00 | $5.00 |
| S3, ECR, CloudFront | 10 GB of files, 3 GB of images, photos within CloudFront's free 1 TB | $0.77 | $0.73 |
| Backups | RDS backups for 35 days, a daily copy in a second region kept a year | $10 | $6.30 |
| SES, Route 53, EventBridge, SNS | Email, DNS zone, the scheduler and alert emails | $1.40 | $1.40 |
| **Total per month** | | **$330** | **$264** |

### Lean beta (recommended until the soft launch)

- One API task and one website task.
- A single-AZ `db.t4g.micro` database.
- Fargate scaled to zero outside 07:00–19:00, Monday to Friday.

The load balancer, NAT gateway and database still run all the time.

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| Fargate: API | 1 task × (1 vCPU, 4 GB, including the ClamAV virus scanner) | $20 | $15 |
| Fargate: website | 1 task × (0.25 vCPU, 0.5 GB) | $4.33 | $3.21 |
| Fargate: worker | 1 task × (0.25 vCPU, 0.5 GB): the every-minute and 5-minute jobs | $4.33 | $3.21 |
| Fargate: daily jobs | 5 short tasks a day (reconcile, reverify, reports) | $0.13 | $0.10 |
| RDS PostgreSQL | db.t4g.micro single-AZ, 20 GB | $18 | $15 |
| NAT gateway | 1 gateway, ~20 GB a month (the S3 endpoint keeps image downloads off it) | $43 | $36 |
| Public IPv4 addresses | Load balancer (2) and NAT gateway (1) | $11 | $11 |
| Load balancer | 1 Application Load Balancer, ~1 capacity unit | $29 | $24 |
| CloudWatch | ~5 GB of logs, 12 alarms, Container Insights (~25 metrics) | $13 | $12 |
| Secrets Manager + KMS | 10 secrets and 1 encryption key | $5.00 | $5.00 |
| S3, ECR, CloudFront | 10 GB of files, 3 GB of images, photos within CloudFront's free 1 TB | $0.77 | $0.73 |
| Backups | RDS backups for 35 days, a daily copy in a second region kept a year | $10 | $6.30 |
| SES, Route 53, EventBridge, SNS | Email, DNS zone, the scheduler and alert emails | $1.40 | $1.40 |
| **Total per month** | | **$160** | **$133** |

Switch beta to the full shape two weeks before the soft launch, and rehearse the launch on it (restore drill, load test).

## Production cost sheet

Production is the staging Terraform with more capacity:
- API and website tasks in two availability zones;
- a Multi-AZ database one size up;
- one NAT gateway per zone;
- AWS WAF in front of the load balancer;
- logs kept 90 days, and backups kept a year in a second region.

**Region (decision B11):**
- **Cape Town** is closest to Accra, with lower delay for users and for mobile money callbacks, and keeps data in Africa. It costs about 20–25% more.
- **Ireland** is cheaper and has every AWS service.

Both are priced below.

### Summary by stage of growth

| Scenario | AWS, Cape Town | AWS, Ireland | Outside AWS | Total (Cape Town) | Total in cedis | Per year (Cape Town) |
|---|---:|---:|---:|---:|---:|---:|
| Year 1 pilot (2–3 Accra neighbourhoods) | $511 | $415 | $198 | **$709** | GHS 8,184 | $8,507 |
| Year 2 (Greater Accra and Tema) | $885 | $719 | $892 | **$1,777** | GHS 20,513 | $21,323 |
| Growth (several Ghanaian cities) | $1,974 | $1,657 | $3,197 | **$5,171** | GHS 59,692 | $62,049 |

The three scenarios assume:

| | Year 1 pilot | Year 2 | Growth |
|---|---|---|---|
| Area | 2–3 Accra neighbourhoods | Greater Accra and Tema | Several Ghanaian cities |
| Verified listings | ~300 | ~1,500 | ~6,000 |
| Protected tenancies a month | 30 | 150 | 600 |
| SMS a month | 10,000 | 50,000 | 200,000 |
| WhatsApp template messages a month | 3,000 | 20,000 | 80,000 |
| Ghana Card checks a month | 120 | 500 | 1,500 |
| Listing photos served a month | 300 GB | 1.5 TB | 5 TB |

### AWS line items: Year 1 pilot

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| Fargate: API | 2 tasks × (1 vCPU, 4 GB, with ClamAV), always on | $115 | $85 |
| Fargate: website | 2 tasks × (0.25 vCPU, 0.5 GB) | $24 | $18 |
| Fargate: worker + daily jobs | 1 worker × (0.25 vCPU, 0.5 GB), 5 daily tasks | $12 | $9.11 |
| RDS PostgreSQL | db.t4g.medium Multi-AZ, 50 GB gp3 | $135 | $113 |
| NAT gateways | 2 (one per availability zone), ~50 GB a month | $86 | $72 |
| Public IPv4 addresses | Load balancer (2), NAT gateways (2) | $15 | $15 |
| Load balancer | 1 ALB, ~2 capacity units | $36 | $30 |
| WAF | 1 web ACL, 5 managed rule groups, ~3 million requests | $12 | $12 |
| CloudWatch | ~10 GB of logs kept 90 days, 15 alarms, Container Insights | $21 | $20 |
| S3 | 100 GB: photos, original uploads (kept as evidence), documents | $4.74 | $4.30 |
| CloudFront | ~300 GB of listing photos a month (within the free 1 TB) | $0 (free) | $0 (free) |
| Data out to the internet | ~150 GB of pages from the load balancer (first 100 GB free) | $7.70 | $4.50 |
| Backups | 35 days of RDS backups; daily copies in a second region kept a year | $31 | $20 |
| Secrets Manager + KMS | 10 secrets, 2 keys | $6.00 | $6.00 |
| SES email | ~20k emails | $2.00 | $2.00 |
| Route 53, ECR, SNS, EventBridge | DNS, container images, alerts, the scheduler | $3.50 | $3.50 |
| **Total per month** | | **$511** | **$415** |

### AWS line items: Year 2

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| Fargate: API | 3 tasks × (1 vCPU, 4 GB, with ClamAV), always on | $172 | $128 |
| Fargate: website | 3 tasks × (0.25 vCPU, 0.5 GB) | $36 | $27 |
| Fargate: worker + daily jobs | 1 worker × (0.25 vCPU, 0.5 GB), 5 daily tasks | $12 | $9.11 |
| RDS PostgreSQL | db.t4g.large Multi-AZ, 100 GB gp3 | $270 | $227 |
| NAT gateways | 2 (one per availability zone), ~50 GB a month | $86 | $72 |
| Public IPv4 addresses | Load balancer (2), NAT gateways (2) | $15 | $15 |
| Load balancer | 1 ALB, ~4 capacity units | $50 | $42 |
| WAF | 1 web ACL, 5 managed rule groups, ~10 million requests | $16 | $16 |
| CloudWatch | ~25 GB of logs kept 90 days, 15 alarms, Container Insights | $33 | $30 |
| S3 | 400 GB: photos, original uploads (kept as evidence), documents | $19 | $17 |
| CloudFront | ~1,500 GB of listing photos a month (1 TB free, the rest at $0.11/GB) | $52 | $52 |
| Data out to the internet | ~400 GB of pages from the load balancer (first 100 GB free) | $46 | $27 |
| Backups | 35 days of RDS backups; daily copies in a second region kept a year | $62 | $41 |
| Secrets Manager + KMS | 10 secrets, 2 keys | $6.00 | $6.00 |
| SES email | ~60k emails | $6.00 | $6.00 |
| Route 53, ECR, SNS, EventBridge | DNS, container images, alerts, the scheduler | $3.50 | $3.50 |
| **Total per month** | | **$885** | **$719** |

### AWS line items: growth

| Item | What it is | Cape Town (af-south-1) | Ireland (eu-west-1) |
|---|---|---:|---:|
| Fargate: API | 5 tasks × (1 vCPU, 4 GB, with ClamAV), always on | $287 | $213 |
| Fargate: website | 4 tasks × (0.25 vCPU, 0.5 GB) | $49 | $36 |
| Fargate: worker + daily jobs | 1 worker × (0.25 vCPU, 0.5 GB), 5 daily tasks | $12 | $9.11 |
| RDS PostgreSQL | db.t4g.xlarge Multi-AZ, 200 GB gp3 | $539 | $454 |
| NAT gateways | 2 (one per availability zone), ~50 GB a month | $86 | $72 |
| Public IPv4 addresses | Load balancer (2), NAT gateways (2) | $15 | $15 |
| Load balancer | 1 ALB, ~10 capacity units | $91 | $77 |
| WAF | 1 web ACL, 5 managed rule groups, ~40 million requests | $34 | $34 |
| CloudWatch | ~60 GB of logs kept 90 days, 15 alarms, Container Insights | $61 | $53 |
| S3 | 1,500 GB: photos, original uploads (kept as evidence), documents | $71 | $64 |
| CloudFront | ~5,000 GB of listing photos a month (1 TB free, the rest at $0.11/GB) | $437 | $437 |
| Data out to the internet | ~1,000 GB of pages from the load balancer (first 100 GB free) | $139 | $81 |
| Backups | 35 days of RDS backups; daily copies in a second region kept a year | $124 | $82 |
| Secrets Manager + KMS | 10 secrets, 2 keys | $6.00 | $6.00 |
| SES email | ~200k emails | $20 | $20 |
| Route 53, ECR, SNS, EventBridge | DNS, container images, alerts, the scheduler | $3.50 | $3.50 |
| **Total per month** | | **$1,974** | **$1,657** |

### Outside AWS: monthly

These rates are estimates:
- Hubtel SMS: GHS 0.015–0.035 per message. The sheet uses GHS 0.035.
- WhatsApp utility templates to Ghana: $0.004–0.0225 per message. The sheet uses $0.0225; replies inside the 24-hour window are free.
- Ghana Card checks: $0.20–1.00 each, depending on the partner chosen for B5. The sheet uses $0.50.

Confirm each with the vendor.

**Year 1 pilot**

| Item | What it is | Per month |
|---|---|---:|
| SMS (Hubtel) | 10,000 messages × GHS 0.035 (sign-in codes, viewing and rent reminders) | $30 |
| WhatsApp (Meta) | 3,000 template messages × $0.0225 (replies within 24 hours are free) | $68 |
| Ghana Card checks (partner B5) | 120 checks × $0.50 | $60 |
| Domain and DNS | afe.com.gh or similar, ~$30 a year | $2.50 |
| Error tracking and CI | Sentry Team and GitHub Team for 3 people (optional) | $38 |
| **Total per month** | | **$198** |

**Year 2**

| Item | What it is | Per month |
|---|---|---:|
| SMS (Hubtel) | 50,000 messages × GHS 0.035 (sign-in codes, viewing and rent reminders) | $152 |
| WhatsApp (Meta) | 20,000 template messages × $0.0225 (replies within 24 hours are free) | $450 |
| Ghana Card checks (partner B5) | 500 checks × $0.50 | $250 |
| Domain and DNS | afe.com.gh or similar, ~$30 a year | $2.50 |
| Error tracking and CI | Sentry Team and GitHub Team for 3 people (optional) | $38 |
| **Total per month** | | **$892** |

**Growth**

| Item | What it is | Per month |
|---|---|---:|
| SMS (Hubtel) | 200,000 messages × GHS 0.035 (sign-in codes, viewing and rent reminders) | $606 |
| WhatsApp (Meta) | 80,000 template messages × $0.0225 (replies within 24 hours are free) | $1,800 |
| Ghana Card checks (partner B5) | 1,500 checks × $0.50 | $750 |
| Domain and DNS | afe.com.gh or similar, ~$30 a year | $2.50 |
| Error tracking and CI | Sentry Team and GitHub Team for 3 people (optional) | $38 |
| **Total per month** | | **$3,197** |

### Payment processing (passed through, not a running cost)

Paystack charges **1.95%** on local card and mobile money payments in Ghana. The escrow partner's own fee depends on decision B7. These fees move with the rent, not with the infrastructure, so they're kept out of the totals above and priced into Afe's fee. During the launch offer (service charges free until 5 Jun 2027), Afe absorbs them.

| Scenario | Protected tenancies a month | Rent advance held (avg GHS 12,000) | Paystack fee at 1.95% |
|---|---:|---:|---:|
| Year 1 pilot (2–3 Accra neighbourhoods) | 30 | GHS 360,000 | GHS 7,020 ($608) |
| Year 2 (Greater Accra and Tema) | 150 | GHS 1,800,000 | GHS 35,100 ($3,041) |
| Growth (several Ghanaian cities) | 600 | GHS 7,200,000 | GHS 140,400 ($12,162) |

### Year 1 budget

| Line | Basis | USD | GHS |
|---|---|---:|---:|
| Development, Oct–Nov 2026 | The free server: Oracle Cloud, Cloudflare, Resend, GitHub | $0 (free) | GHS 0 |
| Staging (lean), 12 months | Scaled down outside working hours | $1,925 | GHS 22,218 |
| Production, 10 months (soft launch 11 Dec 2026 to Sep 2027) | AWS, Cape Town, pilot scale | $5,106 | GHS 58,948 |
| Outside AWS, 10 months | SMS, WhatsApp, Ghana Card checks, domain, tools | $1,983 | GHS 22,894 |
| **Year 1 running costs** | | **$9,014** | **GHS 104,060** |

At the pilot's scale, running Afe costs about **$709 a month** (GHS 8,184). Spread over about 300 verified listings (the plan's "a few hundred" by W52), that is about **$2.36 per live listing per month**; spread over 30 protected tenancies a month, about **$24 per tenancy**.

### One-off costs before launch (estimates)

| Item | Estimate | Notes |
|---|---:|---|
| Security review and penetration test | $3,000–10,000 | Before protected payments open (build plan) |
| Counsel's written opinion on protected payments (B7) | $2,000–6,000 | Required before payments are switched on |
| Data Protection Commission registration | Set by the DPC by organisation size | Confirm the current fee with the DPC before launch |
| Domain names (.com.gh and .com) | $30–60 a year | |
| Hubtel sender ID "Afe" and WhatsApp business verification | Usually free | Allow 1–3 weeks for approval |
| AWS support (optional) | Business support from $100 a month | Worth it once money is held |

## Ways to spend less

- **AWS Activate credits.** Startups can apply for $1,000 or more in credits, often through an accelerator or incubator. This could cover most of Year 1's AWS bill.
- **Compute Savings Plans** once usage is steady (after about 3 months of production): 20–50% off Fargate for a 1-year commitment. RDS Reserved Instances save about 30–40% on the database.
- **ARM (Graviton) Fargate** is about 20% cheaper than x86 at the same size. It needs the images built for `linux/arm64`, which they support.
- **ClamAV:** move the virus scanner to its own small worker, or scan with Amazon GuardDuty Malware Protection for S3. The API tasks can then drop from 4 GB to 1 GB each.
- **Logs:** keep production logs 30 days in CloudWatch and archive to S3 for longer. Turn off Container Insights in beta.
- **One NAT gateway in beta**, and VPC endpoints (already done for S3) before adding more.
- **Scale beta to zero** out of hours (the lean setup above).

## Checklist: from development to production

1. **Decide the region (B11):** Cape Town or Ireland. Enable Cape Town on the account if chosen.
2. **Set up the accounts:**
   - an AWS Organization with separate development, staging and production accounts;
   - MFA everywhere;
   - IAM Identity Center for sign-in;
   - a budget alert on every account.
3. **Apply the staging Terraform**, set the secrets, run `alembic upgrade head`, and smoke-test with real test providers.
4. **Restore drill 1:** restore the database to a point in time and time it (target: back within 4 hours, at most 1 hour of data lost).
5. **Real providers:**
   - the ID-check partner (B5);
   - the payment and escrow partner (B7, after counsel's opinion);
   - Hubtel sender ID;
   - an approved WhatsApp template.
6. **Security review**, WAF rules on, alarms tested (the email arrives), and the runbooks (`docs/runbooks.md`) walked through.
7. **Production:** apply the Terraform with production sizes, load-test the pilot's expected traffic, then do the soft launch (11 Dec 2026).
8. **After 3 months:** review actual costs against this sheet, then buy Savings Plans.
