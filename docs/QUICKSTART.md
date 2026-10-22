# House Agent - Quick Start Guide

> **Stack update (STACK-001, Sept 2026):** backend = Python (FastAPI) + Rust native modules (`afe_native`, via PyO3); mobile = native Android (Kotlin + Jetpack Compose) and iOS (Swift + SwiftUI), replacing Flutter. See `Afe_Stack_Amendment_STACK-001.docx` and `Afe_Project_Statement_v3.3.docx`.

Get your African property platform running in under 30 minutes.

---

## 📋 Prerequisites

- **Python**: 3.11 or higher
- **PostgreSQL**: 15 or higher (with PostGIS extension)
- **Redis**: 7 or higher
- **Docker** (optional, for containerized setup)
- **Git**: For version control

---

## 🚀 Option 1: Docker Quick Start (Recommended)

### Step 1: Clone and Setup
```bash
# Navigate to your project directory
cd /path/to/house-agent-skill

# Copy environment template
cp deployment/.env.example .env

# Edit .env with your settings
nano .env
```

### Step 2: Start All Services
```bash
# Start PostgreSQL, Redis, FastAPI, Celery, Typesense, and monitoring
docker-compose -f deployment/docker-compose.yml up -d

# Check logs
docker-compose logs -f api
```

### Step 3: Initialize Database
```bash
# Wait for PostgreSQL to be ready (about 30 seconds)
sleep 30

# Run database initialization
docker-compose exec api python scripts/init_database.py \
  --db-url postgresql://postgres:dev_password_change_in_production@db:5432/houseagent
```

### Step 4: Access the Platform
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health
- **Prometheus Metrics**: http://localhost:9090
- **Grafana Dashboard**: http://localhost:3001 (admin/admin)

---

## 🛠️ Option 2: Manual Setup

### Step 1: Install Python Dependencies
```bash
pip install -r deployment/requirements.txt
```

### Step 2: Start PostgreSQL
```bash
# Using Docker
docker run -d \
  --name houseagent-db \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=houseagent \
  -p 5432:5432 \
  postgis/postgis:15-3.3

# Wait for startup
sleep 10
```

### Step 3: Start Redis
```bash
docker run -d \
  --name houseagent-redis \
  -p 6379:6379 \
  redis:7-alpine
```

### Step 4: Initialize Database
```bash
python scripts/init_database.py \
  --db-url postgresql://postgres:your_password@localhost:5432/houseagent
```

### Step 5: Create .env File
```bash
cp deployment/.env.example .env

# Update these critical values:
# DATABASE_URL=postgresql://postgres:your_password@localhost:5432/houseagent
# REDIS_URL=redis://localhost:6379
# SECRET_KEY=your-secret-key-min-32-chars
```

### Step 6: Run FastAPI Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📝 Generate Architecture Documentation

```bash
# Generate for Nigeria
python scripts/generate_architecture_doc.py \
  --country NG \
  --output docs/architecture-nigeria.md

# Generate for Kenya
python scripts/generate_architecture_doc.py \
  --country KE \
  --output docs/architecture-kenya.md

# Generate for Ghana
python scripts/generate_architecture_doc.py \
  --country GH \
  --output docs/architecture-ghana.md
```

---

## 🧪 Testing the API

### 1. Health Check
```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### 2. Register a User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!",
    "first_name": "John",
    "last_name": "Doe",
    "phone": "+234801234567",
    "role": "tenant",
    "country_code": "NG"
  }'
```

### 3. Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=TestPass123!"
```

**Save the access_token from the response!**

### 4. Create a Property (Requires Authentication)
```bash
curl -X POST http://localhost:8000/api/v1/properties \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Modern 2BR Apartment in Lekki",
    "description": "Spacious apartment with modern amenities, close to shopping centers",
    "property_type": "apartment",
    "listing_type": "rent",
    "address": "123 Lekki Road",
    "city": "Lagos",
    "state": "Lagos State",
    "latitude": 6.4541,
    "longitude": 3.3947,
    "bedrooms": 2,
    "bathrooms": 2,
    "area_sqm": 85,
    "price": 500000,
    "currency": "NGN",
    "amenities": ["parking", "security", "generator"]
  }'
```

### 5. Search Properties
```bash
curl "http://localhost:8000/api/v1/properties/search?city=Lagos&max_price=600000"
```

---

## 🔧 Running Fraud Detection

### 1. Test Duplicate Image Detection
```python
# In Python shell
from fraud_detection import DuplicateImageDetector
import asyncpg

# Connect to database
db_pool = await asyncpg.create_pool(
    "postgresql://postgres:password@localhost/houseagent"
)

detector = DuplicateImageDetector(db_pool)

# Compute hash for an image
image_hash = await detector.compute_image_hash("http://example.com/property.jpg")

# Find duplicates
duplicates = await detector.find_duplicates(property_id, [image_hash])
```

### 2. Test Verification Scoring
```python
from verification_scorer import VerificationScorer, PropertyData

scorer = VerificationScorer(db_pool)

property_data = PropertyData(
    property_id="uuid-123",
    owner_id="uuid-456",
    has_title_deed=True,
    title_deed_verified=True,
    gps_verified=True,
    # ... other fields
)

score = await scorer.calculate_total_score(property_data)
print(f"Verification Score: {score['total_score']}/100")
print(f"Risk Level: {score['risk_level']}")
```

---

## 📊 Database Verification

### Check Tables
```bash
# Connect to PostgreSQL
docker exec -it houseagent-db psql -U postgres -d houseagent

# List all tables
\dt

# Expected output: 26 tables
# countries, users, properties, property_images, fraud_scores, etc.
```

### Query Example
```sql
-- Count users by country
SELECT c.name, COUNT(u.id) as user_count
FROM countries c
LEFT JOIN users u ON u.country_id = c.id
GROUP BY c.name;

-- Check active properties
SELECT COUNT(*) FROM properties WHERE status = 'active';

-- View fraud scores
SELECT 
  p.title,
  fs.total_score,
  fs.risk_level
FROM properties p
JOIN fraud_scores fs ON fs.property_id = p.id
ORDER BY fs.total_score DESC;
```

---

## 🌍 Regional Configuration

### Nigeria Setup
```bash
# In .env file
DEFAULT_COUNTRY=NG
FLUTTERWAVE_SECRET_KEY=your-flutterwave-key
PAYSTACK_SECRET_KEY=your-paystack-key
```

### Kenya Setup
```bash
DEFAULT_COUNTRY=KE
MPESA_CONSUMER_KEY=your-mpesa-key
MPESA_CONSUMER_SECRET=your-mpesa-secret
```

---

## 📱 Testing Mobile Integration

### 1. Android App Setup (Kotlin)
```bash
cd mobile/android/

# API base URL lives in local.properties (not committed)
#   api.baseUrl=http://10.0.2.2:8000     # Android emulator → host machine
#   api.baseUrl=http://YOUR_IP:8000      # physical device
./gradlew :app:installDebug      # build and install on emulator/device
./gradlew testDebugUnitTest      # unit tests
```

### 1b. iOS App Setup (Swift, macOS + Xcode required)
```bash
cd mobile/ios/
open Afe.xcodeproj
# Set API_BASE_URL in Config/Debug.xcconfig
#   API_BASE_URL = http:/$()/localhost:8000   # iOS simulator
# Run the "Afe" scheme on a simulator (Cmd+R), or from the CLI:
xcodebuild test -scheme Afe -destination 'platform=iOS Simulator,name=iPhone 15'
```

### 1c. Rust native module (backend)
```bash
cd backend/
pip install maturin
maturin develop -m rust/crates/afe-py/Cargo.toml   # builds afe_native into the active venv
cargo test --manifest-path rust/Cargo.toml
pytest tests/parity/                               # Rust vs Python reference outputs
```

### 1d. Local object storage (MinIO)
```bash
docker compose up -d minio minio-init      # creates the dev buckets
# console: http://localhost:9001  (user/password from .env, default afe_dev)
# the API talks to it with S3_ENDPOINT_URL=http://minio:9000
```

### 2. Test Property Search Flow
1. Open app
2. Tap search bar
3. Enter "Lagos"
4. Apply filters (2BR, max ₦600,000)
5. View property details
6. Contact agent

---

## 🚨 Common Issues & Solutions

### Issue: "Database connection refused"
**Solution:**
```bash
# Check if PostgreSQL is running
docker ps | grep houseagent-db

# Restart PostgreSQL
docker restart houseagent-db

# Check logs
docker logs houseagent-db
```

### Issue: "ModuleNotFoundError: No module named 'fastapi'"
**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# Reinstall dependencies
pip install -r deployment/requirements.txt
```

### Issue: "Redis connection timeout"
**Solution:**
```bash
# Check Redis status
docker ps | grep houseagent-redis

# Test connection
redis-cli ping
# Expected: PONG

# Restart if needed
docker restart houseagent-redis
```

### Issue: "Fraud score calculation fails"
**Solution:**
```bash
# Train the ML model first
python -c "
import asyncio
from anomaly_detector import AnomalyDetector
import asyncpg

async def train():
    pool = await asyncpg.create_pool('postgresql://...')
    detector = AnomalyDetector()
    await detector.train(pool)

asyncio.run(train())
"
```

---

## 📈 Performance Testing

### Load Testing with Locust
```bash
# Install locust
pip install locust

# Create locustfile.py
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class PropertyUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def search_properties(self):
        self.client.get("/api/v1/properties/search?city=Lagos")
    
    @task(3)
    def view_property(self):
        self.client.get("/api/v1/properties/uuid-123")
EOF

# Run load test
locust -f locustfile.py --host=http://localhost:8000
```

Open http://localhost:8089 and start the test.

---

## 🎯 Next Steps

### 1. Deploy to Staging
```bash
# Build Docker image
docker build -t houseagent-api:staging -f deployment/Dockerfile .

# Push to registry
docker tag houseagent-api:staging your-registry/houseagent-api:staging
docker push your-registry/houseagent-api:staging

# Apply Kubernetes manifests
kubectl apply -f deployment/kubernetes.yaml
```

### 2. Set Up Monitoring
```bash
# Access Prometheus
http://localhost:9090

# Access Grafana
http://localhost:3001
# Import dashboard: deployment/grafana-dashboards/houseagent-dashboard.json
```

### 3. Configure CI/CD
- Fork repository
- Set GitHub secrets (DATABASE_URL, SECRET_KEY, etc.)
- GitHub Actions will auto-deploy on push to `main`

### 4. Launch Checklist
- [ ] Database backups configured (daily)
- [ ] SSL certificates installed
- [ ] Payment gateways tested (sandbox → production)
- [ ] Fraud detection model trained
- [ ] Monitoring alerts set up
- [ ] Privacy policy published
- [ ] Terms of service published
- [ ] First 100 beta users invited

---

## 📞 Getting Help

- **Documentation**: See `references/` directory for detailed guides
- **API Reference**: http://localhost:8000/docs
- **Architecture**: Run `scripts/generate_architecture_doc.py`
- **Naming Options**: See `references/naming-options.md`

---

## 🎉 Success!

You now have a fully functional African property platform with:
✅ FastAPI backend with fraud detection  
✅ PostgreSQL with 26 tables and PostGIS  
✅ Redis caching and Celery background jobs  
✅ Complete API documentation  
✅ Docker containerization  
✅ Kubernetes deployment configs  
✅ Monitoring with Prometheus + Grafana  

**Start building amazing features for the African property market!**
