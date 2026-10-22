# House Agent - Complete Database Schema

Production-ready PostgreSQL schema with multi-tenancy, anti-fraud tables, geospatial support, and audit logging.

## Schema Overview

```
Core Tables: 15
Anti-Fraud Tables: 8
Audit Tables: 3
Total Tables: 26
Estimated DB Size (100k users): ~50-100 GB
```

## Extensions Required

```sql
-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "postgis";        -- Geospatial queries
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- Encryption functions
CREATE EXTENSION IF NOT EXISTS "btree_gist";     -- Advanced indexing
```

## Enums

```sql
-- Property status lifecycle
CREATE TYPE property_status AS ENUM (
    'draft',           -- Being created
    'pending_review',  -- Awaiting moderation
    'active',          -- Published and searchable
    'rented',          -- Successfully rented/sold
    'suspended',       -- Flagged for fraud
    'deleted'          -- Soft delete
);

-- Property types vary by country
CREATE TYPE property_type AS ENUM (
    -- Nigeria
    'bungalow', 'duplex', 'terrace', 'flat', 'detached', 'semi_detached',
    -- Ghana
    'chamber_and_hall', 'self_contained', 'compound_house',
    -- Kenya/Tanzania
    'bedsitter', 'studio', 'maisonette',
    -- South Africa
    'townhouse', 'cluster', 'freestanding',
    -- Universal
    'apartment', 'commercial', 'land', 'warehouse', 'office'
);

-- Rental vs sale
CREATE TYPE listing_type AS ENUM ('rent', 'sale', 'lease', 'short_term');

-- User roles with permissions
CREATE TYPE user_role AS ENUM (
    'tenant',           -- Looking for property
    'landlord',         -- Property owner
    'agent',            -- Real estate agent
    'property_manager', -- Manages multiple properties
    'admin',            -- Platform administrator
    'moderator'         -- Content reviewer
);

-- Verification status for KYC
CREATE TYPE verification_status AS ENUM (
    'unverified',      -- Default state
    'pending',         -- Documents submitted
    'verified',        -- Approved
    'rejected',        -- Failed verification
    'suspended'        -- Fraud detected
);

-- Payment statuses
CREATE TYPE payment_status AS ENUM (
    'pending',         -- Initiated
    'processing',      -- Gateway processing
    'completed',       -- Success
    'failed',          -- Payment failed
    'refunded',        -- Money returned
    'disputed'         -- Under investigation
);

-- Escrow release conditions
CREATE TYPE escrow_condition AS ENUM (
    'listing_verified',      -- Property docs checked
    'inspection_completed',  -- Physical inspection done
    'keys_handed_over',      -- Tenant has keys
    'move_in_confirmed',     -- Tenant confirms move-in
    'dispute_resolved'       -- Arbitration complete
);

-- Fraud report categories
CREATE TYPE fraud_category AS ENUM (
    'duplicate_listing',     -- Same property posted multiple times
    'fake_photos',           -- Stolen/misrepresented images
    'price_scam',            -- Unrealistic pricing
    'fake_agent',            -- Impersonation
    'non_existent_property', -- Property doesn't exist
    'unauthorized_listing',  -- Not property owner
    'payment_fraud',         -- Fake payment requests
    'identity_theft'         -- Stolen credentials
);
```

---

## Core Tables

### 1. Countries (Multi-Tenancy Root)

```sql
CREATE TABLE countries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(2) UNIQUE NOT NULL,  -- ISO 3166-1 alpha-2 (NG, GH, KE, etc.)
    name VARCHAR(100) NOT NULL,
    currency_code VARCHAR(3) NOT NULL, -- NGN, GHS, KES, etc.
    timezone VARCHAR(50) NOT NULL,     -- Africa/Lagos, Africa/Nairobi
    languages JSONB NOT NULL,          -- ["en", "yo", "ig"] for Nigeria
    
    -- Payment gateways available in this country
    payment_providers JSONB NOT NULL,  -- {"flutterwave": true, "paystack": true, "mpesa": false}
    
    -- Compliance settings
    data_residency_required BOOLEAN DEFAULT false,
    gdpr_applicable BOOLEAN DEFAULT false,
    
    -- Platform settings
    commission_rate DECIMAL(5,2) DEFAULT 3.5,  -- Platform fee %
    is_active BOOLEAN DEFAULT true,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed data
INSERT INTO countries (code, name, currency_code, timezone, languages, payment_providers) VALUES
('NG', 'Nigeria', 'NGN', 'Africa/Lagos', '["en", "yo", "ig", "ha"]', '{"flutterwave": true, "paystack": true}'),
('GH', 'Ghana', 'GHS', 'Africa/Accra', '["en", "tw", "ga"]', '{"flutterwave": true, "paystack": true}'),
('KE', 'Kenya', 'KES', 'Africa/Nairobi', '["en", "sw"]', '{"flutterwave": true, "mpesa": true}'),
('TZ', 'Tanzania', 'TZS', 'Africa/Dar_es_Salaam', '["sw", "en"]', '{"flutterwave": true, "mpesa": true}'),
('ZA', 'South Africa', 'ZAR', 'Africa/Johannesburg', '["en", "zu", "xh", "af"]', '{"paystack": true, "ozow": true}');
```

### 2. Users (Multi-Tenant)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_id UUID NOT NULL REFERENCES countries(id),
    
    -- Authentication
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,  -- E.164 format: +234801234567
    password_hash VARCHAR(255) NOT NULL, -- bcrypt
    
    -- Profile
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role user_role NOT NULL DEFAULT 'tenant',
    avatar_url TEXT,
    
    -- KYC (Know Your Customer)
    verification_status verification_status DEFAULT 'unverified',
    id_document_url TEXT,              -- National ID, passport
    id_verified_at TIMESTAMPTZ,
    
    -- Security
    two_factor_enabled BOOLEAN DEFAULT false,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,
    
    -- Device fingerprinting (for fraud detection)
    device_fingerprints JSONB DEFAULT '[]',  -- [{device_id, user_agent, first_seen}]
    
    -- Reputation (for agents/landlords)
    reputation_score INT DEFAULT 50 CHECK (reputation_score BETWEEN 0 AND 100),
    completed_transactions INT DEFAULT 0,
    dispute_count INT DEFAULT 0,
    
    -- Soft delete
    is_active BOOLEAN DEFAULT true,
    deleted_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_country ON users(country_id) WHERE is_active = true;
CREATE INDEX idx_users_email ON users(email) WHERE is_active = true;
CREATE INDEX idx_users_phone ON users(phone) WHERE is_active = true;
CREATE INDEX idx_users_role ON users(role) WHERE is_active = true;
CREATE INDEX idx_users_verification ON users(verification_status);

-- Row-level security (multi-tenancy isolation)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY country_isolation ON users
    USING (country_id::TEXT = current_setting('app.current_country_id', TRUE));
```

### 3. Properties (Core Entity)

```sql
CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_id UUID NOT NULL REFERENCES countries(id),
    owner_id UUID NOT NULL REFERENCES users(id),
    
    -- Basic info
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    property_type property_type NOT NULL,
    listing_type listing_type NOT NULL,
    
    -- Location (PostGIS)
    address TEXT NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20),
    location GEOGRAPHY(POINT, 4326) NOT NULL,  -- lat/lng
    
    -- Location verification
    gps_verified BOOLEAN DEFAULT false,       -- GPS coordinates match address
    gps_verified_at TIMESTAMPTZ,
    location_accuracy_meters DECIMAL(10,2),   -- How accurate is the GPS pin
    
    -- Property details
    bedrooms INT NOT NULL CHECK (bedrooms >= 0),
    bathrooms DECIMAL(3,1) NOT NULL CHECK (bathrooms >= 0),
    area_sqm DECIMAL(10,2),
    furnished BOOLEAN DEFAULT false,
    
    -- Amenities (flexible per country)
    amenities JSONB DEFAULT '[]',  -- ["parking", "security", "generator", "water"]
    
    -- Pricing
    price DECIMAL(12,2) NOT NULL CHECK (price > 0),
    currency VARCHAR(3) NOT NULL,
    price_negotiable BOOLEAN DEFAULT false,
    
    -- For rentals
    deposit_amount DECIMAL(12,2),
    rent_period VARCHAR(20),  -- "monthly", "yearly", "weekly"
    
    -- Media
    images JSONB NOT NULL DEFAULT '[]',  -- [{url, order, hash}] - hash for duplicate detection
    videos JSONB DEFAULT '[]',
    virtual_tour_url TEXT,
    
    -- Documents (for verification)
    documents JSONB DEFAULT '[]',  -- [{type: "title_deed", url, verified}]
    
    -- Status
    status property_status DEFAULT 'draft',
    published_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    
    -- Moderation
    moderated_at TIMESTAMPTZ,
    moderated_by UUID REFERENCES users(id),
    moderation_notes TEXT,
    
    -- Anti-fraud
    verification_score INT DEFAULT 0 CHECK (verification_score BETWEEN 0 AND 100),
    fraud_flags JSONB DEFAULT '[]',  -- [{flag_type, detected_at, severity}]
    
    -- Analytics
    view_count INT DEFAULT 0,
    favorite_count INT DEFAULT 0,
    inquiry_count INT DEFAULT 0,
    
    -- Soft delete
    is_active BOOLEAN DEFAULT true,
    deleted_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_properties_country ON properties(country_id) WHERE is_active = true;
CREATE INDEX idx_properties_owner ON properties(owner_id);
CREATE INDEX idx_properties_status ON properties(status) WHERE is_active = true;
CREATE INDEX idx_properties_type ON properties(property_type);
CREATE INDEX idx_properties_listing_type ON properties(listing_type);
CREATE INDEX idx_properties_price ON properties(price) WHERE status = 'active';

-- Geospatial index (critical for "properties near me")
CREATE INDEX idx_properties_location ON properties USING GIST(location) WHERE status = 'active';

-- Full-text search on title + description
CREATE INDEX idx_properties_search ON properties USING GIN(to_tsvector('english', title || ' ' || description));

-- Multi-column index for common queries
CREATE INDEX idx_properties_active_price ON properties(status, price) WHERE is_active = true;

-- Row-level security
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;

CREATE POLICY country_isolation ON properties
    USING (country_id::TEXT = current_setting('app.current_country_id', TRUE));
```

### 4. Property Images (Separate table for better duplicate detection)

```sql
CREATE TABLE property_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    
    -- S3 location (never a full URL - see Project Statement 8.6)
    bucket VARCHAR(63) NOT NULL DEFAULT 'afe-media-public',
    storage_key TEXT NOT NULL,          -- processed WebP object
    original_key TEXT NOT NULL,         -- raw upload in afe-media-originals
    display_order INT NOT NULL DEFAULT 0,
    
    -- Perceptual hash for duplicate detection (from imagehash library)
    phash VARCHAR(64) NOT NULL,  -- Hexadecimal representation
    
    -- Image metadata
    width INT,
    height INT,
    file_size_kb INT,
    format VARCHAR(10),  -- "jpeg", "png", "webp"
    
    -- EXIF data read at upload, then STRIPPED from the stored file
    exif_data JSONB,  -- {camera_make, gps_lat, gps_lng, date_taken}
    
    -- Moderation
    is_approved BOOLEAN DEFAULT false,
    moderated_at TIMESTAMPTZ,
    rejection_reason TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_property_images_property ON property_images(property_id);
CREATE INDEX idx_property_images_phash ON property_images(phash);  -- Critical for duplicate detection
CREATE INDEX idx_property_images_order ON property_images(property_id, display_order);
```

---

### 4b. Stored Files

Every object in S3 has a row here: uploads, KYC documents, agreements, exports.

```sql
CREATE TYPE file_sensitivity AS ENUM ('public', 'internal', 'kyc', 'legal');
CREATE TYPE scan_status AS ENUM ('pending', 'clean', 'rejected');

CREATE TABLE stored_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    bucket VARCHAR(63) NOT NULL,
    storage_key TEXT NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,           -- integrity + exact-duplicate detection

    sensitivity file_sensitivity NOT NULL DEFAULT 'internal',
    scan scan_status NOT NULL DEFAULT 'pending',

    -- ownership / linkage (nullable: a file may belong to a user or a listing)
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    country_id VARCHAR(2) NOT NULL,

    metadata_stripped BOOLEAN DEFAULT false,
    retention_until DATE,               -- set from the retention policy (decision D18)
    deleted_at TIMESTAMPTZ,             -- soft delete; object removed by lifecycle job

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (bucket, storage_key)
);

CREATE INDEX idx_stored_files_sha256 ON stored_files(sha256);
CREATE INDEX idx_stored_files_owner ON stored_files(uploaded_by);
CREATE INDEX idx_stored_files_property ON stored_files(property_id);
CREATE INDEX idx_stored_files_retention ON stored_files(retention_until) WHERE deleted_at IS NULL;
```

---

## Anti-Fraud Tables

### 5. Fraud Detection Scores

```sql
CREATE TABLE fraud_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    
    -- Overall score (0-100, higher = more trustworthy)
    total_score INT NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    
    -- Component scores (each 0-100)
    document_score INT DEFAULT 0,      -- Title deed, ownership docs
    agent_reputation_score INT DEFAULT 50,
    property_metadata_score INT DEFAULT 0,  -- Photos, GPS, details
    market_analysis_score INT DEFAULT 50,   -- Price within range
    ml_anomaly_score INT DEFAULT 50,        -- Machine learning prediction
    
    -- Score breakdown for transparency
    score_breakdown JSONB NOT NULL,  -- Detailed explanation
    
    -- Risk classification
    risk_level VARCHAR(20) NOT NULL,  -- "LOW", "MEDIUM", "HIGH", "CRITICAL"
    
    -- Flags that affected score
    active_flags JSONB DEFAULT '[]',  -- ["price_too_low", "new_agent", "no_documents"]
    
    -- ML model info
    model_version VARCHAR(20),
    model_confidence DECIMAL(5,4),  -- 0.0000 to 1.0000
    
    calculated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- Re-calculate periodically
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_fraud_scores_property ON fraud_scores(property_id);
CREATE INDEX idx_fraud_scores_risk ON fraud_scores(risk_level);
CREATE INDEX idx_fraud_scores_total ON fraud_scores(total_score);

-- Ensure only one active score per property
CREATE UNIQUE INDEX idx_fraud_scores_property_active ON fraud_scores(property_id) 
    WHERE expires_at IS NULL OR expires_at > NOW();
```

### 6. Duplicate Detection Records

```sql
CREATE TABLE duplicate_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- The two properties being compared
    property_a_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    property_b_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    
    -- Similarity metrics
    image_similarity_score DECIMAL(5,4),  -- 0.0000 to 1.0000 (perceptual hash distance)
    text_similarity_score DECIMAL(5,4),   -- Title/description similarity
    location_distance_km DECIMAL(10,2),   -- Geographic distance
    
    -- Overall duplicate probability
    duplicate_probability DECIMAL(5,4) NOT NULL,
    
    -- Detection method
    detection_method VARCHAR(50) NOT NULL,  -- "phash", "text", "location", "ml"
    
    -- Status
    is_confirmed_duplicate BOOLEAN,
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMPTZ,
    
    -- Action taken
    action_taken VARCHAR(50),  -- "property_suspended", "owner_notified", "false_positive"
    
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    
    CHECK (property_a_id < property_b_id)  -- Prevent duplicate pairs
);

-- Indexes
CREATE INDEX idx_duplicate_detections_property_a ON duplicate_detections(property_a_id);
CREATE INDEX idx_duplicate_detections_property_b ON duplicate_detections(property_b_id);
CREATE INDEX idx_duplicate_detections_probability ON duplicate_detections(duplicate_probability DESC);
CREATE UNIQUE INDEX idx_duplicate_detections_unique_pair ON duplicate_detections(property_a_id, property_b_id);
```

### 7. Fraud Reports (User-submitted)

```sql
CREATE TABLE fraud_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- What's being reported
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    reported_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Who reported it
    reporter_id UUID NOT NULL REFERENCES users(id),
    
    -- Report details
    category fraud_category NOT NULL,
    description TEXT NOT NULL,
    evidence_urls JSONB DEFAULT '[]',  -- Screenshots, photos
    
    -- Investigation
    status VARCHAR(20) DEFAULT 'pending',  -- "pending", "investigating", "confirmed", "dismissed"
    investigated_by UUID REFERENCES users(id),
    investigated_at TIMESTAMPTZ,
    investigation_notes TEXT,
    
    -- Action taken
    action_taken VARCHAR(100),
    property_suspended BOOLEAN DEFAULT false,
    user_suspended BOOLEAN DEFAULT false,
    
    -- Reporter credibility (prevent spam reports)
    reporter_credibility_score INT,  -- Based on past report accuracy
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_fraud_reports_property ON fraud_reports(property_id);
CREATE INDEX idx_fraud_reports_reported_user ON fraud_reports(reported_user_id);
CREATE INDEX idx_fraud_reports_reporter ON fraud_reports(reporter_id);
CREATE INDEX idx_fraud_reports_status ON fraud_reports(status);
CREATE INDEX idx_fraud_reports_category ON fraud_reports(category);
```

### 8. User Behavior Analytics (for fraud pattern detection)

```sql
CREATE TABLE user_behaviors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session info
    session_id UUID NOT NULL,
    device_fingerprint VARCHAR(255),
    ip_address INET NOT NULL,
    user_agent TEXT,
    
    -- Location
    country_code VARCHAR(2),
    city VARCHAR(100),
    
    -- Activity
    event_type VARCHAR(50) NOT NULL,  -- "login", "property_view", "inquiry_sent", "payment_initiated"
    event_metadata JSONB DEFAULT '{}',
    
    -- Anomaly detection
    is_anomalous BOOLEAN DEFAULT false,
    anomaly_score DECIMAL(5,4),  -- ML model output
    anomaly_reason TEXT,
    
    -- Timestamp
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes (time-series partitioning recommended for scale)
CREATE INDEX idx_user_behaviors_user ON user_behaviors(user_id, occurred_at DESC);
CREATE INDEX idx_user_behaviors_session ON user_behaviors(session_id);
CREATE INDEX idx_user_behaviors_ip ON user_behaviors(ip_address);
CREATE INDEX idx_user_behaviors_event ON user_behaviors(event_type, occurred_at DESC);
CREATE INDEX idx_user_behaviors_anomalous ON user_behaviors(is_anomalous) WHERE is_anomalous = true;

-- Partition by month for performance
CREATE TABLE user_behaviors_2024_01 PARTITION OF user_behaviors
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
-- (Create partitions dynamically via cron job)
```

### 9. Fraud Ring Detection (Graph Analysis)

```sql
CREATE TABLE fraud_networks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Network identification
    network_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    network_name VARCHAR(255),  -- "Lagos Rental Scam Ring #7"
    
    -- Members
    member_user_ids UUID[] NOT NULL,  -- Array of user IDs in the ring
    member_count INT NOT NULL,
    
    -- Network patterns
    shared_ip_addresses INET[],
    shared_devices VARCHAR(255)[],
    shared_bank_accounts VARCHAR(100)[],
    
    -- Detection metadata
    detection_algorithm VARCHAR(50) NOT NULL,  -- "graph_clustering", "connected_components"
    confidence_score DECIMAL(5,4) NOT NULL,
    
    -- Graph metrics
    network_density DECIMAL(5,4),      -- How interconnected
    avg_transaction_value DECIMAL(12,2),
    total_transaction_volume DECIMAL(15,2),
    
    -- Investigation
    status VARCHAR(20) DEFAULT 'detected',  -- "detected", "investigating", "confirmed", "dismantled"
    investigated_by UUID REFERENCES users(id),
    notes TEXT,
    
    -- Actions
    users_suspended INT DEFAULT 0,
    properties_removed INT DEFAULT 0,
    law_enforcement_notified BOOLEAN DEFAULT false,
    
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_fraud_networks_status ON fraud_networks(status);
CREATE INDEX idx_fraud_networks_detected ON fraud_networks(detected_at DESC);
CREATE INDEX idx_fraud_networks_confidence ON fraud_networks(confidence_score DESC);

-- GIN index for array searches
CREATE INDEX idx_fraud_networks_members ON fraud_networks USING GIN(member_user_ids);
```

### 10. Transaction Escrow (Prevent payment fraud)

```sql
CREATE TABLE escrow_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id),
    
    -- Parties
    buyer_id UUID NOT NULL REFERENCES users(id),
    seller_id UUID NOT NULL REFERENCES users(id),
    agent_id UUID REFERENCES users(id),  -- Optional
    
    -- Amounts
    total_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    platform_fee DECIMAL(12,2) NOT NULL,
    agent_commission DECIMAL(12,2),
    seller_amount DECIMAL(12,2) NOT NULL,
    
    -- Release conditions (multi-sig)
    release_conditions JSONB NOT NULL,  -- [{condition: "keys_handed_over", amount_pct: 50, required_signatures: ["buyer", "seller"]}]
    conditions_met JSONB DEFAULT '[]',  -- Track which conditions are satisfied
    
    -- Time locks (prevent instant withdrawal scams)
    locked_until TIMESTAMPTZ NOT NULL,  -- Cannot release before this
    
    -- Payment gateway
    payment_provider VARCHAR(50) NOT NULL,  -- "flutterwave", "paystack"
    payment_reference VARCHAR(255) UNIQUE NOT NULL,
    payment_status payment_status DEFAULT 'pending',
    
    -- Release tracking
    amount_released DECIMAL(12,2) DEFAULT 0,
    release_signatures JSONB DEFAULT '[]',  -- [{party: "buyer", signed_at, signature}]
    
    -- Dispute handling
    is_disputed BOOLEAN DEFAULT false,
    dispute_opened_at TIMESTAMPTZ,
    dispute_opened_by UUID REFERENCES users(id),
    arbitrator_id UUID REFERENCES users(id),
    dispute_resolved_at TIMESTAMPTZ,
    dispute_outcome TEXT,
    
    -- Refund
    refund_amount DECIMAL(12,2),
    refunded_at TIMESTAMPTZ,
    refund_reason TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_escrow_property ON escrow_transactions(property_id);
CREATE INDEX idx_escrow_buyer ON escrow_transactions(buyer_id);
CREATE INDEX idx_escrow_seller ON escrow_transactions(seller_id);
CREATE INDEX idx_escrow_status ON escrow_transactions(payment_status);
CREATE INDEX idx_escrow_disputed ON escrow_transactions(is_disputed) WHERE is_disputed = true;
```

### 11. Payment Transactions (Audit trail)

```sql
CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    escrow_id UUID REFERENCES escrow_transactions(id),
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Transaction details
    transaction_type VARCHAR(50) NOT NULL,  -- "payment", "refund", "commission", "withdrawal"
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    
    -- Payment provider
    provider VARCHAR(50) NOT NULL,
    provider_transaction_id VARCHAR(255) UNIQUE,
    provider_reference VARCHAR(255),
    
    -- Status
    status payment_status DEFAULT 'pending',
    
    -- Fraud checks
    fraud_check_passed BOOLEAN,
    fraud_check_score DECIMAL(5,4),
    fraud_check_notes TEXT,
    
    -- Metadata
    ip_address INET,
    device_fingerprint VARCHAR(255),
    payment_method VARCHAR(50),  -- "card", "bank_transfer", "mobile_money", "ussd"
    
    -- Timestamps
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    failure_reason TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_payment_escrow ON payment_transactions(escrow_id);
CREATE INDEX idx_payment_user ON payment_transactions(user_id, created_at DESC);
CREATE INDEX idx_payment_status ON payment_transactions(status);
CREATE INDEX idx_payment_provider_ref ON payment_transactions(provider_transaction_id);
```

### 12. Rate Limiting (Prevent scraping & brute force)

```sql
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Who/what is being rate limited
    identifier_type VARCHAR(20) NOT NULL,  -- "ip", "user", "device", "api_key"
    identifier_value VARCHAR(255) NOT NULL,
    
    -- Endpoint/action
    resource VARCHAR(100) NOT NULL,  -- "/api/properties/search", "login", "sms_otp"
    
    -- Limits
    max_requests INT NOT NULL,
    window_seconds INT NOT NULL,  -- 60, 3600, 86400
    
    -- Current state
    request_count INT DEFAULT 0,
    window_start TIMESTAMPTZ DEFAULT NOW(),
    
    -- Violation tracking
    violations INT DEFAULT 0,
    last_violation_at TIMESTAMPTZ,
    
    -- Blocking
    is_blocked BOOLEAN DEFAULT false,
    blocked_until TIMESTAMPTZ,
    block_reason TEXT,
    
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX idx_rate_limits_identifier ON rate_limits(identifier_type, identifier_value, resource);
CREATE INDEX idx_rate_limits_blocked ON rate_limits(is_blocked, blocked_until) WHERE is_blocked = true;
```

---

## Audit & Logging Tables

### 13. Audit Logs (Compliance & forensics)

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Who
    user_id UUID REFERENCES users(id),
    ip_address INET NOT NULL,
    user_agent TEXT,
    
    -- What
    action VARCHAR(100) NOT NULL,  -- "property_created", "user_suspended", "payment_released"
    entity_type VARCHAR(50),       -- "property", "user", "escrow"
    entity_id UUID,
    
    -- Changes (for audit trail)
    old_values JSONB,
    new_values JSONB,
    
    -- Context
    request_id UUID,  -- Trace through distributed system
    session_id UUID,
    
    -- Timestamp
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes (partitioned by month for performance)
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, occurred_at DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(action, occurred_at DESC);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id, occurred_at DESC);
CREATE INDEX idx_audit_logs_occurred ON audit_logs(occurred_at DESC);

-- Partition by month
CREATE TABLE audit_logs_2024_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

---

## Supporting Tables

### 14. Inquiries (Lead tracking)

```sql
CREATE TABLE inquiries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Message
    message TEXT NOT NULL,
    
    -- Contact preference
    contact_via VARCHAR(20) DEFAULT 'email',  -- "email", "phone", "whatsapp"
    
    -- Status
    status VARCHAR(20) DEFAULT 'new',  -- "new", "replied", "viewed", "converted", "spam"
    replied_at TIMESTAMPTZ,
    
    -- Spam detection
    is_spam BOOLEAN DEFAULT false,
    spam_score DECIMAL(5,4),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_inquiries_property ON inquiries(property_id, created_at DESC);
CREATE INDEX idx_inquiries_user ON inquiries(user_id, created_at DESC);
CREATE INDEX idx_inquiries_status ON inquiries(status);
```

### 15. Favorites (Wishlist)

```sql
CREATE TABLE favorites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, property_id)
);

-- Indexes
CREATE INDEX idx_favorites_user ON favorites(user_id, created_at DESC);
CREATE INDEX idx_favorites_property ON favorites(property_id);
```

---

## Triggers & Functions

### Auto-update `updated_at` timestamp

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_countries_updated_at BEFORE UPDATE ON countries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### Audit log trigger (automatic)

```sql
CREATE OR REPLACE FUNCTION log_property_changes()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_logs (
        user_id, 
        action, 
        entity_type, 
        entity_id, 
        old_values, 
        new_values,
        ip_address
    )
    VALUES (
        NEW.owner_id,
        TG_OP || '_property',
        'property',
        NEW.id,
        CASE WHEN TG_OP = 'UPDATE' THEN row_to_json(OLD) ELSE NULL END,
        row_to_json(NEW),
        inet_client_addr()
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_property_changes
    AFTER INSERT OR UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION log_property_changes();
```

### Calculate fraud score on property creation

```sql
CREATE OR REPLACE FUNCTION calculate_initial_fraud_score()
RETURNS TRIGGER AS $$
DECLARE
    score INT := 50;  -- Start at neutral
BEGIN
    -- Adjust based on agent reputation
    IF (SELECT reputation_score FROM users WHERE id = NEW.owner_id) >= 80 THEN
        score := score + 15;
    END IF;
    
    -- Penalize if no documents
    IF NEW.documents = '[]' THEN
        score := score - 20;
    END IF;
    
    -- Reward GPS verification
    IF NEW.gps_verified THEN
        score := score + 10;
    END IF;
    
    -- Penalize if too many images (common scam tactic)
    IF jsonb_array_length(NEW.images) > 20 THEN
        score := score - 10;
    END IF;
    
    -- Clamp to 0-100
    score := GREATEST(0, LEAST(100, score));
    
    NEW.verification_score := score;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_initial_fraud_score
    BEFORE INSERT ON properties
    FOR EACH ROW EXECUTE FUNCTION calculate_initial_fraud_score();
```

---

## Performance Optimization

### Materialized Views (for dashboards)

```sql
-- Country-level statistics (refresh hourly)
CREATE MATERIALIZED VIEW country_stats AS
SELECT 
    c.code AS country_code,
    c.name AS country_name,
    COUNT(DISTINCT p.id) AS total_properties,
    COUNT(DISTINCT p.id) FILTER (WHERE p.status = 'active') AS active_properties,
    COUNT(DISTINCT u.id) AS total_users,
    COUNT(DISTINCT u.id) FILTER (WHERE u.role = 'agent') AS total_agents,
    AVG(p.price) AS avg_property_price,
    SUM(p.view_count) AS total_views,
    COUNT(DISTINCT fr.id) AS fraud_reports_count
FROM countries c
LEFT JOIN properties p ON p.country_id = c.id
LEFT JOIN users u ON u.country_id = c.id
LEFT JOIN fraud_reports fr ON fr.property_id = p.id
GROUP BY c.id, c.code, c.name;

CREATE UNIQUE INDEX ON country_stats(country_code);

-- Refresh schedule (via cron or pg_cron extension)
-- SELECT cron.schedule('refresh_country_stats', '0 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY country_stats');
```

---

## Data Retention & Archival

```sql
-- Archive old audit logs (keep 1 year, archive to S3)
CREATE TABLE audit_logs_archive (LIKE audit_logs);

-- Move logs older than 1 year
INSERT INTO audit_logs_archive 
SELECT * FROM audit_logs 
WHERE occurred_at < NOW() - INTERVAL '1 year';

DELETE FROM audit_logs 
WHERE occurred_at < NOW() - INTERVAL '1 year';

-- Similar for user_behaviors (keep 3 months)
DELETE FROM user_behaviors 
WHERE occurred_at < NOW() - INTERVAL '3 months';
```

---

## Summary

**Total Tables**: 26
- **Core**: 6 (countries, users, properties, property_images, inquiries, favorites)
- **Anti-Fraud**: 8 (fraud_scores, duplicate_detections, fraud_reports, user_behaviors, fraud_networks, escrow_transactions, payment_transactions, rate_limits)
- **Audit**: 3 (audit_logs, + partitions)

**Key Features**:
- ✅ Multi-tenant (country-level RLS)
- ✅ Geospatial (PostGIS for location queries)
- ✅ Full-text search (property titles/descriptions)
- ✅ Fraud prevention (scores, duplicate detection, behavior tracking)
- ✅ Escrow system (time-locked payments)
- ✅ Audit trail (compliance-ready)
- ✅ Performance (indexes, partitioning, materialized views)

**Next Steps**:
1. Apply migrations with Alembic
2. Seed with country data
3. Implement fraud detection algorithms (see fraud-detection.md)
4. Set up monitoring (query performance, fraud alerts)
