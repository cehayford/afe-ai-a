#!/usr/bin/env python3
"""
init_database.py

Initialize House Agent database schema with all tables, indexes, and seed data.
Uses Alembic for migration management.

Usage:
    python init_database.py --db-url postgresql://user:pass@localhost/houseagent
    python init_database.py --create-migration "add fraud tables"
"""

import argparse
import asyncio
import asyncpg
from pathlib import Path
import sys

# Database schema SQL
SCHEMA_SQL = """
-- ============================================================================
-- House Agent Database Schema v1.0
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE property_status AS ENUM (
    'draft', 'pending_review', 'active', 'rented', 'suspended', 'deleted'
);

CREATE TYPE property_type AS ENUM (
    'bungalow', 'duplex', 'terrace', 'flat', 'detached', 'semi_detached',
    'chamber_and_hall', 'self_contained', 'compound_house',
    'bedsitter', 'studio', 'maisonette',
    'townhouse', 'cluster', 'freestanding',
    'apartment', 'commercial', 'land', 'warehouse', 'office'
);

CREATE TYPE listing_type AS ENUM ('rent', 'sale', 'lease', 'short_term');

CREATE TYPE user_role AS ENUM (
    'tenant', 'landlord', 'agent', 'property_manager', 'admin', 'moderator'
);

CREATE TYPE verification_status AS ENUM (
    'unverified', 'pending', 'verified', 'rejected', 'suspended'
);

CREATE TYPE payment_status AS ENUM (
    'pending', 'processing', 'completed', 'failed', 'refunded', 'disputed'
);

CREATE TYPE escrow_condition AS ENUM (
    'listing_verified', 'inspection_completed', 'keys_handed_over',
    'move_in_confirmed', 'dispute_resolved'
);

CREATE TYPE fraud_category AS ENUM (
    'duplicate_listing', 'fake_photos', 'price_scam', 'fake_agent',
    'non_existent_property', 'unauthorized_listing', 'payment_fraud', 'identity_theft'
);

-- ============================================================================
-- CORE TABLES
-- ============================================================================

CREATE TABLE countries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(2) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    languages JSONB NOT NULL,
    payment_providers JSONB NOT NULL,
    data_residency_required BOOLEAN DEFAULT false,
    gdpr_applicable BOOLEAN DEFAULT false,
    commission_rate DECIMAL(5,2) DEFAULT 3.5,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_id UUID NOT NULL REFERENCES countries(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role user_role NOT NULL DEFAULT 'tenant',
    avatar_url TEXT,
    verification_status verification_status DEFAULT 'unverified',
    id_document_url TEXT,
    id_verified_at TIMESTAMPTZ,
    two_factor_enabled BOOLEAN DEFAULT false,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,
    device_fingerprints JSONB DEFAULT '[]',
    reputation_score INT DEFAULT 50 CHECK (reputation_score BETWEEN 0 AND 100),
    completed_transactions INT DEFAULT 0,
    dispute_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_id UUID NOT NULL REFERENCES countries(id),
    owner_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    property_type property_type NOT NULL,
    listing_type listing_type NOT NULL,
    address TEXT NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20),
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    gps_verified BOOLEAN DEFAULT false,
    gps_verified_at TIMESTAMPTZ,
    location_accuracy_meters DECIMAL(10,2),
    bedrooms INT NOT NULL CHECK (bedrooms >= 0),
    bathrooms DECIMAL(3,1) NOT NULL CHECK (bathrooms >= 0),
    area_sqm DECIMAL(10,2),
    furnished BOOLEAN DEFAULT false,
    amenities JSONB DEFAULT '[]',
    price DECIMAL(12,2) NOT NULL CHECK (price > 0),
    currency VARCHAR(3) NOT NULL,
    price_negotiable BOOLEAN DEFAULT false,
    deposit_amount DECIMAL(12,2),
    rent_period VARCHAR(20),
    images JSONB NOT NULL DEFAULT '[]',
    videos JSONB DEFAULT '[]',
    virtual_tour_url TEXT,
    documents JSONB DEFAULT '[]',
    status property_status DEFAULT 'draft',
    published_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    moderated_at TIMESTAMPTZ,
    moderated_by UUID REFERENCES users(id),
    moderation_notes TEXT,
    verification_score INT DEFAULT 0 CHECK (verification_score BETWEEN 0 AND 100),
    fraud_flags JSONB DEFAULT '[]',
    view_count INT DEFAULT 0,
    favorite_count INT DEFAULT 0,
    inquiry_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE property_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    bucket VARCHAR(63) NOT NULL DEFAULT 'afe-media-public',
    storage_key TEXT NOT NULL,
    original_key TEXT NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    phash VARCHAR(64) NOT NULL,
    width INT,
    height INT,
    file_size_kb INT,
    format VARCHAR(10),
    exif_data JSONB,
    is_approved BOOLEAN DEFAULT false,
    moderated_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TYPE file_sensitivity AS ENUM ('public', 'internal', 'kyc', 'legal');
CREATE TYPE scan_status AS ENUM ('pending', 'clean', 'rejected');

CREATE TABLE stored_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bucket VARCHAR(63) NOT NULL,
    storage_key TEXT NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    sensitivity file_sensitivity NOT NULL DEFAULT 'internal',
    scan scan_status NOT NULL DEFAULT 'pending',
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    country_id VARCHAR(2) NOT NULL,
    metadata_stripped BOOLEAN DEFAULT false,
    retention_until DATE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (bucket, storage_key)
);

-- ============================================================================
-- ANTI-FRAUD TABLES
-- ============================================================================

CREATE TABLE fraud_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    total_score INT NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    document_score INT DEFAULT 0,
    agent_reputation_score INT DEFAULT 50,
    property_metadata_score INT DEFAULT 0,
    market_analysis_score INT DEFAULT 50,
    ml_anomaly_score INT DEFAULT 50,
    score_breakdown JSONB NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    active_flags JSONB DEFAULT '[]',
    model_version VARCHAR(20),
    model_confidence DECIMAL(5,4),
    calculated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE duplicate_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_a_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    property_b_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    image_similarity_score DECIMAL(5,4),
    text_similarity_score DECIMAL(5,4),
    location_distance_km DECIMAL(10,2),
    duplicate_probability DECIMAL(5,4) NOT NULL,
    detection_method VARCHAR(50) NOT NULL,
    is_confirmed_duplicate BOOLEAN,
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMPTZ,
    action_taken VARCHAR(50),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (property_a_id < property_b_id)
);

CREATE TABLE fraud_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    reported_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    reporter_id UUID NOT NULL REFERENCES users(id),
    category fraud_category NOT NULL,
    description TEXT NOT NULL,
    evidence_urls JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'pending',
    investigated_by UUID REFERENCES users(id),
    investigated_at TIMESTAMPTZ,
    investigation_notes TEXT,
    action_taken VARCHAR(100),
    property_suspended BOOLEAN DEFAULT false,
    user_suspended BOOLEAN DEFAULT false,
    reporter_credibility_score INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_behaviors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    device_fingerprint VARCHAR(255),
    ip_address INET NOT NULL,
    user_agent TEXT,
    country_code VARCHAR(2),
    city VARCHAR(100),
    event_type VARCHAR(50) NOT NULL,
    event_metadata JSONB DEFAULT '{}',
    is_anomalous BOOLEAN DEFAULT false,
    anomaly_score DECIMAL(5,4),
    anomaly_reason TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE fraud_networks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    network_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    network_name VARCHAR(255),
    member_user_ids UUID[] NOT NULL,
    member_count INT NOT NULL,
    shared_ip_addresses INET[],
    shared_devices VARCHAR(255)[],
    shared_bank_accounts VARCHAR(100)[],
    detection_algorithm VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(5,4) NOT NULL,
    network_density DECIMAL(5,4),
    avg_transaction_value DECIMAL(12,2),
    total_transaction_volume DECIMAL(15,2),
    status VARCHAR(20) DEFAULT 'detected',
    investigated_by UUID REFERENCES users(id),
    notes TEXT,
    users_suspended INT DEFAULT 0,
    properties_removed INT DEFAULT 0,
    law_enforcement_notified BOOLEAN DEFAULT false,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE escrow_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id),
    buyer_id UUID NOT NULL REFERENCES users(id),
    seller_id UUID NOT NULL REFERENCES users(id),
    agent_id UUID REFERENCES users(id),
    total_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    platform_fee DECIMAL(12,2) NOT NULL,
    agent_commission DECIMAL(12,2),
    seller_amount DECIMAL(12,2) NOT NULL,
    release_conditions JSONB NOT NULL,
    conditions_met JSONB DEFAULT '[]',
    locked_until TIMESTAMPTZ NOT NULL,
    payment_provider VARCHAR(50) NOT NULL,
    payment_reference VARCHAR(255) UNIQUE NOT NULL,
    payment_status payment_status DEFAULT 'pending',
    amount_released DECIMAL(12,2) DEFAULT 0,
    release_signatures JSONB DEFAULT '[]',
    is_disputed BOOLEAN DEFAULT false,
    dispute_opened_at TIMESTAMPTZ,
    dispute_opened_by UUID REFERENCES users(id),
    arbitrator_id UUID REFERENCES users(id),
    dispute_resolved_at TIMESTAMPTZ,
    dispute_outcome TEXT,
    refund_amount DECIMAL(12,2),
    refunded_at TIMESTAMPTZ,
    refund_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    escrow_id UUID REFERENCES escrow_transactions(id),
    user_id UUID NOT NULL REFERENCES users(id),
    transaction_type VARCHAR(50) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_transaction_id VARCHAR(255) UNIQUE,
    provider_reference VARCHAR(255),
    status payment_status DEFAULT 'pending',
    fraud_check_passed BOOLEAN,
    fraud_check_score DECIMAL(5,4),
    fraud_check_notes TEXT,
    ip_address INET,
    device_fingerprint VARCHAR(255),
    payment_method VARCHAR(50),
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identifier_type VARCHAR(20) NOT NULL,
    identifier_value VARCHAR(255) NOT NULL,
    resource VARCHAR(100) NOT NULL,
    max_requests INT NOT NULL,
    window_seconds INT NOT NULL,
    request_count INT DEFAULT 0,
    window_start TIMESTAMPTZ DEFAULT NOW(),
    violations INT DEFAULT 0,
    last_violation_at TIMESTAMPTZ,
    is_blocked BOOLEAN DEFAULT false,
    blocked_until TIMESTAMPTZ,
    block_reason TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- AUDIT TABLES
-- ============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    ip_address INET NOT NULL,
    user_agent TEXT,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    old_values JSONB,
    new_values JSONB,
    request_id UUID,
    session_id UUID,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- SUPPORTING TABLES
-- ============================================================================

CREATE TABLE inquiries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    contact_via VARCHAR(20) DEFAULT 'email',
    status VARCHAR(20) DEFAULT 'new',
    replied_at TIMESTAMPTZ,
    is_spam BOOLEAN DEFAULT false,
    spam_score DECIMAL(5,4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE favorites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, property_id)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Users
CREATE INDEX idx_users_country ON users(country_id) WHERE is_active = true;
CREATE INDEX idx_users_email ON users(email) WHERE is_active = true;
CREATE INDEX idx_users_phone ON users(phone) WHERE is_active = true;
CREATE INDEX idx_users_role ON users(role) WHERE is_active = true;
CREATE INDEX idx_users_verification ON users(verification_status);

-- Properties
CREATE INDEX idx_properties_country ON properties(country_id) WHERE is_active = true;
CREATE INDEX idx_properties_owner ON properties(owner_id);
CREATE INDEX idx_properties_status ON properties(status) WHERE is_active = true;
CREATE INDEX idx_properties_type ON properties(property_type);
CREATE INDEX idx_properties_listing_type ON properties(listing_type);
CREATE INDEX idx_properties_price ON properties(price) WHERE status = 'active';
CREATE INDEX idx_properties_location ON properties USING GIST(location) WHERE status = 'active';
CREATE INDEX idx_properties_search ON properties USING GIN(to_tsvector('english', title || ' ' || description));
CREATE INDEX idx_properties_active_price ON properties(status, price) WHERE is_active = true;

-- Property Images
CREATE INDEX idx_property_images_property ON property_images(property_id);
CREATE INDEX idx_property_images_phash ON property_images(phash);
CREATE INDEX idx_property_images_order ON property_images(property_id, display_order);

-- Stored Files
CREATE INDEX idx_stored_files_sha256 ON stored_files(sha256);
CREATE INDEX idx_stored_files_owner ON stored_files(uploaded_by);
CREATE INDEX idx_stored_files_property ON stored_files(property_id);
CREATE INDEX idx_stored_files_retention ON stored_files(retention_until) WHERE deleted_at IS NULL;

-- Fraud Scores
CREATE INDEX idx_fraud_scores_property ON fraud_scores(property_id);
CREATE INDEX idx_fraud_scores_risk ON fraud_scores(risk_level);
CREATE INDEX idx_fraud_scores_total ON fraud_scores(total_score);
CREATE UNIQUE INDEX idx_fraud_scores_property_active ON fraud_scores(property_id) 
    WHERE expires_at IS NULL OR expires_at > NOW();

-- Duplicate Detections
CREATE INDEX idx_duplicate_detections_property_a ON duplicate_detections(property_a_id);
CREATE INDEX idx_duplicate_detections_property_b ON duplicate_detections(property_b_id);
CREATE INDEX idx_duplicate_detections_probability ON duplicate_detections(duplicate_probability DESC);
CREATE UNIQUE INDEX idx_duplicate_detections_unique_pair ON duplicate_detections(property_a_id, property_b_id);

-- Fraud Reports
CREATE INDEX idx_fraud_reports_property ON fraud_reports(property_id);
CREATE INDEX idx_fraud_reports_reported_user ON fraud_reports(reported_user_id);
CREATE INDEX idx_fraud_reports_reporter ON fraud_reports(reporter_id);
CREATE INDEX idx_fraud_reports_status ON fraud_reports(status);
CREATE INDEX idx_fraud_reports_category ON fraud_reports(category);

-- User Behaviors
CREATE INDEX idx_user_behaviors_user ON user_behaviors(user_id, occurred_at DESC);
CREATE INDEX idx_user_behaviors_session ON user_behaviors(session_id);
CREATE INDEX idx_user_behaviors_ip ON user_behaviors(ip_address);
CREATE INDEX idx_user_behaviors_event ON user_behaviors(event_type, occurred_at DESC);
CREATE INDEX idx_user_behaviors_anomalous ON user_behaviors(is_anomalous) WHERE is_anomalous = true;

-- Fraud Networks
CREATE INDEX idx_fraud_networks_status ON fraud_networks(status);
CREATE INDEX idx_fraud_networks_detected ON fraud_networks(detected_at DESC);
CREATE INDEX idx_fraud_networks_confidence ON fraud_networks(confidence_score DESC);
CREATE INDEX idx_fraud_networks_members ON fraud_networks USING GIN(member_user_ids);

-- Escrow & Payments
CREATE INDEX idx_escrow_property ON escrow_transactions(property_id);
CREATE INDEX idx_escrow_buyer ON escrow_transactions(buyer_id);
CREATE INDEX idx_escrow_seller ON escrow_transactions(seller_id);
CREATE INDEX idx_escrow_status ON escrow_transactions(payment_status);
CREATE INDEX idx_escrow_disputed ON escrow_transactions(is_disputed) WHERE is_disputed = true;
CREATE INDEX idx_payment_escrow ON payment_transactions(escrow_id);
CREATE INDEX idx_payment_user ON payment_transactions(user_id, created_at DESC);
CREATE INDEX idx_payment_status ON payment_transactions(status);
CREATE INDEX idx_payment_provider_ref ON payment_transactions(provider_transaction_id);

-- Rate Limits
CREATE UNIQUE INDEX idx_rate_limits_identifier ON rate_limits(identifier_type, identifier_value, resource);
CREATE INDEX idx_rate_limits_blocked ON rate_limits(is_blocked, blocked_until) WHERE is_blocked = true;

-- Audit Logs
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, occurred_at DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(action, occurred_at DESC);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id, occurred_at DESC);
CREATE INDEX idx_audit_logs_occurred ON audit_logs(occurred_at DESC);

-- Inquiries & Favorites
CREATE INDEX idx_inquiries_property ON inquiries(property_id, created_at DESC);
CREATE INDEX idx_inquiries_user ON inquiries(user_id, created_at DESC);
CREATE INDEX idx_inquiries_status ON inquiries(status);
CREATE INDEX idx_favorites_user ON favorites(user_id, created_at DESC);
CREATE INDEX idx_favorites_property ON favorites(property_id);

-- ============================================================================
-- ROW-LEVEL SECURITY
-- ============================================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;

CREATE POLICY country_isolation_users ON users
    USING (country_id::TEXT = current_setting('app.current_country_id', TRUE));

CREATE POLICY country_isolation_properties ON properties
    USING (country_id::TEXT = current_setting('app.current_country_id', TRUE));

-- ============================================================================
-- TRIGGERS
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_countries_updated_at BEFORE UPDATE ON countries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fraud_reports_updated_at BEFORE UPDATE ON fraud_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fraud_networks_updated_at BEFORE UPDATE ON fraud_networks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_escrow_updated_at BEFORE UPDATE ON escrow_transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
"""

SEED_DATA_SQL = """
-- ============================================================================
-- SEED DATA
-- ============================================================================

INSERT INTO countries (code, name, currency_code, timezone, languages, payment_providers) VALUES
('NG', 'Nigeria', 'NGN', 'Africa/Lagos', '["en", "yo", "ig", "ha"]', '{"flutterwave": true, "paystack": true}'),
('GH', 'Ghana', 'GHS', 'Africa/Accra', '["en", "tw", "ga"]', '{"flutterwave": true, "paystack": true}'),
('KE', 'Kenya', 'KES', 'Africa/Nairobi', '["en", "sw"]', '{"flutterwave": true, "mpesa": true}'),
('TZ', 'Tanzania', 'TZS', 'Africa/Dar_es_Salaam', '["sw", "en"]', '{"flutterwave": true, "mpesa": true}'),
('ZA', 'South Africa', 'ZAR', 'Africa/Johannesburg', '["en", "zu", "xh", "af"]', '{"paystack": true, "ozow": true}');
"""


async def init_database(db_url: str):
    """Initialize database with schema and seed data."""
    print("🔧 Connecting to database...")
    conn = await asyncpg.connect(db_url)
    
    try:
        print("📋 Creating schema...")
        await conn.execute(SCHEMA_SQL)
        
        print("🌱 Inserting seed data...")
        await conn.execute(SEED_DATA_SQL)
        
        print("✅ Database initialized successfully!")
        
        # Verify
        count = await conn.fetchval("SELECT COUNT(*) FROM countries")
        print(f"📊 Seeded {count} countries")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description='Initialize House Agent database')
    parser.add_argument(
        '--db-url',
        required=True,
        help='PostgreSQL connection URL (postgresql://user:pass@host/db)'
    )
    
    args = parser.parse_args()
    
    asyncio.run(init_database(args.db_url))


if __name__ == '__main__':
    main()
