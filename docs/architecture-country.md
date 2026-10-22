# House Agent - Technical Architecture Documentation

**Platform**: African Property SaaS Platform  
**Target Markets**: East & West Africa  
**Primary Country**: Nigeria (NG)  
**Generated**: 2026-05-05 04:48:18  
**Version**: 1.0.0

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Technology Stack](#technology-stack)
- [Regional Configuration - Nigeria](#regional-configuration---nigeria)
- [System Architecture](#system-architecture)
- [Data Flow Diagrams](#data-flow-diagrams)
- [Security Architecture](#security-architecture)
- [Deployment Architecture](#deployment-architecture)
- [Cost Estimates](#cost-estimates)
- [API Reference (Core Endpoints)](#api-reference-(core-endpoints))


## Executive Summary

House Agent is a mobile-first property platform designed for the African market, with built-in fraud prevention, multi-tenancy, and region-specific payment integration. The platform enables property listings, verification, escrow transactions, and secure payments across Nigeria and other African countries.

### Key Features
- 🏠 **Property Listings**: Search, filter, and browse verified properties
- 🔐 **Anti-Fraud System**: ML-based fraud detection with 0-100 trust scores
- 💰 **Escrow Payments**: Time-locked, multi-signature fund release
- 📱 **Mobile-First**: native Android (Kotlin) and iOS (Swift) apps with offline-first architecture
- 🌍 **Multi-Region**: Country-level data isolation and compliance
- ⚡ **Real-Time**: WebSocket updates for property availability

### Target Users
1. **Tenants**: Looking for rental properties
2. **Landlords**: Property owners listing for rent/sale
3. **Agents**: Real estate professionals managing multiple listings
4. **Property Managers**: Companies managing portfolios

---

## Technology Stack

### Backend
- Framework: FastAPI 0.104+ (Python 3.11)
- ORM: SQLAlchemy 2.0 + Alembic
- Validation: Pydantic v2
- Task Queue: Celery + Redis
- WebSockets: Native FastAPI
- API Docs: OpenAPI/Swagger (auto-generated)

### Database
- Primary DB: PostgreSQL 15+
- Extensions: PostGIS (geospatial), pg_trgm (search), uuid-ossp
- Search Engine: Typesense (typo-tolerant, geo-aware)
- Cache: Redis 7
- Multi-tenancy: Row-Level Security (RLS)

### Frontend
- Mobile: Android (Kotlin + Jetpack Compose), iOS (Swift + SwiftUI)
- Performance modules: Rust (PyO3 `afe_native`) for photo hashing, image processing, scoring
- Web: SvelteKit (SSR, PWA)
- Admin: Django Admin

### Infrastructure
- Cloud: AWS (eu-west-1 primary, af-south-1 secondary)
- CDN: CloudFront (Lagos, Nairobi, Johannesburg POPs)
- Containers: Docker + Kubernetes (EKS)
- CI/CD: GitHub Actions → ArgoCD
- Monitoring: Prometheus + Grafana / Datadog

### Security
- Authentication: OAuth 2.0 + JWT (15-min expiry)
- Encryption: TLS 1.3 (transit), AES-256-GCM (at rest)
- Payment: PCI DSS compliant via Flutterwave/Paystack
- Rate Limiting: Redis-based (100 req/min per IP)

---

## Regional Configuration - Nigeria

### Payment Integration
**Primary Providers**: Paystack, Flutterwave

**Supported Methods**:
- Mobile Money (M-Pesa, MTN, Airtel)
- Bank Transfer
- Debit/Credit Cards
- USSD (for non-smartphone users)

**Currency**: NGN

**Transaction Fees**:
- Platform commission: 3.5% (pending decision D6; RFC-002 says 2.5%. Note the gateway fee below is charged on the full escrowed amount, not on the commission - see Statement 12.2)
- Payment gateway: 1.5-2.0%
- Agent commission: 3-5% (negotiable)

### Compliance
**Regulation**: Nigeria Data Protection Regulation (NDPR)

**Data Requirements**:
- User consent for data collection (GDPR-style)
- Data retention: 7 years for financial records
- Right to erasure: 30-day processing
- Data breach notification: 72 hours

### Localization
**Languages**: English, Yoruba, Igbo, Hausa

**Property Types**:
- Bungalow
- Duplex
- Terrace
- Flat

**Date/Time Format**:
- Date: DD/MM/YYYY
- Time: 24-hour format
- Timezone: Nigeria Standard Time

---

## System Architecture


┌────────────────────────────────────────────────────────────────┐
│                       User Devices                              │
├────────────────────────────────────────────────────────────────┤
│  Android/iOS (native)   │  Web Browser (SvelteKit PWA)         │
└────────────────────────────────────────────────────────────────┘
                              ↓ HTTPS
┌────────────────────────────────────────────────────────────────┐
│                    CDN / Edge Network                           │
├────────────────────────────────────────────────────────────────┤
│  CloudFront POPs (Lagos, Nairobi, Johannesburg)                │
│  • Static assets (images, CSS, JS)                             │
│  • Cached API responses                                        │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                  Application Load Balancer                      │
├────────────────────────────────────────────────────────────────┤
│  • TLS termination                                             │
│  • Rate limiting                                               │
│  • Health checks                                               │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│              FastAPI Application Cluster (K8s)                  │
├────────────────────────────────────────────────────────────────┤
│  Pod 1: API Server  │  Pod 2: API Server  │  Pod 3: API Server │
│  (Uvicorn workers)  │  (Uvicorn workers)  │  (Uvicorn workers) │
│                     │                     │                     │
│  • REST endpoints   │  • GraphQL          │  • WebSockets      │
│  • Auth middleware  │  • Fraud detection  │  • Real-time feed  │
└────────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌──────────────┐   ┌───────────────┐   ┌─────────────────────────┐
│ PostgreSQL   │   │    Redis      │   │   Celery Workers        │
│              │   │               │   │                         │
│ • Properties │   │ • Sessions    │   │ • Image processing      │
│ • Users      │   │ • Cache       │   │ • Fraud analysis        │
│ • Escrow     │   │ • Pub/Sub     │   │ • Email/SMS             │
│ • Audit logs │   │ • Rate limit  │   │ • Report generation     │
└──────────────┘   └───────────────┘   └─────────────────────────┘
         ↓                                        ↓
┌──────────────┐                        ┌─────────────────────────┐
│  Typesense   │                        │   S3 Object Storage     │
│              │                        │                         │
│ • Full-text  │                        │ • Property images       │
│   search     │                        │ • Documents (locked)    │
│ • Geo query  │                        │ • KYC (private bucket)  │
└──────────────┘                        └─────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                   External Services                             │
├────────────────────────────────────────────────────────────────┤
│  Flutterwave  │  Paystack  │  SMS Gateway  │  Email (SES)      │
└────────────────────────────────────────────────────────────────┘

---

## Data Flow Diagrams

### 1. Property Listing Creation


┌─────────┐
│  User   │ (Agent/Landlord)
└────┬────┘
     │ 1. POST /api/properties
     ↓
┌────────────────┐
│  FastAPI       │
│  Endpoint      │
└────┬───────────┘
     │ 2. Validate with Pydantic
     ↓
┌────────────────┐
│  Fraud Check   │
│  (Pre-listing) │
└────┬───────────┘
     │ 3. Check duplicates (image hashing)
     │ 4. Verify agent KYC
     │ 5. Calculate initial fraud score
     ↓
┌────────────────┐      NO (score < 40)
│  Score >= 40?  │ ───────────────────→ Reject + notify moderator
└────┬───────────┘
     │ YES
     │ 6. Insert into PostgreSQL
     ↓
┌────────────────┐
│  Database      │
│  (properties   │
│   table)       │
└────┬───────────┘
     │ 7. Trigger: Calculate full fraud score
     │ 8. Index in Typesense (async)
     ↓
┌────────────────┐
│  Celery Task   │
│  (Background)  │
└────┬───────────┘
     │ 9. Process images (resize, compress)
     │ 10. Compute perceptual hashes
     │ 11. Store in S3
     ↓
┌────────────────┐
│  Response      │
│  (201 Created) │
└────────────────┘


### 2. Property Search


┌─────────┐
│  User   │ (Tenant)
└────┬────┘
     │ 1. GET /api/properties/search?city=Lagos&max_price=50000
     ↓
┌────────────────┐
│  FastAPI       │
│  Endpoint      │
└────┬───────────┘
     │ 2. Check Redis cache
     ↓
┌────────────────┐     HIT
│  Redis Cache   │ ─────────→ Return cached results
└────┬───────────┘
     │ MISS
     │ 3. Query Typesense (fast full-text + geo search)
     ↓
┌────────────────┐
│  Typesense     │
│  Search        │
└────┬───────────┘
     │ 4. Returns property IDs + scores
     ↓
┌────────────────┐
│  PostgreSQL    │
│  Fetch details │
└────┬───────────┘
     │ 5. Enrich with fraud scores, agent info
     │ 6. Filter: status='active', fraud_score >= 40
     ↓
┌────────────────┐
│  Cache result  │ (TTL: 5 minutes)
│  in Redis      │
└────┬───────────┘
     │ 7. Return JSON
     ↓
┌────────────────┐
│  Response      │
│  (200 OK)      │
└────────────────┘


### 3. Escrow Payment Flow


┌─────────┐
│ Tenant  │
└────┬────┘
     │ 1. POST /api/escrow/create
     │    {property_id, amount}
     ↓
┌────────────────┐
│  FastAPI       │
│  Create Escrow │
└────┬───────────┘
     │ 2. Verify property availability
     │ 3. Check tenant verification status
     ↓
┌────────────────┐
│  PostgreSQL    │
│  Insert escrow │
│  (status:      │
│   pending)     │
└────┬───────────┘
     │ 4. Initiate payment with Flutterwave
     ↓
┌────────────────┐
│  Flutterwave   │
│  Payment API   │
└────┬───────────┘
     │ 5. User redirected to payment page
     │ 6. Completes payment (card/mobile money)
     │ 7. Webhook: payment.successful
     ↓
┌────────────────┐
│  FastAPI       │
│  Webhook       │
│  Handler       │
└────┬───────────┘
     │ 8. Verify webhook signature
     │ 9. Update escrow (status: processing)
     │ 10. Lock funds (time_locked_until = NOW + 7 days)
     ↓
┌────────────────┐
│  PostgreSQL    │
│  Update escrow │
└────┬───────────┘
     │ 11. Notify all parties (email/SMS)
     ↓
┌────────────────┐
│  Celery Task   │
│  (Email/SMS)   │
└────┬───────────┘
     │ 12. Wait for release conditions:
     │     - Keys handed over
     │     - Move-in confirmed
     │     - Inspection completed
     ↓
┌────────────────┐
│  Multi-sig     │ (Requires 2 of 3: buyer, seller, platform)
│  Release       │
└────┬───────────┘
     │ 13. Release funds in tranches:
     │     - 10% on listing verified
     │     - 40% on inspection complete
     │     - 50% on keys handover + 7 day time lock
     ↓
┌────────────────┐
│  Flutterwave   │
│  Payout API    │
└────┬───────────┘
     │ 14. Transfer to seller account
     │ 15. Update escrow (status: completed)
     ↓
┌────────────────┐
│  Complete      │
└────────────────┘


---

## Security Architecture

### 1. Authentication & Authorization

**Flow**: OAuth 2.0 with JWT tokens

# Python example:
# Login flow
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "***"
}

# Response
{
  "access_token": "eyJhbGc...",  # Expires in 15 minutes
  "refresh_token": "fdb8fdbecf...",  # Expires in 7 days
  "token_type": "Bearer"
}

# Protected endpoint
GET /api/properties/my-listings
Authorization: Bearer eyJhbGc...


**Security Measures**:
- ✅ Password hashing: bcrypt (cost factor 12)
- ✅ JWT signed with RS256 (asymmetric keys)
- ✅ Refresh token rotation (single use)
- ✅ Device fingerprinting (track suspicious logins)
- ✅ Rate limiting: 5 login attempts per 15 minutes
- ✅ Account lockout: 30 minutes after 5 failed attempts

### 2. Data Encryption

**At Rest**:
- Database: AES-256-GCM (PostgreSQL TDE)
- Files: S3 SSE-KMS; customer-managed KMS key for the KYC bucket
- Sensitive fields: Application-level encryption (ChaCha20-Poly1305)

**In Transit**:
- TLS 1.3 with perfect forward secrecy
- Certificate pinning in mobile apps
- HSTS headers (max-age=31536000)

### 3. API Security

**Rate Limiting** (Redis-based):
# Python example:
# Per endpoint limits
/api/auth/login:           5 req/15min per IP
/api/properties/search:    100 req/min per user
/api/escrow/create:        10 req/hour per user
/api/properties/create:    20 req/hour per agent


**Input Validation**:
- Pydantic models (type checking)
- SQL injection prevention (parameterized queries)
- XSS prevention (Content Security Policy)
- CSRF tokens (state-changing operations)

### 4. Anti-Fraud Measures

See `fraud-detection.md` for full algorithms.

**Real-time Checks**:
1. Duplicate image detection (perceptual hashing)
2. Property verification score (0-100)
3. Anomaly detection (Isolation Forest ML)
4. Device fingerprinting
5. Behavioral analysis

**Offline Jobs** (run hourly):
1. Fraud ring detection (graph analysis)
2. Payment pattern analysis
3. Review score recalculation

### 5. Audit Logging

**All sensitive operations logged**:
```sql
INSERT INTO audit_logs (user_id, action, entity_type, entity_id, ip_address, old_values, new_values)
VALUES (
  'uuid-123',
  'property_suspended',
  'property',
  'uuid-456',
  '197.210.x.x',
  '{"status": "active"}',
  '{"status": "suspended", "reason": "fraud_detected"}'
);


**Retention**:
- Hot logs: 90 days (PostgreSQL)
- Cold logs: 7 years (S3 + Glacier)
- Compliance: GDPR/NDPR/DPA

---

## Deployment Architecture

### Infrastructure (AWS)

**Regions** (primary region pending decision D2 - measure latency from Ghana first):
- Primary: eu-west-1 (Ireland) - lowest latency to West Africa
- Secondary: af-south-1 (Cape Town) - East/Southern Africa
- DR: us-east-1 (N. Virginia) - disaster recovery

**Kubernetes Cluster** (EKS):
# YAML example:
# Production cluster
Node Groups:
  - Name: api-nodes
    Instance Type: t3.large (2 vCPU, 8 GB RAM)
    Min Size: 3
    Max Size: 20
    Auto-scaling: CPU > 70% or Memory > 80%
  
  - Name: worker-nodes
    Instance Type: t3.xlarge (4 vCPU, 16 GB RAM)
    Min Size: 2
    Max Size: 10
    Auto-scaling: Queue depth > 100

Namespaces:
  - production
  - staging
  - monitoring


**Database** (RDS):
# YAML example:
PostgreSQL 15.4:
  Instance Class: db.t3.large (2 vCPU, 8 GB RAM)
  Storage: 500 GB SSD (gp3)
  Multi-AZ: true
  Backup:
    Retention: 30 days
    Automated snapshots: daily at 03:00 UTC
  Read Replicas: 2 (for scaling reads)


**Cache** (ElastiCache):
# YAML example:
Redis 7.0:
  Instance Type: cache.t3.medium (2 vCPU, 3.09 GB RAM)
  Cluster Mode: enabled
  Replicas: 2
  Auto-failover: enabled


### Storage & Backup

**Object storage (S3)** — the database stores each file's bucket and key, never a full URL:

| Bucket | Contents | Access | Protection |
|---|---|---|---|
| `afe-media-public` | Processed listing photos (WebP sizes) | Public via CloudFront only | Rebuildable from originals |
| `afe-media-originals` | Raw uploads, chat photos (private prefix) | Backend only; signed URLs | Versioning + cross-region replication |
| `afe-kyc-private` | ID cards, ownership docs, agent licences | Admin reviewers; signed URLs expiring in minutes | Customer-managed KMS key, public access blocked, access logged |
| `afe-documents` | Tenancy agreements, receipts, dispute evidence | Deal parties + admins | Versioning + Object Lock |
| `afe-backups` | DB snapshots and exports | Separate AWS account, no app access | Object Lock + second region |

**Upload pipeline**: presigned URL -> `quarantine/` prefix -> S3 event -> worker (file-type check, malware scan,
read EXIF GPS/date into the database then strip metadata, perceptual hash + WebP sizes via the Rust `afe_native`
module) -> final bucket. Rejected files are deleted after 7 days.

**Backup targets**: RTO <= 4 hours, RPO <= 1 hour.

| Asset | Method | Retention |
|---|---|---|
| PostgreSQL | RDS Multi-AZ + point-in-time recovery; daily AWS Backup snapshot copied to a second region and to the backup account | 35 days PITR; monthly snapshots 12 months |
| Audit logs | Monthly partitions exported to S3, then Glacier | 7 years |
| S3 files | Versioning + replication (originals, KYC, documents); Object Lock (documents, backups) | Per retention policy |
| Redis | Not backed up - sessions and check-in tokens are disposable. Payment and escrow events go to the Postgres outbox first | n/a |
| Typesense | Rebuilt from Postgres; snapshot only to speed recovery | Latest |
| Infrastructure | Terraform in Git; secrets in Secrets Manager (replicated) | Git history |
| App signing keys | Play App Signing; upload key and iOS certificates in a team vault | Permanent |

**Restore drills**: full restore into a test account before launch and every quarter, timed against the 4-hour RTO.
Once a year, rebuild the environment from Terraform in the second region.

### CI/CD Pipeline


┌─────────────┐
│  Developer  │
│  Push Code  │
└──────┬──────┘
       │
       ↓
┌─────────────────┐
│  GitHub Actions │ (CI)
├─────────────────┤
│ 1. Run tests    │
│ 2. Lint code    │
│ 3. Security scan│
│ 4. Build Docker │
│ 5. Push to ECR  │
└──────┬──────────┘
       │
       ↓
┌─────────────────┐
│    ArgoCD       │ (CD)
├─────────────────┤
│ 1. Detect       │
│    changes      │
│ 2. Pull image   │
│ 3. Apply K8s    │
│    manifests    │
│ 4. Rolling      │
│    update       │
└──────┬──────────┘
       │
       ↓
┌─────────────────┐
│  EKS Cluster    │
├─────────────────┤
│ New pods        │
│ deployed        │
└─────────────────┘


**GitHub Actions Workflow**:
# YAML example:
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/
      
      - name: Security scan
        run: |
          pip install bandit semgrep
          bandit -r src/
          semgrep --config=auto .
  
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker image
        run: docker build -t house-agent-api:${{ github.sha }} .
      
      - name: Push to ECR
        run: |
          aws ecr get-login-password | docker login ...
          docker push house-agent-api:${{ github.sha }}
      
      - name: Update ArgoCD
        run: |
          # Update image tag in K8s manifests
          argocd app sync house-agent-production


### Scaling Strategy

**Horizontal Scaling** (Auto-scaling):
# YAML example:
# HorizontalPodAutoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fastapi-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fastapi-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80


**Vertical Scaling** (When to upgrade):
- DB: When CPU > 80% consistently → upgrade to db.r6g.large
- Redis: When memory > 90% → upgrade to cache.r6g.large
- Nodes: When all pods at max → add larger instance types

### Monitoring & Alerting

**Metrics** (Prometheus + Grafana):
- API latency (P50, P95, P99)
- Request rate (req/sec)
- Error rate (4xx, 5xx)
- Database query time
- Fraud score distribution
- Payment success rate

**Alerts** (PagerDuty):
# YAML example:
Alerts:
  - name: HighErrorRate
    condition: error_rate > 5%
    duration: 5m
    severity: critical
  
  - name: SlowAPI
    condition: p95_latency > 500ms
    duration: 10m
    severity: warning
  
  - name: FraudSpike
    condition: fraud_reports > 50/hour
    duration: 5m
    severity: critical


---

## Cost Estimates

### Monthly Infrastructure Costs (Startup Phase)

| Service | Configuration | Monthly Cost (USD) |
|---------|--------------|-------------------|
| **EKS Cluster** | Control plane | $75 |
| **EC2 Nodes** | 3x t3.large (API) | $150 |
| **EC2 Nodes** | 2x t3.xlarge (workers) | $120 |
| **RDS PostgreSQL** | db.t3.large + Multi-AZ | $180 |
| **ElastiCache Redis** | cache.t3.medium + replicas | $45 |
| **S3** | 1 TB storage + 10 TB transfer | $120 |
| **CloudFront** | 10 TB data transfer | $85 |
| **Typesense Cloud** | Starter plan | $30 |
| **Route53** | Hosted zone + queries | $5 |
| **ACM** | SSL certificates | $0 (free) |
| **Monitoring** | CloudWatch + Datadog (or self-hosted) | $75 |
| **Backups** | S3 + Glacier | $25 |
| **Payment Gateway** | Flutterwave/Paystack transaction fees | Variable |
| **SMS** | Twilio/Africa's Talking | Variable |
| **TOTAL** | | **~$910/month** |

### Scaling Projections

| User Count | Infra Cost/Month | Notes |
|-----------|------------------|-------|
| **0-10k** | $910 | Starter config |
| **10k-50k** | $1,800 | Add read replicas, more nodes |
| **50k-100k** | $3,200 | Upgrade DB to db.r6g.large, 10+ nodes |
| **100k-500k** | $8,000 | Multi-region, CDN optimization |
| **500k-1M** | $18,000 | Dedicated caching layer, microservices |

### Cost Optimization Tips

1. **Use Spot Instances**: 60-70% savings on worker nodes (Celery)
2. **Reserved Instances**: 30-40% savings on RDS (1-year commitment)
3. **S3 Lifecycle Policies**: Move old images to Glacier after 90 days
4. **CDN Optimization**: Cache aggressively (reduce origin requests)
5. **Database Query Optimization**: Proper indexes reduce RDS size needs
6. **Auto-scaling**: Scale down during off-peak hours (2am-6am)

---

## API Reference (Core Endpoints)

**Base URL**: `https://api.houseagent.com/v1`

### Authentication

```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+234801234567",
  "role": "tenant"
}

Response: 201 Created
{
  "user_id": "uuid-123",
  "email": "user@example.com",
  "verification_status": "unverified"
}


```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

Response: 200 OK
{
  "access_token": "eyJhbGc...",
  "refresh_token": "fdb8fdb...",
  "token_type": "Bearer",
  "expires_in": 900
}


### Properties

```http
GET /api/properties/search
  ?city=Lagos
  &max_price=500000
  &bedrooms=2
  &property_type=apartment
  &listing_type=rent

Response: 200 OK
{
  "total": 42,
  "results": [
    {
      "id": "uuid-456",
      "title": "Modern 2BR in Lekki",
      "price": 450000,
      "currency": "NGN",
      "location": {
        "city": "Lagos",
        "state": "Lagos State",
        "lat": 6.4541,
        "lng": 3.3947
      },
      "verification_score": 85,
      "risk_level": "LOW",
      "images": ["url1", "url2"],
      "agent": {
        "id": "uuid-789",
        "name": "Jane Agent",
        "reputation_score": 92
      }
    }
  ]
}


```http
POST /api/properties
Authorization: Bearer eyJhbGc...
Content-Type: application/json

{
  "title": "Luxury 3BR Apartment",
  "description": "Spacious apartment with modern amenities",
  "property_type": "apartment",
  "listing_type": "rent",
  "price": 800000,
  "currency": "NGN",
  "bedrooms": 3,
  "bathrooms": 2,
  "area_sqm": 120,
  "location": {
    "address": "123 Lekki Road",
    "city": "Lagos",
    "state": "Lagos State",
    "lat": 6.4541,
    "lng": 3.3947
  },
  "amenities": ["parking", "security", "generator"],
  "images": ["data:image/jpeg;base64,..."]
}

Response: 201 Created
{
  "id": "uuid-new",
  "status": "pending_review",
  "verification_score": 65,
  "risk_level": "MEDIUM",
  "message": "Property submitted for review. You'll be notified within 24 hours."
}


### Escrow

```http
POST /api/escrow
Authorization: Bearer eyJhbGc...
Content-Type: application/json

{
  "property_id": "uuid-456",
  "total_amount": 450000,
  "deposit_amount": 900000,
  "rent_period": "yearly"
}

Response: 201 Created
{
  "escrow_id": "uuid-escrow",
  "payment_url": "https://flutterwave.com/pay/...",
  "expires_at": "2024-01-15T10:30:00Z"
}


**Full API documentation**: Auto-generated Swagger UI at `/docs`

---
