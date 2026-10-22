# House Agent - Backend Framework Selection

**Decision: FastAPI (Python) is the recommended framework**

## Executive Summary

For the House Agent property platform targeting East/West African markets, **FastAPI** provides the optimal balance of:
- **Developer availability**: 10x more Python developers than Go in target markets
- **Rapid development**: 2-3x faster MVP delivery than Java Spring
- **Performance**: Handles 10k+ concurrent users with proper architecture
- **Ecosystem**: Native ML/fraud detection libraries (scikit-learn, TensorFlow)
- **Cost efficiency**: Lower salary costs, faster time-to-market

---

## Framework Comparison Matrix

### Performance Benchmarks

| Framework | Requests/sec | Latency (P95) | Memory Usage | Startup Time |
|-----------|-------------|---------------|--------------|--------------|
| **FastAPI (Python)** | 20,000-30,000 | 15-25ms | 150-250 MB | <1s |
| **Go (Gin/Echo)** | 50,000-70,000 | 5-10ms | 20-50 MB | <100ms |
| **Java (Spring Boot)** | 15,000-25,000 | 20-40ms | 400-800 MB | 5-10s |
| **Node.js (Express)** | 15,000-20,000 | 20-30ms | 100-200 MB | <1s |

**Verdict**: FastAPI is 80% of Go's performance but 3x faster to develop. For a startup, speed-to-market > raw throughput.

---

## Detailed Framework Analysis

### 1. FastAPI (Python) ⭐ **RECOMMENDED**

#### Strengths
✅ **Async I/O**: Native asyncio support (comparable to Node.js/Go)
✅ **Type Safety**: Pydantic models catch bugs at development time
✅ **Auto Documentation**: OpenAPI/Swagger UI generated automatically
✅ **ML Ecosystem**: scikit-learn, TensorFlow, pandas, numpy (native)
✅ **Developer Pool**: Largest pool of available developers in Africa
✅ **Rapid Prototyping**: 2-3x faster MVP development than Java
✅ **Modern**: Built on Python 3.7+ with type hints

#### Weaknesses
❌ **Lower Raw Performance**: 40-50% slower than Go/C++
❌ **GIL Limitation**: CPU-bound tasks need multiprocessing
❌ **Deployment Size**: Larger Docker images (~200-300MB vs Go's 20MB)

#### Code Example
```python
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, validator
from typing import List, Optional
import asyncpg

app = FastAPI(title="House Agent API")

class PropertyCreate(BaseModel):
    title: str
    price: float
    location: dict
    
    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be positive')
        return v

@app.post("/api/properties", response_model=Property)
async def create_property(
    property: PropertyCreate,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    # Fraud check
    fraud_score = await check_fraud_score(property)
    if fraud_score < 40:
        raise HTTPException(status_code=400, detail="Property flagged for fraud")
    
    # Insert into DB
    async with db.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO properties (title, price, location)
            VALUES ($1, $2, $3)
            RETURNING *
        """, property.title, property.price, property.location)
    
    return result
```

#### Deployment
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

#### Scaling Strategy
1. **Horizontal**: Run multiple Uvicorn workers behind Nginx/Traefik
2. **Async**: Use asyncpg, aiohttp for non-blocking I/O
3. **Caching**: Redis for hot data (property listings, user sessions)
4. **Background Jobs**: Celery for heavy tasks (image processing, fraud analysis)

---

### 2. Go (Gin/Echo) - **Second Choice**

#### Strengths
✅ **Raw Performance**: 2-3x faster than FastAPI
✅ **Lightweight**: 20MB Docker images, 50MB RAM
✅ **Concurrency**: Goroutines handle 100k+ concurrent connections
✅ **Type Safety**: Compiled language catches all errors
✅ **Single Binary**: Easy deployment (no dependencies)

#### Weaknesses
❌ **Talent Pool**: 10x fewer Go developers in Nigeria/Ghana/Kenya
❌ **Higher Salaries**: Go devs command 30-50% premium
❌ **Slower Development**: Verbose error handling, no REPL
❌ **ML Ecosystem**: Limited (need to call Python services for fraud detection)
❌ **Learning Curve**: Steeper for junior developers

#### When to Choose Go
- You have 100k+ concurrent users (not typical for MVP/Series A)
- You need <10ms API latency
- You have experienced Go developers on team
- ML/fraud detection is handled by separate service

---

### 3. Java (Spring Boot) - **Not Recommended**

#### Strengths
✅ **Enterprise Ecosystem**: Mature libraries, tooling
✅ **Strong Typing**: Compile-time error checking
✅ **Performance**: On par with FastAPI after JVM warmup
✅ **Developer Pool**: Large pool of Java devs globally

#### Weaknesses
❌ **Slow Startup**: 5-10s startup time (bad for serverless/autoscaling)
❌ **Memory Hungry**: 400-800MB per instance
❌ **Verbose**: 3-5x more boilerplate than Python/Go
❌ **Slow Development**: Longer iteration cycles
❌ **Heavyweight**: Overkill for API-first startup

#### Verdict
Spring Boot is excellent for enterprises with existing Java teams, but for a startup building an MVP, the development speed penalty is too high.

---

### 4. Node.js (Express/NestJS) - **Not Recommended**

#### Strengths
✅ **JavaScript Everywhere**: Same language frontend/backend
✅ **Async by Default**: Event loop handles concurrency well
✅ **NPM Ecosystem**: Massive package library
✅ **Developer Pool**: Large pool of JS developers

#### Weaknesses
❌ **Weak Typing**: TypeScript helps but still runtime issues
❌ **Callback Hell**: Complex async code gets messy
❌ **Security Issues**: npm packages have high vulnerability rate
❌ **ML Ecosystem**: Limited (would need Python microservices)
❌ **Single-Threaded**: CPU-bound tasks block event loop

#### Verdict
Node.js works for simple CRUD APIs, but for complex business logic with fraud detection, type safety becomes critical. FastAPI provides better guarantees.

---

## Why FastAPI Wins for House Agent

### 1. **Fraud Detection is Native**
```python
# All in one language
from sklearn.ensemble import IsolationForest
import imagehash
from PIL import Image

# No need for microservices or gRPC calls
fraud_model = IsolationForest()
fraud_model.fit(training_data)

score = fraud_model.predict(new_listing_features)
```

With Go/Java/Node, you'd need:
- Separate Python service for ML
- gRPC/REST communication overhead
- Data serialization complexity
- Additional infrastructure costs

### 2. **Developer Availability in Africa**

**Lagos, Nigeria (Tech Hub)**:
- Python developers: ~5,000+ (bootcamps, universities)
- Go developers: ~300-500
- Java developers: ~2,000 (mostly enterprise)

**Nairobi, Kenya**:
- Python developers: ~3,000+
- Go developers: ~200-300
- Java developers: ~1,500

**Salary Comparison** (Lagos, mid-level):
- Python: $24k-36k/year
- Go: $36k-48k/year
- Java: $30k-42k/year

**Hiring Time**:
- Python: 2-4 weeks
- Go: 2-3 months
- Java: 4-6 weeks

### 3. **Development Velocity**

**Time to MVP (Property listing + search + fraud detection)**:
- FastAPI: 4-6 weeks
- Go: 8-12 weeks
- Spring Boot: 10-14 weeks
- Node.js: 6-8 weeks

**Why FastAPI is faster**:
- Auto-generated API docs (no manual Swagger)
- Pydantic handles validation (no manual checks)
- SQLAlchemy ORM (vs manual SQL in Go)
- Rich ecosystem (no building from scratch)

### 4. **Total Cost of Ownership (Year 1)**

| Cost Category | FastAPI | Go | Spring Boot |
|--------------|---------|-----|-------------|
| **Developer Salaries** (3 devs) | $90k | $120k | $105k |
| **Infrastructure** | $6k | $4k | $8k |
| **Time to Market** (opp. cost) | - | -$50k | -$70k |
| **Training/Onboarding** | $2k | $10k | $5k |
| **TOTAL** | **$98k** | **$184k** | **$188k** |

FastAPI saves **~$86k-90k in Year 1** due to faster development and lower salaries.

---

## Performance Reality Check

### "But Go is 3x faster!"

**True for CPU-bound workloads**. But House Agent is **I/O-bound**:
- Database queries: 20-50ms
- External APIs (payment gateways): 100-500ms
- Image processing: 200-1000ms (offloaded to Celery)

**Bottlenecks**:
1. ❌ NOT Python interpreter
2. ✅ Database query optimization
3. ✅ Network latency (Africa → AWS)
4. ✅ Caching strategy

**With proper architecture** (async, caching, DB indexes):
- FastAPI: Handles 50k daily active users
- Go: Handles 200k daily active users

For a startup, you'll hit product-market fit long before you hit FastAPI's performance ceiling.

### When to Migrate to Go

**Trigger**: >100k concurrent users and profiling shows Python as bottleneck (unlikely)

**Strategy**: Microservices migration
1. Keep FastAPI for business logic APIs
2. Move hot paths to Go (e.g., real-time property feed)
3. Use gRPC for inter-service communication

---

## Recommended Tech Stack

```
┌─────────────────────────────────────────┐
│            Frontend Layer                │
├─────────────────────────────────────────┤
│  Android: Kotlin + Jetpack Compose      │
│  iOS: Swift + SwiftUI                   │
│  Web: SvelteKit (SSR + PWA)             │
│  Admin: SvelteKit admin role            │
└─────────────────────────────────────────┘
                  ↓ HTTPS
┌─────────────────────────────────────────┐
│         API Gateway / CDN                │
├─────────────────────────────────────────┤
│  CloudFront (global CDN)                │
│  AWS ALB (load balancer)                │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      Backend: FastAPI (Python)          │
├─────────────────────────────────────────┤
│  • REST API (Pydantic validation)       │
│  • GraphQL (Strawberry)                 │
│  • WebSockets (real-time updates)       │
│  • JWT Auth (OAuth 2.0)                 │
└─────────────────────────────────────────┘
         ↓              ↓              ↓
┌─────────────┐  ┌──────────────┐  ┌──────────┐
│ PostgreSQL  │  │    Redis     │  │ Celery   │
│  (PostGIS)  │  │  (Cache +    │  │ Workers  │
│             │  │   Sessions)  │  │          │
└─────────────┘  └──────────────┘  └──────────┘
```

### Dependencies (requirements.txt)

```txt
# Web Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic[email]==2.5.0
python-multipart==0.0.6

# Database
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.23
alembic==1.12.1

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6

# Validation & Serialization
pydantic-settings==2.1.0
email-validator==2.1.0

# Caching & Sessions
redis==5.0.1
hiredis==2.2.3

# Background Jobs
celery[redis]==5.3.4

# Fraud Detection
scikit-learn==1.3.2
numpy==1.26.2
scipy==1.11.4
imagehash==4.3.1
pillow==10.1.0
networkx==3.2.1

# Payment Integrations
httpx==0.25.2
aiohttp==3.9.1

# Monitoring & Logging
prometheus-client==0.19.0
python-json-logger==2.0.7

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2  # For testing API
```

---

## Migration Path (If Needed)

### Phase 1: MVP (FastAPI)
- Build entire platform in FastAPI
- Validate product-market fit
- Optimize with caching, DB indexes

### Phase 2: Scaling (FastAPI + Go microservices)
- Identify bottlenecks via profiling
- Extract hot paths to Go services
- Keep business logic in FastAPI

### Phase 3: Enterprise (Hybrid)
- FastAPI: Business logic, fraud detection
- Go: Real-time feeds, WebSocket servers
- gRPC for inter-service communication

---

## Decision Summary

| Criteria | Weight | FastAPI | Go | Spring Boot |
|----------|--------|---------|-----|-------------|
| **Developer Availability** | 25% | 10 | 4 | 7 |
| **Development Speed** | 25% | 10 | 6 | 5 |
| **Performance** | 15% | 7 | 10 | 7 |
| **ML/Fraud Ecosystem** | 20% | 10 | 3 | 5 |
| **Cost** | 15% | 10 | 6 | 6 |
| **TOTAL** | 100% | **9.35** | **5.75** | **5.95** |

## Final Recommendation

**Use FastAPI (Python) for House Agent backend**

**Rationale**:
1. Fastest time to market (4-6 weeks to MVP)
2. Largest developer pool in target markets
3. Native fraud detection (no microservices needed)
4. Sufficient performance for 0-100k users
5. Lowest total cost of ownership

**Update (STACK-001, Sept 2026)**: hot paths go to **Rust**, not Go. Rust is compiled into the Python app with PyO3 (`afe_native`) for photo hashing, image processing and scoring, so there is still one deployable API. Standalone Rust (Axum) services are an R2 option if load tests call for them. See the addendum at the end of this file.

**When to reconsider**: If you hit 100k+ concurrent users and Python becomes the bottleneck (unlikely in first 2-3 years). At that point, migrate hot paths to Go while keeping business logic in FastAPI.

---

## Next Steps

1. ✅ FastAPI backend selected
2. → Set up project structure (see project-structure.md)
3. → Design API endpoints (see api-design.md)
4. → Implement database migrations (Alembic)
5. → Deploy to AWS EKS with auto-scaling


---

## Addendum — Python + Rust (STACK-001, September 2026)

| Criterion | Python only | Python + Rust (chosen) | Python + Go (previous plan) |
|---|---|---|---|
| Deployment | One service | One service (Rust built into a Python wheel) | Extra services + gRPC |
| CPU-heavy work (hashing, imaging) | Slow, holds the GIL | Fast, releases the GIL | Fast, but needs a network hop |
| Hiring in Ghana | Easy | Harder for the Rust part | Moderate |
| Memory safety | Yes | Yes | Yes |

**Rules**
1. Rust only for pure, CPU-bound functions with shared test fixtures.
2. Python keeps business logic, config (weights, thresholds) and all database writes.
3. The old Python implementations stay as reference code; CI runs parity tests.

**Rust in Release 1:** `phash`, `dhash`, `hamming_matches`, `normalise_image`, `verification_score`, `checkin_score`, `price_outlier`.
**Stays Python:** Isolation Forest, XGBoost, LightFM, NLP, networkx graph jobs (Rust `petgraph` only if they become too slow).
