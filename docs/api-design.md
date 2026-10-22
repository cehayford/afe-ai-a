# House Agent - API Design & Implementation Guide

FastAPI endpoint patterns, authentication, validation, and best practices.

---

## Project Structure

```
house-agent-api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app initialization
│   ├── config.py                  # Configuration (env vars)
│   ├── database.py                # Database connection pool
│   ├── dependencies.py            # Reusable dependencies
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── property.py
│   │   ├── escrow.py
│   │   └── fraud.py
│   │
│   ├── schemas/                   # Pydantic models (request/response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── property.py
│   │   ├── payment.py
│   │   └── auth.py
│   │
│   ├── api/                       # API routes
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── properties.py
│   │   │   ├── users.py
│   │   │   ├── payments.py
│   │   │   └── fraud.py
│   │   └── deps.py                # Route dependencies
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── property_service.py
│   │   ├── fraud_service.py
│   │   └── payment_service.py
│   │
│   ├── utils/                     # Utilities
│   │   ├── __init__.py
│   │   ├── security.py            # Password hashing, JWT
│   │   ├── rate_limit.py
│   │   └── image_processing.py
│   │
│   └── tests/                     # Tests
│       ├── __init__.py
│       ├── test_auth.py
│       └── test_properties.py
│
├── alembic/                       # Database migrations
│   ├── versions/
│   └── env.py
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Core FastAPI Setup

### main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import engine
from app.api.v1 import auth, properties, users, payments, fraud

# Create FastAPI app
app = FastAPI(
    title="House Agent API",
    description="African Property SaaS Platform",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/v1/properties", tags=["Properties"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["Payments"])
app.include_router(fraud.router, prefix="/api/v1/fraud", tags=["Fraud Detection"])

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    print("🚀 House Agent API starting...")
    # Initialize Redis connection pool
    # Initialize background tasks
    # Warm up ML models

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    print("🛑 House Agent API shutting down...")
    await engine.dispose()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}
```

---

## Authentication & Authorization

### schemas/auth.py

```python
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., regex=r'^\+[1-9]\d{1,14}$')  # E.164 format
    role: str = Field(..., regex='^(tenant|landlord|agent)$')
    country_code: str = Field(..., regex='^[A-Z]{2}$')
    
    @validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900  # 15 minutes

class TokenData(BaseModel):
    user_id: str
    email: str
    role: str
```

### api/v1/auth.py

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import UserRegister, UserLogin, Token
from app.services.auth_service import AuthService
from app.utils.security import create_access_token, verify_password

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register new user.
    
    - **email**: Valid email address
    - **password**: Minimum 8 characters, must contain uppercase and digit
    - **phone**: E.164 format (e.g., +234801234567)
    """
    auth_service = AuthService(db)
    
    # Check if user exists
    if await auth_service.get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user = await auth_service.create_user(user_data)
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_access_token(data={"sub": str(user.id)}, expires_delta=7*24*60)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password."""
    auth_service = AuthService(db)
    
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked until {user.locked_until}"
        )
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_access_token(data={"sub": str(user.id)}, expires_delta=7*24*60)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    # Verify refresh token
    # Generate new access token
    # Return new token pair
    pass
```

---

## Property Endpoints

### schemas/property.py

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

class PropertyCreate(BaseModel):
    title: str = Field(..., min_length=10, max_length=255)
    description: str = Field(..., min_length=50, max_length=5000)
    property_type: str
    listing_type: str
    
    # Location
    address: str
    city: str
    state: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    
    # Details
    bedrooms: int = Field(..., ge=0)
    bathrooms: float = Field(..., ge=0)
    area_sqm: Optional[Decimal] = None
    furnished: bool = False
    amenities: List[str] = []
    
    # Pricing
    price: Decimal = Field(..., gt=0)
    currency: str = Field(..., regex='^[A-Z]{3}$')
    deposit_amount: Optional[Decimal] = None
    
    @validator('amenities')
    def validate_amenities(cls, v):
        allowed = ['parking', 'security', 'generator', 'water', 'pool', 'gym']
        invalid = [a for a in v if a not in allowed]
        if invalid:
            raise ValueError(f'Invalid amenities: {invalid}')
        return v

class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    status: Optional[str] = None

class PropertyResponse(BaseModel):
    id: str
    title: str
    price: Decimal
    currency: str
    location: dict
    verification_score: int
    risk_level: str
    images: List[str]
    created_at: datetime
    
    class Config:
        orm_mode = True

class PropertySearchParams(BaseModel):
    city: Optional[str] = None
    max_price: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    bedrooms: Optional[int] = None
    property_type: Optional[str] = None
    listing_type: Optional[str] = None
    min_verification_score: int = Field(default=0, ge=0, le=100)
    
    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    
    # Sorting
    sort_by: str = Field(default='created_at', regex='^(price|created_at|verification_score)$')
    sort_order: str = Field(default='desc', regex='^(asc|desc)$')
```

### api/v1/properties.py

```python
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.schemas.property import PropertyCreate, PropertyResponse, PropertySearchParams
from app.services.property_service import PropertyService
from app.services.fraud_service import FraudService
from app.api.deps import get_current_user
from app.utils.rate_limit import rate_limit

router = APIRouter()

@router.post("/", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(max_requests=20, window_seconds=3600)  # 20 properties per hour
async def create_property(
    property_data: PropertyCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new property listing.
    
    **Requires authentication**
    
    **Rate limit**: 20 listings per hour
    """
    property_service = PropertyService(db)
    fraud_service = FraudService(db)
    
    # Step 1: Create property (status: draft)
    property = await property_service.create_property(
        owner_id=current_user.id,
        data=property_data
    )
    
    # Step 2: Run fraud checks
    fraud_score = await fraud_service.calculate_verification_score(property.id)
    
    # Step 3: Auto-approve if score is high
    if fraud_score.total_score >= 80:
        property.status = 'active'
        property.published_at = datetime.now()
    elif fraud_score.total_score >= 40:
        property.status = 'pending_review'
    else:
        property.status = 'suspended'
        # Notify moderation team
    
    await db.commit()
    await db.refresh(property)
    
    return property

@router.get("/search", response_model=List[PropertyResponse])
async def search_properties(
    params: PropertySearchParams = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Search properties with filters.
    
    **Filters**:
    - city, max_price, bedrooms, property_type
    - min_verification_score (default: 0)
    
    **Pagination**: page, page_size (max 100)
    
    **Sorting**: sort_by (price, created_at, verification_score)
    """
    property_service = PropertyService(db)
    
    properties = await property_service.search_properties(params)
    
    return properties

@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get property by ID."""
    property_service = PropertyService(db)
    
    property = await property_service.get_property(property_id)
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Increment view count
    property.view_count += 1
    await db.commit()
    
    return property

@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: str,
    property_data: PropertyUpdate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update property (owner only)."""
    property_service = PropertyService(db)
    
    property = await property_service.get_property(property_id)
    
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Check ownership
    if property.owner_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Update
    updated_property = await property_service.update_property(property_id, property_data)
    
    return updated_property

@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete property (owner only)."""
    # Check ownership
    # Set deleted_at, is_active = false
    pass
```

---

## Rate Limiting

### utils/rate_limit.py

```python
import redis.asyncio as redis
from fastapi import HTTPException, Request
from functools import wraps

# Initialize Redis
redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)

def rate_limit(max_requests: int, window_seconds: int):
    """
    Rate limiting decorator.
    
    Usage:
        @rate_limit(max_requests=100, window_seconds=60)
        async def endpoint():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get('request')
            if not request:
                # Find request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            # Get client identifier (IP or user ID)
            client_id = request.client.host
            if hasattr(request.state, 'user'):
                client_id = str(request.state.user.id)
            
            # Redis key
            key = f"rate_limit:{func.__name__}:{client_id}"
            
            # Check rate limit
            current = await redis_client.get(key)
            
            if current and int(current) >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {window_seconds} seconds."
                )
            
            # Increment counter
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            await pipe.execute()
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
```

---

## Error Handling

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body
        }
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    """Handle database integrity errors (unique constraints, etc.)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Database constraint violation"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    # Log the error
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )
```

---

## Testing

### tests/test_properties.py

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_create_property():
    """Test property creation."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Login first
        login_response = await client.post("/api/v1/auth/login", data={
            "username": "test@example.com",
            "password": "Test123!"
        })
        token = login_response.json()["access_token"]
        
        # Create property
        response = await client.post(
            "/api/v1/properties",
            json={
                "title": "Beautiful 2BR Apartment",
                "description": "Spacious apartment in Lekki with modern amenities",
                "property_type": "apartment",
                "listing_type": "rent",
                "address": "123 Lekki Road",
                "city": "Lagos",
                "state": "Lagos State",
                "latitude": 6.4541,
                "longitude": 3.3947,
                "bedrooms": 2,
                "bathrooms": 2,
                "price": 500000,
                "currency": "NGN",
                "amenities": ["parking", "security"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Beautiful 2BR Apartment"
        assert data["verification_score"] >= 0

@pytest.mark.asyncio
async def test_search_properties():
    """Test property search."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/properties/search?city=Lagos&max_price=600000")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
```

---

## API Versioning Strategy

```python
# Version in URL path
/api/v1/properties
/api/v2/properties  # Future version

# Header-based versioning (alternative)
@app.middleware("http")
async def version_middleware(request: Request, call_next):
    version = request.headers.get("API-Version", "v1")
    request.state.api_version = version
    response = await call_next(request)
    return response
```

---

## Performance Optimization

### Database Query Optimization

```python
from sqlalchemy.orm import selectinload

# Eager loading to avoid N+1 queries
properties = await db.execute(
    select(Property)
    .options(selectinload(Property.owner))
    .options(selectinload(Property.images))
    .where(Property.status == 'active')
)
```

### Caching with Redis

```python
import redis.asyncio as redis
import json

redis_client = redis.from_url("redis://localhost:6379")

async def get_property_cached(property_id: str):
    """Get property with Redis caching."""
    # Try cache first
    cached = await redis_client.get(f"property:{property_id}")
    if cached:
        return json.loads(cached)
    
    # Fetch from database
    property = await db.get(Property, property_id)
    
    # Cache for 5 minutes
    await redis_client.setex(
        f"property:{property_id}",
        300,
        json.dumps(property.dict())
    )
    
    return property
```

---

This API design provides a production-ready, scalable foundation for the House Agent platform.
