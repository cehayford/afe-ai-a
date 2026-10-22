# House Agent - Complete Technical Documentation Package

**Project**: African Property SaaS Platform  
**Target Markets**: Nigeria, Ghana, Kenya, Tanzania, South Africa  
**Tech Stack**: FastAPI (Python) + Rust native modules, PostgreSQL, Redis, Typesense, SvelteKit (web), Kotlin (Android), Swift (iOS)  
**Version**: 1.0.0

> **Stack update (STACK-001, Sept 2026):** backend = Python (FastAPI) + Rust native modules (`afe_native`, via PyO3); mobile = native Android (Kotlin + Jetpack Compose) and iOS (Swift + SwiftUI), replacing Flutter. See `Afe_Stack_Amendment_STACK-001.docx` and `Afe_Project_Statement_v3.3.docx`.

---

## 📦 Package Contents

This package contains everything needed to build, deploy, and scale the House Agent property platform.

### 1. Core Skill (`SKILL.md`)
The main skill file that Claude uses to automatically generate architecture, code, and documentation for the House Agent platform. Includes:
- When to trigger this skill
- Regional configurations (per-country settings)
- Anti-fraud architecture patterns
- Multi-tenant design principles

### 2. Technical References (`references/`)

#### Architecture & Infrastructure
- **`framework-comparison.md`** - Why FastAPI was chosen over Go/Java/Node.js
- **`database-schema.md`** - Complete PostgreSQL schema with 26 tables, indexes, and RLS
- **`api-design.md`** - FastAPI endpoint patterns, authentication, validation
- **`page-structure.md`** - Complete sitemap for web, mobile, and admin interfaces

#### Security & Anti-Fraud
- **`fraud-detection.md`** - Production-ready Python algorithms:
  - Duplicate image detection (perceptual hashing)
  - Property verification scoring (weighted algorithm)
  - ML anomaly detection (Isolation Forest)
  - Graph-based fraud ring detection
  
#### Business
- **`naming-options.md`** - 45+ naming options across 3 categories (Descriptive, Cultural, Humor)

### 3. Executable Scripts (`scripts/`)

#### `generate_architecture_doc.py`
**Purpose**: Auto-generate comprehensive architecture documentation  
**Usage**:
```bash
python generate_architecture_doc.py --output architecture.md --country NG
```
**Outputs**: Complete markdown document with:
- Tech stack overview
- Regional configuration (payments, compliance, languages)
- System architecture diagrams (ASCII art)
- Data flow diagrams
- Security architecture
- Deployment guide
- Cost estimates
- API reference

**Options**:
- `--country`: NG (Nigeria), GH (Ghana), KE (Kenya), TZ (Tanzania), ZA (South Africa)
- `--output`: Output file path (default: architecture.md)

---

#### `init_database.py`
**Purpose**: Initialize PostgreSQL database with complete schema  
**Usage**:
```bash
python init_database.py --db-url postgresql://user:pass@localhost/houseagent
```
**What it creates**:
- All 26 tables (users, properties, escrow, fraud detection, audit logs)
- PostGIS extension for geospatial queries
- Row-level security policies (multi-tenancy)
- Indexes (B-tree, GiST, GIN)
- Triggers (auto-update timestamps, audit logging)
- Seed data (5 African countries with payment/compliance config)

**Requirements**:
```bash
pip install asyncpg
```

---

#### `fraud_detection.py` (in fraud-detection.md)
**Purpose**: Production-ready fraud detection algorithms  
**Modules**:
1. **DuplicateImageDetector** - Perceptual hashing to find duplicate listings
2. **VerificationScorer** - Calculate 0-100 trust score for properties
3. **AnomalyDetector** - ML-based anomaly detection (Isolation Forest)
4. **FraudRingDetector** - Graph analysis to find coordinated scam networks

**Usage Example**:
```python
from fraud_detection import DuplicateImageDetector, VerificationScorer

# Check for duplicate images
detector = DuplicateImageDetector(db_pool)
image_hashes = await detector.compute_image_hash(image_url)
duplicates = await detector.find_duplicates(property_id, image_hashes)

# Calculate verification score
scorer = VerificationScorer(db_pool)
score_data = await scorer.calculate_total_score(property_data)
# Returns: {total_score: 85, risk_level: 'LOW', component_scores: {...}}
```

---

## 🚀 Quick Start Guide

### Step 1: Generate Architecture Documentation
```bash
cd scripts/
python generate_architecture_doc.py --country NG --output ../architecture-nigeria.md
```

### Step 2: Set Up Database
```bash
# Start PostgreSQL (Docker)
docker run -d \
  --name houseagent-db \
  -e POSTGRES_PASSWORD=secretpass \
  -e POSTGRES_DB=houseagent \
  -p 5432:5432 \
  postgis/postgis:15-3.3

# Initialize schema
python init_database.py --db-url postgresql://postgres:secretpass@localhost/houseagent
```

### Step 3: Install Python Dependencies
```bash
pip install --break-system-packages \
  fastapi==0.104.1 \
  uvicorn==0.24.0 \
  asyncpg==0.29.0 \
  pydantic==2.5.0 \
  scikit-learn==1.3.2 \
  imagehash==4.3.1 \
  networkx==3.2.1
```

### Step 4: Run FastAPI Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000/docs for interactive API documentation

---

## 📊 Database Schema Overview

**26 Tables** organized into:

### Core Tables (6)
- `countries` - Multi-tenant root (NG, GH, KE, TZ, ZA)
- `users` - Tenants, landlords, agents, admins
- `properties` - Property listings with geospatial data
- `property_images` - Separate table for perceptual hash duplicate detection
- `inquiries` - Lead tracking
- `favorites` - User wishlists

### Anti-Fraud Tables (8)
- `fraud_scores` - Verification scores (0-100) per property
- `duplicate_detections` - Image/text similarity matches
- `fraud_reports` - User-submitted fraud reports
- `user_behaviors` - Behavioral analytics (anomaly detection)
- `fraud_networks` - Graph-based fraud ring detection
- `escrow_transactions` - Time-locked payments
- `payment_transactions` - Full audit trail
- `rate_limits` - API rate limiting & DDoS prevention

### Audit Tables (3)
- `audit_logs` - Compliance audit trail (7-year retention)
- Partitioned by month for performance

### Key Features
✅ **PostGIS** for geospatial queries ("properties within 5km")  
✅ **Row-Level Security** for multi-tenant data isolation  
✅ **Full-text search** (pg_trgm) with typo tolerance  
✅ **Perceptual hashing** (phash) for duplicate image detection  
✅ **Triggers** for auto-updating timestamps and audit logs  

---

## 🔐 Fraud Detection Algorithms

### 1. Duplicate Image Detection
**Algorithm**: Perceptual hashing (pHash)  
**How it works**:
1. Resize image to 32x32
2. Convert to grayscale
3. Apply DCT (Discrete Cosine Transform)
4. Generate 64-bit hash
5. Compare hashes using Hamming distance

**Performance**: <500ms per image  
**Accuracy**: Detects duplicates even after resizing, compression, cropping

**Use case**: Scammers posting same property multiple times

---

### 2. Property Verification Score
**Algorithm**: Weighted scoring (0-100)  
**Components**:
- Document verification (30%): Title deed, land registry match
- Agent reputation (25%): Completed transactions, dispute count
- Property metadata (20%): Photos, GPS, description quality
- Market analysis (15%): Price within market range
- ML anomaly (10%): Isolation Forest prediction

**Example Output**:
```json
{
  "total_score": 85,
  "risk_level": "LOW",
  "component_scores": {
    "document_score": 90,
    "agent_reputation_score": 88,
    "property_metadata_score": 75,
    "market_analysis_score": 90,
    "ml_anomaly_score": 82
  },
  "active_flags": []
}
```

**Actions**:
- Score ≥80: Auto-approve
- Score 40-79: Manual review
- Score <40: Auto-suspend + notify moderator

---

### 3. ML Anomaly Detection
**Algorithm**: Isolation Forest (unsupervised learning)  
**Features** (8):
- Price per sqm
- Listing duration
- Seller account age
- Photo count
- Description length
- Response time
- GPS deviation
- Price deviation from market

**Output**: Anomaly score (-1 to 1)
- <-0.5: High risk
- -0.5 to 0: Medium risk
- >0: Low risk

**Retraining**: Weekly on last 6 months of data

---

### 4. Fraud Ring Detection
**Algorithm**: Graph-based network analysis  
**Nodes**: Users  
**Edges**: Shared attributes (IP, device, bank account)

**Detection Methods**:
1. **Connected Components**: Find groups of related users
2. **Circular Transactions**: Detect money laundering (A→B→C→A)
3. **Hub-and-Spoke**: One account receiving from many (scam hub)
4. **Clustering Coefficient**: Measure network density

**Example**:
```
Network #7: 12 members
- Shared 3 IP addresses
- Shared 5 device fingerprints
- Network density: 0.85 (very suspicious)
- Action: Flag for investigation
```

---

## 🌍 Regional Configuration

### Nigeria (NG)
- **Currency**: NGN (Naira)
- **Payments**: Paystack, Flutterwave
- **Compliance**: NDPR (Nigeria Data Protection Regulation)
- **Languages**: English, Yoruba, Igbo, Hausa
- **Property Types**: Bungalow, Duplex, Terrace, Flat

### Ghana (GH)
- **Currency**: GHS (Cedi)
- **Payments**: Flutterwave, Paystack
- **Compliance**: Data Protection Act 2012
- **Languages**: English, Twi, Ga, Ewe
- **Property Types**: Chamber and Hall, Self-contained, Compound House

### Kenya (KE)
- **Currency**: KES (Shilling)
- **Payments**: M-Pesa, Flutterwave
- **Compliance**: Data Protection Act 2019
- **Languages**: English, Swahili
- **Property Types**: Bedsitter, Studio, Maisonette

### Tanzania (TZ)
- **Currency**: TZS (Shilling)
- **Payments**: M-Pesa, Tigo Pesa, Airtel Money
- **Compliance**: Electronic and Postal Communications Act
- **Languages**: Swahili, English
- **Property Types**: Flat, Standalone House, Apartment

### South Africa (ZA)
- **Currency**: ZAR (Rand)
- **Payments**: Paystack, Ozow
- **Compliance**: POPIA (Protection of Personal Information Act)
- **Languages**: English, Zulu, Xhosa, Afrikaans
- **Property Types**: Townhouse, Cluster, Freestanding, Apartment

---

## 💰 Cost Estimates

### Infrastructure (Monthly)

**Startup Phase** (0-10k users):
- AWS EKS + EC2: $150
- PostgreSQL RDS: $180
- Redis ElastiCache: $45
- S3 + CloudFront: $120
- Monitoring: $75
- **Total: ~$570/month**

**Growth Phase** (50k-100k users):
- AWS EKS + EC2: $500
- PostgreSQL RDS (upgraded): $400
- Redis ElastiCache: $100
- S3 + CloudFront: $300
- Monitoring: $150
- **Total: ~$1,450/month**

**Scale Phase** (500k-1M users):
- Multi-region deployment
- Microservices architecture
- **Total: ~$8,000-12,000/month**

### Variable Costs
- **Payment gateway**: 1.5-2% per transaction (Flutterwave/Paystack)
- **SMS**: $0.01-0.05 per message
- **Email**: $0.0001 per email (AWS SES)

---

## 📱 Platform Components

### Web Application
- **Framework**: SvelteKit (SSR, PWA)
- **Features**: 
  - Property search with filters
  - Real-time messaging (WebSocket)
  - Escrow payment flow
  - Agent dashboard with analytics

### Mobile Applications
- **Android**: Kotlin + Jetpack Compose (Android 8.0+)
- **iOS**: Swift + SwiftUI (iOS 16+, pending decision D13)
- **Shared**: API clients generated from the FastAPI OpenAPI spec; shared design tokens
- **Features**:
  - Offline-first architecture
  - GPS property verification
  - Push notifications
  - In-app messaging

### Admin Dashboard
- **Framework**: Admin role inside the SvelteKit app (replaces Django Admin)
- **Features**:
  - User management
  - Property moderation
  - Fraud detection review
  - Analytics & reporting

---

## 🔒 Security Features

### Authentication
- OAuth 2.0 + JWT (15-min expiry)
- Refresh tokens (7-day expiry, single-use)
- Two-factor authentication (TOTP)
- Device fingerprinting
- Rate limiting (5 login attempts per 15 min)

### Data Encryption
- **At Rest**: AES-256-GCM (PostgreSQL TDE)
- **In Transit**: TLS 1.3 with perfect forward secrecy
- **Application**: ChaCha20-Poly1305 for sensitive fields

### Compliance
- GDPR/NDPR compliant
- Data retention: 7 years (financial), 90 days (logs)
- Right to erasure: 30-day processing
- Data breach notification: 72 hours

---

## 📚 Additional Resources

### API Documentation
- Auto-generated: http://localhost:8000/docs (Swagger UI)
- ReDoc: http://localhost:8000/redoc

### Monitoring
- Prometheus metrics: http://localhost:8000/metrics
- Health check: http://localhost:8000/health

### Support
- Documentation: https://docs.houseagent.com
- Support: support@houseagent.com
- Status page: https://status.houseagent.com

---

## 🛠️ Development Workflow

### 1. Create Feature Branch
```bash
git checkout -b feature/property-search
```

### 2. Write Tests
```python
# tests/test_properties.py
@pytest.mark.asyncio
async def test_search_properties():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/properties/search?city=Lagos")
        assert response.status_code == 200
```

### 3. Run Tests
```bash
pytest tests/ -v
```

### 4. Create Pull Request
- GitHub Actions runs: tests, linting, security scan
- ArgoCD deploys to staging on merge to `develop`
- Production deployment on merge to `main`

---

## 📈 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| API Response Time (P95) | <200ms | Prometheus |
| Database Query Time | <50ms | PostgreSQL explain |
| Property Search | <100ms | Typesense |
| Fraud Score Calculation | <500ms | Custom timer |
| Page Load (Mobile 3G) | <3s | Lighthouse |
| Uptime | 99.9% | UptimeRobot |

---

## 🎯 Next Steps

### Phase 1: MVP (Weeks 1-6)
- [ ] Set up infrastructure (AWS, PostgreSQL, Redis)
- [ ] Implement authentication & user management
- [ ] Build property listing & search
- [ ] Integrate fraud detection (duplicate checking)
- [ ] Deploy to staging

### Phase 2: Beta (Weeks 7-12)
- [ ] Escrow payment integration (Flutterwave)
- [ ] Android app (Kotlin) — first
- [ ] iOS app (Swift)
- [ ] Rust native module (`afe_native`): photo hashing, image processing, scoring
- [ ] S3 buckets, presigned uploads, quarantine + malware scan pipeline
- [ ] Backups: PITR, cross-region and cross-account copies, quarterly restore drill
- [ ] Monetization: escrow fee, agent subscriptions (see `Afe_Unit_Economics_Model.xlsx` and Statement Section 12)
- [ ] Admin dashboard
- [ ] ML fraud detection (train model)
- [ ] Beta testing (100 users)

### Phase 3: Launch (Weeks 13-16)
- [ ] Performance optimization
- [ ] Security audit
- [ ] Launch in Nigeria (Lagos)
- [ ] Marketing campaign
- [ ] Monitor metrics

---

## 📞 Contact

**Project**: House Agent  
**Version**: 1.0.0  
**Last Updated**: 2024

For questions or support regarding this documentation package, please refer to the individual reference files in the `references/` directory.

---

**🎉 You now have everything needed to build a production-ready African property platform with built-in fraud prevention!**
