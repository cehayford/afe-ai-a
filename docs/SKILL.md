---
name: house-agent-africa
description: Architecture, database design, and fraud detection for African SaaS property platforms. Use this skill whenever the user mentions House Agent, property platforms, real estate SaaS for East/West Africa, anti-fraud systems for property listings, escrow systems, multi-tenant architecture for African markets, FastAPI backend design, or generating technical documentation for property technology startups. Also trigger for questions about African payment integrations (Flutterwave, Paystack), mobile-first design for African markets, offline-first architecture, or region-specific compliance (Nigeria, Ghana, Kenya, Tanzania, South Africa).
---

# House Agent - African Property SaaS Platform Architecture

A comprehensive skill for designing, building, and documenting secure property platforms for East and West African markets, with built-in fraud prevention, multi-tenancy, and mobile-first architecture.

## Overview

This skill enables senior engineers to rapidly scaffold and document production-ready property platforms with:
- **Regional optimization** for African market constraints (bandwidth, mobile-first, offline capability)
- **Anti-fraud architecture** (property verification, escrow, duplicate detection, scam prevention)
- **Multi-tenant design** (country-level data isolation, region-specific compliance)
- **Payment integration** (Flutterwave, Paystack, mobile money, USSD)
- **Security-first** (authentication, encryption, rate limiting, audit trails)

## Core Architecture Stack

### **Backend: Python + FastAPI, with Rust for hot paths**
- **Framework**: FastAPI 0.104+ (async, high-performance REST/GraphQL APIs)
- **ORM**: SQLAlchemy 2.0 + Alembic (migrations)
- **Validation**: Pydantic v2 (strict type checking)
- **Task Queue**: Celery + Redis (background jobs)
- **WebSockets**: Native FastAPI (real-time property updates)
- **Revenue**: 3.5% escrow transaction fee (D6) + premium agent subscription (D22); tenants never pay to search
- **Object storage**: Amazon S3, split into public media, raw originals, KYC (customer-managed KMS key), documents (Object Lock) and backups (separate account). MinIO locally
- **Backups**: RDS point-in-time recovery + AWS Backup copies to a second region and a separate account; RTO 4 h / RPO 1 h, drilled quarterly
- **Rust native module** (`afe_native`, PyO3 + maturin): perceptual hashing, image resize/WebP, verification and GPS check-in scoring. Pure functions only; Python owns business logic and database writes

### **Database: PostgreSQL 15+**
- **Extensions**: PostGIS (geospatial), pg_trgm (fuzzy search), uuid-ossp
- **Multi-tenancy**: Row-level security (RLS) per country
- **Partitioning**: Time-series tables for audit logs, analytics
- **Replication**: Multi-region (Lagos, Nairobi, Johannesburg)

### **Search: Typesense**
- Typo-tolerant search (African names/locations)
- Geo-filtering (properties within radius)
- Faceted filtering (price, bedrooms, verified status)

### **Cache & Session: Redis 7**
- Session storage (JWT blacklist, user sessions)
- Rate limiting (prevent scraping, DDoS)
- Real-time counters (property views, favorites)
- Task queue backend (Celery broker)

### **Frontend**
- **Android**: Kotlin + Jetpack Compose (native)
- **iOS**: Swift + SwiftUI (native)
- **Web**: SvelteKit (SSR, PWA, offline-first)
- **Admin**: Admin role inside the SvelteKit app

### **Infrastructure**
- **Cloud**: AWS (eu-west-1 primary, af-south-1 secondary)
- **CDN**: CloudFront (Lagos, Nairobi, Johannesburg POPs)
- **Containers**: Docker + Kubernetes (EKS)
- **CI/CD**: GitHub Actions → ArgoCD

## When to Use This Skill

### Primary Triggers
- Designing property/real estate platforms for African markets
- Building anti-fraud systems for property transactions
- Creating multi-tenant SaaS with country-level isolation
- Implementing escrow/payment systems for African countries
- Generating architecture documentation for property tech startups
- Designing databases with geospatial + anti-fraud requirements

### Specific Use Cases
1. **Architecture Documentation**: Generate comprehensive tech specs for House Agent platform
2. **Database Design**: Create schemas with anti-fraud tables, multi-tenancy, audit trails
3. **Fraud Detection**: Implement production-ready algorithms (duplicate detection, anomaly detection, graph analysis)
4. **API Design**: FastAPI endpoints with Pydantic validation, rate limiting, caching
5. **Security Implementation**: Auth flows, encryption, row-level security, audit logging
6. **Payment Integration**: Flutterwave/Paystack setup with escrow and split payments
7. **Mobile Optimization**: Offline-first patterns, data syncing, image compression
8. **Compliance**: GDPR, Nigerian DPA, Kenyan Data Protection Act, South African POPIA

## Workflow

When this skill is triggered, Claude should:

1. **Understand Context**: Clarify which component is needed (full architecture, database only, fraud detection, etc.)
2. **Read References**: Load relevant documentation from `references/` directory
3. **Generate Artifacts**: Produce production-ready code, schemas, or documentation
4. **Regional Customization**: Adapt for specific countries (payment methods, compliance, languages)
5. **Security Review**: Ensure anti-fraud measures, encryption, and access controls are in place

## Key Design Principles

### 1. Mobile-First (80%+ African users on mobile)
- Offline-first architecture (service workers, local storage)
- Image optimization (WebP, lazy loading, CDN)
- Low bandwidth optimization (<100KB initial page load)
- Progressive Web App (PWA) capabilities

### 2. Security & Anti-Fraud
- **Property Verification Score**: ML-based trust scoring (0-100)
- **Duplicate Detection**: Perceptual image hashing
- **Escrow with Time-Locks**: Multi-signature fund release
- **Graph Analysis**: Fraud ring detection
- **Device Fingerprinting**: Track suspicious patterns
- **Rate Limiting**: Prevent scraping, credential stuffing

### 3. Multi-Tenancy
- **Country-level isolation**: PostgreSQL Row-Level Security (RLS)
- **Regional compliance**: Per-country data residency, privacy laws
- **Localization**: Multiple languages (English, French, Swahili, Yoruba, Twi)
- **Currency support**: NGN, GHS, KES, TZS, ZAR, USD

### 4. Performance
- **Async I/O**: FastAPI with asyncio/asyncpg
- **Database indexing**: B-tree, GiST (geospatial), GIN (full-text)
- **Caching strategy**: Redis (hot data), CDN (static assets)
- **Query optimization**: Materialized views, partitioning

### 5. Observability
- **Logging**: Structured JSON logs (ELK stack or Datadog)
- **Metrics**: Prometheus (API latency, error rates, fraud detection scores)
- **Tracing**: OpenTelemetry (distributed tracing)
- **Alerts**: PagerDuty (fraud spikes, payment failures, downtime)

## File Structure

```
house-agent-skill/
├── SKILL.md                          # This file
├── references/
│   ├── database-schema.md            # Complete PostgreSQL schema
│   ├── fraud-detection.md            # Production fraud algorithms
│   ├── api-design.md                 # FastAPI patterns and endpoints
│   ├── security-guide.md             # Auth, encryption, compliance
│   ├── payment-integration.md        # Flutterwave/Paystack setup
│   ├── deployment-guide.md           # AWS/K8s deployment
│   └── regional-config.md            # Per-country customizations
├── scripts/
│   ├── generate_architecture_doc.py  # Auto-generate tech specs
│   ├── init_database.py              # Create schema with seed data
│   ├── fraud_detection.py            # Production-ready algorithms
│   └── api_generator.py              # Scaffold FastAPI endpoints
├── rust/                             # Cargo workspace: afe-core, afe-py (PyO3), afe-realtime (R2)
└── templates/
    ├── fastapi_endpoint.py.j2        # API endpoint template
    ├── pydantic_model.py.j2          # Data validation template
    └── architecture_doc.md.j2        # Documentation template
```

## Quick Start Examples

### Example 1: Generate Full Architecture Documentation
```
User: "Generate the complete architecture documentation for House Agent"

Claude actions:
1. Read references/architecture-patterns.md
2. Read references/database-schema.md
3. Read references/fraud-detection.md
4. Run scripts/generate_architecture_doc.py
5. Output comprehensive markdown documentation with:
   - Stack overview
   - Database ERD
   - API design
   - Security architecture
   - Deployment strategy
   - Cost estimates
```

### Example 2: Design Database Schema
```
User: "Create the database schema with anti-fraud tables"

Claude actions:
1. Read references/database-schema.md
2. Generate PostgreSQL DDL with:
   - Multi-tenant tables (countries, users, properties)
   - Anti-fraud tables (verification_scores, fraud_reports, escrow_transactions)
   - Geospatial indexes (PostGIS)
   - Row-level security policies
   - Audit triggers
3. Output migration files (Alembic)
```

### Example 3: Implement Fraud Detection
```
User: "Write the fraud detection algorithms for property listings"

Claude actions:
1. Read references/fraud-detection.md
2. Generate Python code for:
   - Duplicate image detection (perceptual hashing)
   - Anomaly detection (Isolation Forest)
   - Graph-based fraud ring detection
   - Real-time scoring API endpoint
3. Include tests and performance benchmarks
```

### Example 4: Create FastAPI Endpoint
```
User: "Create an API endpoint for searching properties with fraud filtering"

Claude actions:
1. Read references/api-design.md
2. Generate:
   - Pydantic request/response models
   - FastAPI route with validation
   - Database query with fraud score filtering
   - Caching logic (Redis)
   - Rate limiting
   - Unit tests
```

## Regional Considerations

### Nigeria
- **Payment**: Paystack, Flutterwave (bank transfer, USSD, cards)
- **Compliance**: Nigeria Data Protection Regulation (NDPR)
- **Languages**: English, Yoruba, Igbo, Hausa
- **Property Types**: Bungalow, duplex, terrace, flat

### Ghana
- **Payment**: Flutterwave, Paystack (mobile money: MTN, Vodafone)
- **Compliance**: Data Protection Act 2012
- **Languages**: English, Twi, Ga, Ewe
- **Property Types**: Chamber and hall, self-contained, compound house

### Kenya
- **Payment**: M-Pesa (dominant), Flutterwave
- **Compliance**: Data Protection Act 2019
- **Languages**: English, Swahili
- **Property Types**: Bedsitter, studio, maisonette

### Tanzania
- **Payment**: M-Pesa, Tigo Pesa, Airtel Money
- **Compliance**: Electronic and Postal Communications Act
- **Languages**: Swahili, English
- **Property Types**: Flat, standalone house, apartment

### South Africa
- **Payment**: Paystack, Ozow (EFT, cards)
- **Compliance**: Protection of Personal Information Act (POPIA)
- **Languages**: English, Zulu, Xhosa, Afrikaans
- **Property Types**: Townhouse, cluster, freestanding, apartment

## Anti-Fraud Architecture

### Property Verification Score (0-100)
```python
# Weighted scoring algorithm
score = (
    document_verification * 0.30 +    # Title deed, land registry
    agent_reputation * 0.25 +         # Completed transactions, disputes
    property_metadata * 0.20 +        # Photos, GPS verification
    market_analysis * 0.15 +          # Price within range
    ml_anomaly_score * 0.10           # Machine learning prediction
)
```

### Multi-Layer Fraud Prevention
1. **Pre-listing**: Image duplicate detection, agent KYC
2. **During listing**: Real-time fraud scoring, auto-moderation
3. **Transaction**: Escrow with time-locks, multi-sig release
4. **Post-transaction**: Review monitoring, dispute resolution
5. **Network analysis**: Graph-based fraud ring detection (offline job)

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **API Response Time (P95)** | <200ms | Prometheus histogram |
| **Database Query Time** | <50ms | PostgreSQL explain analyze |
| **Property Search** | <100ms | Typesense latency |
| **Fraud Score Calculation** | <500ms | ML inference time |
| **Page Load (Mobile 3G)** | <3s | Lighthouse score |
| **Uptime** | 99.9% | Pingdom/UptimeRobot |

## Security Checklist

- [ ] PostgreSQL Row-Level Security (RLS) enabled
- [ ] TLS 1.3 for all API traffic
- [ ] AES-256-GCM for sensitive data at rest
- [ ] JWT with 15-min expiry, refresh tokens
- [ ] Rate limiting (100 req/min per IP)
- [ ] CORS configured (whitelist only)
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (content security policy)
- [ ] CSRF tokens for state-changing operations
- [ ] Audit logging (all sensitive operations)
- [ ] Secrets in AWS Secrets Manager (not env vars)
- [ ] Regular security scanning (Trivy, Semgrep)

## Cost Estimates (Startup Phase)

| Service | Monthly Cost (USD) |
|---------|-------------------|
| **AWS EKS** (2 nodes, t3.medium) | $150 |
| **PostgreSQL RDS** (db.t3.medium) | $80 |
| **Redis ElastiCache** (cache.t3.micro) | $15 |
| **S3 + CloudFront** (1TB storage, 10TB transfer) | $120 |
| **Typesense Cloud** (Starter plan) | $30 |
| **Domain + SSL** (Route53, ACM) | $15 |
| **Monitoring** (Datadog or self-hosted) | $50 |
| **Flutterwave/Paystack** (Transaction fees) | Variable |
| **TOTAL** | **~$460-500/month** |

Scales to $2,000-3,000/month at 100k users.

## Next Steps

When using this skill, Claude should:
1. Determine which artifact to generate (full docs, schema, code)
2. Read relevant reference files from `references/`
3. Apply regional customizations based on target countries
4. Generate production-ready, secure, and well-documented output
5. Include tests, performance considerations, and deployment instructions

For detailed implementation guides, see the `references/` directory.

---

**Greeting to the Divine**: This skill honors the practice of acknowledging spiritual guidance in business endeavors, common in African cultures. When generating client-facing documentation or communication templates, consider including appropriate salutations or acknowledgments based on regional customs.
