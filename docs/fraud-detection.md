# House Agent - Production Fraud Detection Algorithms

Production-ready Python implementation of fraud detection systems for the House Agent property platform.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Fraud Detection Pipeline                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Pre-listing Validation  (Real-time, <500ms)              │
│     ├─ Duplicate Image Detection (perceptual hashing)       │
│     ├─ Agent KYC Check                                       │
│     └─ Document Verification                                 │
│                                                               │
│  2. Listing Scoring  (Real-time, <1s)                        │
│     ├─ Property Verification Score (weighted algorithm)      │
│     ├─ Market Price Analysis                                 │
│     └─ ML Anomaly Detection (Isolation Forest)               │
│                                                               │
│  3. Transaction Monitoring  (Real-time + batch)              │
│     ├─ Payment Fraud Detection                               │
│     ├─ Behavior Anomaly Detection                            │
│     └─ Device Fingerprinting                                 │
│                                                               │
│  4. Network Analysis  (Batch, hourly)                        │
│     ├─ Fraud Ring Detection (graph clustering)              │
│     ├─ Community Detection (Louvain algorithm)               │
│     └─ Suspicious Pattern Mining                             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation & Dependencies

```bash
# Core dependencies
pip install --break-system-packages \
    pillow==10.1.0 \
    imagehash==4.3.1 \
    scikit-learn==1.3.2 \
    networkx==3.2.1 \
    numpy==1.26.2 \
    scipy==1.11.4 \
    asyncpg==0.29.0 \
    pydantic==2.5.0

# Optional for advanced features
pip install --break-system-packages \
    python-louvain==0.16 \        # Community detection
    tensorflow==2.15.0 \           # Deep learning (if needed)
    redis==5.0.1                   # Caching fraud scores
```

---

## 1. Duplicate Image Detection

> **STACK-001:** production hashing runs in Rust (`afe_native.phash`, `afe_native.hamming_matches`). The Python code below is kept as the reference implementation for parity tests.

### Implementation (Perceptual Hashing)

```python
"""
duplicate_detector.py

Detects duplicate property listings by comparing image perceptual hashes.
Uses pHash algorithm which is robust to resizing, compression, and minor edits.
"""

import imagehash
from PIL import Image
from typing import List, Dict, Optional, Tuple
import asyncpg
from dataclasses import dataclass
from io import BytesIO
import aiohttp

@dataclass
class DuplicateMatch:
    property_a_id: str
    property_b_id: str
    similarity_score: float
    matching_images: List[Tuple[str, str]]
    detection_method: str

class DuplicateImageDetector:
    """
    Detects duplicate property listings using perceptual image hashing.
    
    Algorithm: pHash (Perceptual Hash)
    - Converts image to grayscale
    - Resizes to 32x32 (or 8x8 for faster, less accurate)
    - Applies DCT (Discrete Cosine Transform)
    - Generates 64-bit hash
    
    Similarity: Hamming distance between hashes
    - Distance 0-5: Very likely duplicate
    - Distance 6-10: Possibly duplicate (minor edits)
    - Distance 11-15: Similar but probably different
    - Distance >15: Different images
    """
    
    DUPLICATE_THRESHOLD = 10  # Hamming distance
    HASH_SIZE = 8  # 8x8 = 64-bit hash (trade-off: speed vs accuracy)
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
    
    async def compute_image_hash(self, image_url: str) -> Optional[str]:
        """
        Download image and compute perceptual hash.
        
        Returns:
            Hexadecimal hash string (e.g., "8f373714c1c6c1c6")
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=10) as response:
                    if response.status != 200:
                        return None
                    
                    image_bytes = await response.read()
                    image = Image.open(BytesIO(image_bytes))
                    
                    # Compute perceptual hash
                    phash = imagehash.phash(image, hash_size=self.HASH_SIZE)
                    
                    return str(phash)
        
        except Exception as e:
            print(f"Error computing hash for {image_url}: {e}")
            return None
    
    async def find_duplicates(
        self, 
        property_id: str, 
        image_hashes: List[str]
    ) -> List[DuplicateMatch]:
        """
        Find duplicate properties by comparing image hashes.
        
        Args:
            property_id: New property being checked
            image_hashes: List of perceptual hashes for this property's images
        
        Returns:
            List of potential duplicate matches
        """
        duplicates = []
        
        async with self.db_pool.acquire() as conn:
            # Get all other properties' image hashes
            existing_properties = await conn.fetch("""
                SELECT DISTINCT
                    pi.property_id,
                    pi.phash,
                    pi.url
                FROM property_images pi
                WHERE pi.property_id != $1
                    AND pi.is_approved = true
            """, property_id)
            
            # Group by property_id
            property_hashes = {}
            for row in existing_properties:
                pid = row['property_id']
                if pid not in property_hashes:
                    property_hashes[pid] = []
                property_hashes[pid].append({
                    'hash': row['phash'],
                    'url': row['url']
                })
            
            # Compare each new hash against existing properties
            for pid, existing_images in property_hashes.items():
                matching_images = []
                min_distance = float('inf')
                
                for new_hash in image_hashes:
                    new_hash_obj = imagehash.hex_to_hash(new_hash)
                    
                    for existing_img in existing_images:
                        existing_hash_obj = imagehash.hex_to_hash(existing_img['hash'])
                        
                        # Hamming distance (number of differing bits)
                        distance = new_hash_obj - existing_hash_obj
                        
                        if distance < self.DUPLICATE_THRESHOLD:
                            matching_images.append((new_hash, existing_img['hash']))
                            min_distance = min(min_distance, distance)
                
                # If we found matching images, this is likely a duplicate
                if matching_images:
                    similarity_score = 1.0 - (min_distance / 64.0)  # Normalize to 0-1
                    
                    duplicates.append(DuplicateMatch(
                        property_a_id=property_id,
                        property_b_id=pid,
                        similarity_score=similarity_score,
                        matching_images=matching_images,
                        detection_method='phash'
                    ))
        
        # Sort by similarity (highest first)
        duplicates.sort(key=lambda x: x.similarity_score, reverse=True)
        
        return duplicates
    
    async def store_duplicate_detection(
        self, 
        match: DuplicateMatch
    ) -> None:
        """
        Store duplicate detection in database for review.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO duplicate_detections (
                    property_a_id,
                    property_b_id,
                    image_similarity_score,
                    duplicate_probability,
                    detection_method,
                    detected_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (property_a_id, property_b_id) DO UPDATE
                SET 
                    image_similarity_score = EXCLUDED.image_similarity_score,
                    duplicate_probability = EXCLUDED.duplicate_probability,
                    detected_at = NOW()
            """, 
                match.property_a_id,
                match.property_b_id,
                match.similarity_score,
                match.similarity_score,  # Can combine with other signals later
                match.detection_method
            )


# Example usage
async def check_for_duplicates(property_id: str, image_urls: List[str]):
    """
    Full workflow for checking a new property listing.
    """
    detector = DuplicateImageDetector(db_pool)
    
    # Step 1: Compute hashes for new images
    image_hashes = []
    for url in image_urls:
        phash = await detector.compute_image_hash(url)
        if phash:
            image_hashes.append(phash)
    
    # Step 2: Find duplicates
    duplicates = await detector.find_duplicates(property_id, image_hashes)
    
    # Step 3: Store results and take action
    for match in duplicates:
        await detector.store_duplicate_detection(match)
        
        # Auto-suspend if very high confidence
        if match.similarity_score > 0.95:
            print(f"HIGH CONFIDENCE DUPLICATE: {property_id} matches {match.property_b_id}")
            # await suspend_property(property_id, reason="Duplicate listing detected")
    
    return duplicates
```

---

## 2. Property Verification Score

> **STACK-001:** production scoring runs in Rust (`afe_native.verification_score`); weights stay in Python config and are passed on each call. Release 1 sets `ml_anomaly` to 0 until a model is trained (Project Statement 6.1). The Python code below is the reference implementation.

### Weighted Scoring Algorithm

```python
"""
verification_scorer.py

Calculates a trust score (0-100) for property listings.
Higher score = more trustworthy.
"""

from pydantic import BaseModel
from typing import Optional, Dict, List
import asyncpg
from datetime import datetime
import json

class PropertyData(BaseModel):
    """Input data for scoring."""
    property_id: str
    owner_id: str
    has_title_deed: bool
    title_deed_verified: bool
    matches_land_registry: bool
    has_street_view_photos: bool
    gps_verified: bool
    gps_accuracy_meters: Optional[float]
    photo_count: int
    price: float
    market_avg_price: float
    market_price_range: tuple  # (min, max)
    agent_completed_transactions: int
    agent_dispute_count: int
    agent_reputation_score: int
    listing_duration_hours: float
    description_length: int

class VerificationScorer:
    """
    Calculate property verification score using weighted components.
    
    Components:
    1. Document Verification (30%)
    2. Agent Reputation (25%)
    3. Property Metadata (20%)
    4. Market Analysis (15%)
    5. ML Anomaly Detection (10%)
    """
    
    # Weights (must sum to 1.0)
    WEIGHTS = {
        'document': 0.30,
        'agent_reputation': 0.25,
        'property_metadata': 0.20,
        'market_analysis': 0.15,
        'ml_anomaly': 0.10
    }
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
    
    def score_documents(self, data: PropertyData) -> int:
        """
        Document verification score (0-100).
        
        Scoring:
        - Has title deed: +30
        - Title deed verified by admin: +40
        - Matches land registry API: +30
        """
        score = 0
        
        if data.has_title_deed:
            score += 30
        
        if data.title_deed_verified:
            score += 40
        
        if data.matches_land_registry:
            score += 30
        
        return min(100, score)
    
    def score_agent_reputation(self, data: PropertyData) -> int:
        """
        Agent reputation score (0-100).
        
        Based on:
        - Completed transactions (positive signal)
        - Disputes (negative signal)
        - Overall reputation score
        """
        score = data.agent_reputation_score  # Start with existing score (0-100)
        
        # Bonus for successful transactions
        transaction_bonus = min(20, data.agent_completed_transactions * 2)
        score += transaction_bonus
        
        # Penalty for disputes
        dispute_penalty = data.agent_dispute_count * 10
        score -= dispute_penalty
        
        return max(0, min(100, score))
    
    def score_property_metadata(self, data: PropertyData) -> int:
        """
        Property metadata quality score (0-100).
        
        Checks:
        - Street view photos
        - GPS verification
        - Photo count (too few or too many is suspicious)
        - Description length
        """
        score = 0
        
        # Street view photos (harder to fake)
        if data.has_street_view_photos:
            score += 25
        
        # GPS verification
        if data.gps_verified:
            score += 20
            
            # Bonus for high accuracy
            if data.gps_accuracy_meters and data.gps_accuracy_meters < 10:
                score += 10
        
        # Photo count (sweet spot: 5-15 photos)
        if 5 <= data.photo_count <= 15:
            score += 20
        elif data.photo_count < 3:
            score -= 20  # Too few photos is suspicious
        elif data.photo_count > 20:
            score -= 15  # Too many photos (common scam tactic)
        
        # Description length (100-1000 chars is good)
        if 100 <= data.description_length <= 1000:
            score += 15
        elif data.description_length < 50:
            score -= 10  # Too brief
        
        return max(0, min(100, score))
    
    def score_market_analysis(self, data: PropertyData) -> int:
        """
        Market price analysis score (0-100).
        
        Checks if price is within reasonable market range.
        Too cheap = likely scam. Too expensive = overpriced but not fraud.
        """
        score = 50  # Start neutral
        
        min_price, max_price = data.market_price_range
        
        # Price within normal range
        if min_price <= data.price <= max_price:
            score += 40
        
        # Price near market average
        price_deviation = abs(data.price - data.market_avg_price) / data.market_avg_price
        if price_deviation < 0.10:  # Within 10% of average
            score += 10
        
        # RED FLAG: Price too low (>40% below market)
        if data.price < min_price * 0.6:
            score -= 50  # Major red flag for scams
        
        return max(0, min(100, score))
    
    async def score_ml_anomaly(self, data: PropertyData) -> int:
        """
        ML-based anomaly detection score (0-100).
        
        Uses Isolation Forest to detect outliers.
        See anomaly_detector.py for full implementation.
        """
        # Placeholder - will be implemented with full ML pipeline
        # For now, use simple heuristics
        
        score = 50  # Start neutral
        
        # Flag: New agent with high-value property
        if data.agent_completed_transactions == 0 and data.price > data.market_avg_price * 1.5:
            score -= 30
        
        # Flag: Very fast listing (created in <10 minutes)
        if data.listing_duration_hours < 0.17:  # 10 minutes
            score -= 20
        
        return max(0, min(100, score))
    
    async def calculate_total_score(self, data: PropertyData) -> Dict:
        """
        Calculate weighted total score and risk classification.
        
        Returns:
            {
                'total_score': int (0-100),
                'risk_level': str ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'),
                'component_scores': dict,
                'active_flags': list
            }
        """
        # Calculate component scores
        components = {
            'document_score': self.score_documents(data),
            'agent_reputation_score': self.score_agent_reputation(data),
            'property_metadata_score': self.score_property_metadata(data),
            'market_analysis_score': self.score_market_analysis(data),
            'ml_anomaly_score': await self.score_ml_anomaly(data)
        }
        
        # Weighted total
        total_score = int(
            components['document_score'] * self.WEIGHTS['document'] +
            components['agent_reputation_score'] * self.WEIGHTS['agent_reputation'] +
            components['property_metadata_score'] * self.WEIGHTS['property_metadata'] +
            components['market_analysis_score'] * self.WEIGHTS['market_analysis'] +
            components['ml_anomaly_score'] * self.WEIGHTS['ml_anomaly']
        )
        
        # Risk classification
        if total_score >= 80:
            risk_level = 'LOW'
        elif total_score >= 60:
            risk_level = 'MEDIUM'
        elif total_score >= 40:
            risk_level = 'HIGH'
        else:
            risk_level = 'CRITICAL'
        
        # Identify active flags
        flags = []
        if not data.has_title_deed:
            flags.append('no_title_deed')
        if data.agent_dispute_count > 0:
            flags.append('agent_has_disputes')
        if data.price < data.market_price_range[0] * 0.6:
            flags.append('price_too_low')
        if data.photo_count < 3:
            flags.append('insufficient_photos')
        if data.agent_completed_transactions == 0:
            flags.append('new_agent')
        
        return {
            'total_score': total_score,
            'risk_level': risk_level,
            'component_scores': components,
            'active_flags': flags,
            'score_breakdown': {
                'document': f"{components['document_score']} * {self.WEIGHTS['document']} = {components['document_score'] * self.WEIGHTS['document']:.1f}",
                'agent': f"{components['agent_reputation_score']} * {self.WEIGHTS['agent_reputation']} = {components['agent_reputation_score'] * self.WEIGHTS['agent_reputation']:.1f}",
                'metadata': f"{components['property_metadata_score']} * {self.WEIGHTS['property_metadata']} = {components['property_metadata_score'] * self.WEIGHTS['property_metadata']:.1f}",
                'market': f"{components['market_analysis_score']} * {self.WEIGHTS['market_analysis']} = {components['market_analysis_score'] * self.WEIGHTS['market_analysis']:.1f}",
                'ml': f"{components['ml_anomaly_score']} * {self.WEIGHTS['ml_anomaly']} = {components['ml_anomaly_score'] * self.WEIGHTS['ml_anomaly']:.1f}"
            }
        }
    
    async def store_fraud_score(
        self, 
        property_id: str, 
        score_data: Dict
    ) -> None:
        """
        Store fraud score in database.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO fraud_scores (
                    property_id,
                    total_score,
                    document_score,
                    agent_reputation_score,
                    property_metadata_score,
                    market_analysis_score,
                    ml_anomaly_score,
                    score_breakdown,
                    risk_level,
                    active_flags,
                    calculated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """,
                property_id,
                score_data['total_score'],
                score_data['component_scores']['document_score'],
                score_data['component_scores']['agent_reputation_score'],
                score_data['component_scores']['property_metadata_score'],
                score_data['component_scores']['market_analysis_score'],
                score_data['component_scores']['ml_anomaly_score'],
                json.dumps(score_data['score_breakdown']),
                score_data['risk_level'],
                json.dumps(score_data['active_flags'])
            )
```

---

## 3. ML-Based Anomaly Detection

### Isolation Forest Implementation

```python
"""
anomaly_detector.py

Machine learning model to detect fraudulent property listings.
Uses Isolation Forest algorithm for unsupervised anomaly detection.
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import asyncpg
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class PropertyFeatures:
    """Feature vector for ML model."""
    price_per_sqm: float
    listing_duration_hours: float
    seller_account_age_days: float
    photo_count: int
    description_length: int
    response_time_minutes: float
    location_deviation_km: float  # Distance from claimed location to GPS
    price_deviation_pct: float    # % deviation from market average

class AnomalyDetector:
    """
    Detects anomalous property listings using Isolation Forest.
    
    Algorithm: Isolation Forest
    - Unsupervised learning (doesn't need labeled fraud data)
    - Isolates anomalies by randomly selecting features and split values
    - Anomalies are easier to isolate (require fewer splits)
    - Returns anomaly score: -1 to 1 (-1 = anomaly, 1 = normal)
    """
    
    MODEL_PATH = '/home/claude/models/anomaly_detector.pkl'
    SCALER_PATH = '/home/claude/models/feature_scaler.pkl'
    
    def __init__(self, contamination: float = 0.05):
        """
        Args:
            contamination: Expected proportion of anomalies (default 5%)
        """
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
            max_samples='auto',
            n_jobs=-1  # Use all CPU cores
        )
        self.scaler = StandardScaler()
        self.is_trained = False
    
    def extract_features(self, property_data: Dict) -> np.ndarray:
        """
        Convert property data to feature vector.
        """
        features = PropertyFeatures(
            price_per_sqm=property_data['price'] / max(property_data['area_sqm'], 1),
            listing_duration_hours=property_data['listing_duration_hours'],
            seller_account_age_days=property_data['seller_account_age_days'],
            photo_count=property_data['photo_count'],
            description_length=property_data['description_length'],
            response_time_minutes=property_data.get('avg_response_time_minutes', 60),
            location_deviation_km=property_data.get('location_deviation_km', 0),
            price_deviation_pct=abs(
                (property_data['price'] - property_data['market_avg_price']) / 
                property_data['market_avg_price'] * 100
            )
        )
        
        return np.array([
            features.price_per_sqm,
            features.listing_duration_hours,
            features.seller_account_age_days,
            features.photo_count,
            features.description_length,
            features.response_time_minutes,
            features.location_deviation_km,
            features.price_deviation_pct
        ])
    
    async def train(self, db_pool: asyncpg.Pool) -> None:
        """
        Train model on historical property data.
        Should be run periodically (e.g., weekly) to update with latest data.
        """
        async with db_pool.acquire() as conn:
            # Get all properties from last 6 months
            properties = await conn.fetch("""
                SELECT 
                    p.id,
                    p.price,
                    p.area_sqm,
                    EXTRACT(EPOCH FROM (NOW() - p.created_at)) / 3600 AS listing_duration_hours,
                    EXTRACT(EPOCH FROM (p.created_at - u.created_at)) / 86400 AS seller_account_age_days,
                    jsonb_array_length(p.images) AS photo_count,
                    length(p.description) AS description_length,
                    
                    -- Market average for this city/property_type
                    (
                        SELECT AVG(price) 
                        FROM properties p2 
                        WHERE p2.city = p.city 
                        AND p2.property_type = p.property_type
                        AND p2.status = 'active'
                    ) AS market_avg_price,
                    
                    -- Location deviation (if available)
                    COALESCE(p.location_accuracy_meters / 1000, 0) AS location_deviation_km
                    
                FROM properties p
                JOIN users u ON u.id = p.owner_id
                WHERE p.created_at > NOW() - INTERVAL '6 months'
                    AND p.price > 0
                    AND p.area_sqm > 0
            """)
        
        # Extract features
        X = []
        for prop in properties:
            features = self.extract_features(dict(prop))
            X.append(features)
        
        X = np.array(X)
        
        # Standardize features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled)
        self.is_trained = True
        
        # Save model
        joblib.dump(self.model, self.MODEL_PATH)
        joblib.dump(self.scaler, self.SCALER_PATH)
        
        print(f"Model trained on {len(X)} properties")
    
    def load_model(self) -> None:
        """Load pre-trained model from disk."""
        self.model = joblib.load(self.MODEL_PATH)
        self.scaler = joblib.load(self.SCALER_PATH)
        self.is_trained = True
    
    def predict(self, property_data: Dict) -> Dict:
        """
        Predict if a property is anomalous.
        
        Returns:
            {
                'is_anomaly': bool,
                'anomaly_score': float,  # -1 to 1
                'risk_category': str,    # 'LOW', 'MEDIUM', 'HIGH'
                'confidence': float      # 0 to 1
            }
        """
        if not self.is_trained:
            raise ValueError("Model not trained. Call train() or load_model() first.")
        
        # Extract and scale features
        features = self.extract_features(property_data)
        features_scaled = self.scaler.transform([features])
        
        # Predict
        prediction = self.model.predict(features_scaled)[0]  # 1 or -1
        anomaly_score = self.model.decision_function(features_scaled)[0]
        
        # Classify risk
        if anomaly_score < -0.5:
            risk_category = 'HIGH'
        elif anomaly_score < 0:
            risk_category = 'MEDIUM'
        else:
            risk_category = 'LOW'
        
        # Confidence (how far from decision boundary)
        confidence = abs(anomaly_score)
        
        return {
            'is_anomaly': prediction == -1,
            'anomaly_score': float(anomaly_score),
            'risk_category': risk_category,
            'confidence': float(confidence)
        }


# Example usage
async def score_new_listing(property_id: str, db_pool: asyncpg.Pool):
    """
    Score a new property listing for fraud risk.
    """
    detector = AnomalyDetector()
    detector.load_model()
    
    # Get property data
    async with db_pool.acquire() as conn:
        property_data = await conn.fetchrow("""
            SELECT 
                p.id,
                p.price,
                p.area_sqm,
                EXTRACT(EPOCH FROM (NOW() - p.created_at)) / 3600 AS listing_duration_hours,
                EXTRACT(EPOCH FROM (p.created_at - u.created_at)) / 86400 AS seller_account_age_days,
                jsonb_array_length(p.images) AS photo_count,
                length(p.description) AS description_length,
                (
                    SELECT AVG(price) 
                    FROM properties p2 
                    WHERE p2.city = p.city 
                    AND p2.property_type = p.property_type
                ) AS market_avg_price
            FROM properties p
            JOIN users u ON u.id = p.owner_id
            WHERE p.id = $1
        """, property_id)
    
    # Predict
    result = detector.predict(dict(property_data))
    
    if result['is_anomaly'] and result['risk_category'] == 'HIGH':
        print(f"⚠️  HIGH RISK LISTING DETECTED: {property_id}")
        print(f"   Anomaly score: {result['anomaly_score']:.3f}")
        print(f"   Confidence: {result['confidence']:.3f}")
        
        # Auto-flag for review
        # await flag_for_moderation(property_id, reason="ML anomaly detection")
    
    return result
```

---

## 4. Fraud Ring Detection (Graph Analysis)

### Network Analysis with NetworkX

```python
"""
fraud_ring_detector.py

Detects coordinated fraud rings using graph-based analysis.
Identifies groups of users/properties with suspicious connections.
"""

import networkx as nx
from typing import List, Dict, Set
import asyncpg
from collections import defaultdict
from dataclasses import dataclass
import json

@dataclass
class FraudRing:
    network_id: str
    member_user_ids: List[str]
    shared_ips: List[str]
    shared_devices: List[str]
    confidence_score: float
    detection_algorithm: str
    network_density: float

class FraudRingDetector:
    """
    Detects fraud rings using graph analysis.
    
    Algorithms:
    1. Connected Components: Find groups of users with shared attributes
    2. Community Detection: Identify tightly-knit clusters
    3. Betweenness Centrality: Find key coordinators in fraud networks
    4. Cycle Detection: Identify circular transaction patterns (money laundering)
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.graph = nx.Graph()
    
    async def build_transaction_graph(self) -> nx.DiGraph:
        """
        Build directed graph of payment transactions.
        
        Nodes: users
        Edges: payment transactions (weighted by amount)
        """
        G = nx.DiGraph()
        
        async with self.db_pool.acquire() as conn:
            # Get escrow transactions
            transactions = await conn.fetch("""
                SELECT 
                    buyer_id,
                    seller_id,
                    total_amount,
                    payment_status,
                    created_at
                FROM escrow_transactions
                WHERE created_at > NOW() - INTERVAL '3 months'
                    AND payment_status = 'completed'
            """)
        
        for txn in transactions:
            G.add_edge(
                txn['buyer_id'],
                txn['seller_id'],
                amount=float(txn['total_amount']),
                timestamp=txn['created_at']
            )
        
        return G
    
    def detect_circular_transactions(self, G: nx.DiGraph) -> List[List[str]]:
        """
        Detect circular money flows (common in money laundering).
        
        Example: A → B → C → A
        """
        cycles = list(nx.simple_cycles(G))
        
        # Filter for significant cycles (>= 3 nodes, high total value)
        significant_cycles = []
        for cycle in cycles:
            if len(cycle) >= 3:
                # Calculate total value in cycle
                total_value = sum(
                    G[cycle[i]][cycle[(i+1) % len(cycle)]]['amount']
                    for i in range(len(cycle))
                )
                
                if total_value > 10000:  # Threshold (adjust per market)
                    significant_cycles.append(cycle)
        
        return significant_cycles
    
    def detect_hub_and_spoke(self, G: nx.DiGraph, threshold: int = 50) -> List[str]:
        """
        Detect hub-and-spoke patterns (one account receiving from many).
        Common in scam operations where victims pay a central account.
        """
        suspicious_hubs = []
        
        for node in G.nodes():
            in_degree = G.in_degree(node)
            out_degree = G.out_degree(node)
            
            # High inflow, low outflow = potential scam hub
            if in_degree > threshold and out_degree < 5:
                suspicious_hubs.append(node)
        
        return suspicious_hubs
    
    async def build_similarity_graph(self) -> nx.Graph:
        """
        Build undirected graph based on user similarities.
        
        Users are connected if they share:
        - IP addresses
        - Device fingerprints
        - Bank accounts
        - Phone numbers
        - Operating patterns (same listing times, etc.)
        """
        G = nx.Graph()
        
        async with self.db_pool.acquire() as conn:
            # Get user connections via shared attributes
            
            # 1. Shared IP addresses
            shared_ips = await conn.fetch("""
                SELECT 
                    ub1.user_id AS user_a,
                    ub2.user_id AS user_b,
                    ub1.ip_address
                FROM user_behaviors ub1
                JOIN user_behaviors ub2 ON ub1.ip_address = ub2.ip_address
                WHERE ub1.user_id < ub2.user_id
                    AND ub1.occurred_at > NOW() - INTERVAL '30 days'
                GROUP BY ub1.user_id, ub2.user_id, ub1.ip_address
                HAVING COUNT(*) > 5  -- Multiple sessions from same IP
            """)
            
            for row in shared_ips:
                G.add_edge(
                    row['user_a'],
                    row['user_b'],
                    reason='shared_ip',
                    ip=str(row['ip_address'])
                )
            
            # 2. Shared device fingerprints
            shared_devices = await conn.fetch("""
                SELECT DISTINCT
                    ub1.user_id AS user_a,
                    ub2.user_id AS user_b,
                    ub1.device_fingerprint
                FROM user_behaviors ub1
                JOIN user_behaviors ub2 ON ub1.device_fingerprint = ub2.device_fingerprint
                WHERE ub1.user_id < ub2.user_id
                    AND ub1.device_fingerprint IS NOT NULL
            """)
            
            for row in shared_devices:
                G.add_edge(
                    row['user_a'],
                    row['user_b'],
                    reason='shared_device',
                    device=row['device_fingerprint']
                )
        
        return G
    
    def detect_connected_components(self, G: nx.Graph) -> List[Set[str]]:
        """
        Find all connected components (groups of related users).
        """
        components = list(nx.connected_components(G))
        
        # Filter for suspicious components (size >= 3)
        suspicious_components = [c for c in components if len(c) >= 3]
        
        return suspicious_components
    
    def calculate_network_metrics(self, G: nx.Graph, nodes: Set[str]) -> Dict:
        """
        Calculate metrics for a subgraph (potential fraud ring).
        """
        subgraph = G.subgraph(nodes)
        
        # Network density (0 to 1, higher = more interconnected)
        density = nx.density(subgraph)
        
        # Average clustering coefficient
        try:
            clustering = nx.average_clustering(subgraph)
        except:
            clustering = 0
        
        # Identify central figures (highest degree)
        degrees = dict(subgraph.degree())
        central_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            'density': density,
            'clustering': clustering,
            'central_nodes': central_nodes,
            'edge_count': subgraph.number_of_edges(),
            'node_count': subgraph.number_of_nodes()
        }
    
    async def detect_fraud_rings(self) -> List[FraudRing]:
        """
        Main detection pipeline.
        """
        # Build similarity graph
        G = await self.build_similarity_graph()
        
        # Find connected components
        components = self.detect_connected_components(G)
        
        fraud_rings = []
        
        for component in components:
            # Calculate metrics
            metrics = self.calculate_network_metrics(G, component)
            
            # High density + high clustering = likely coordinated
            if metrics['density'] > 0.5 and metrics['clustering'] > 0.6:
                # Gather shared attributes
                shared_ips = set()
                shared_devices = set()
                
                for u, v, data in G.subgraph(component).edges(data=True):
                    if data.get('reason') == 'shared_ip':
                        shared_ips.add(data['ip'])
                    if data.get('reason') == 'shared_device':
                        shared_devices.add(data['device'])
                
                fraud_ring = FraudRing(
                    network_id=str(min(component)),  # Use min user_id as network ID
                    member_user_ids=list(component),
                    shared_ips=list(shared_ips),
                    shared_devices=list(shared_devices),
                    confidence_score=metrics['density'] * metrics['clustering'],
                    detection_algorithm='connected_components',
                    network_density=metrics['density']
                )
                
                fraud_rings.append(fraud_ring)
        
        return fraud_rings
    
    async def store_fraud_network(self, ring: FraudRing) -> None:
        """
        Store detected fraud ring in database.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO fraud_networks (
                    network_id,
                    network_name,
                    member_user_ids,
                    member_count,
                    shared_ip_addresses,
                    shared_devices,
                    detection_algorithm,
                    confidence_score,
                    network_density,
                    status,
                    detected_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'detected', NOW())
            """,
                ring.network_id,
                f"Network {ring.network_id[:8]}",
                ring.member_user_ids,
                len(ring.member_user_ids),
                ring.shared_ips,
                ring.shared_devices,
                ring.detection_algorithm,
                ring.confidence_score,
                ring.network_density
            )


# Example: Run fraud ring detection
async def run_fraud_ring_detection(db_pool: asyncpg.Pool):
    """
    Periodic job to detect fraud rings (run daily or weekly).
    """
    detector = FraudRingDetector(db_pool)
    
    fraud_rings = await detector.detect_fraud_rings()
    
    for ring in fraud_rings:
        print(f"🚨 Fraud ring detected: {len(ring.member_user_ids)} members")
        print(f"   Confidence: {ring.confidence_score:.2f}")
        print(f"   Shared IPs: {len(ring.shared_ips)}")
        print(f"   Shared devices: {len(ring.shared_devices)}")
        
        await detector.store_fraud_network(ring)
        
        # High-confidence rings: auto-suspend users
        if ring.confidence_score > 0.8:
            print(f"   ⚠️  HIGH CONFIDENCE - Flagging for immediate review")
            # await suspend_users(ring.member_user_ids, reason="Fraud ring detected")
```

---

## Performance & Optimization

### Caching Fraud Scores with Redis

```python
"""
fraud_cache.py

Cache fraud scores in Redis for fast lookups.
"""

import redis.asyncio as redis
import json
from typing import Optional, Dict

class FraudScoreCache:
    """
    Cache fraud scores in Redis to avoid re-computation.
    TTL: 1 hour (scores expire and need recalculation)
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.ttl = 3600  # 1 hour
    
    async def get_score(self, property_id: str) -> Optional[Dict]:
        """Get cached fraud score."""
        key = f"fraud_score:{property_id}"
        data = await self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def set_score(self, property_id: str, score_data: Dict) -> None:
        """Cache fraud score with TTL."""
        key = f"fraud_score:{property_id}"
        await self.redis.setex(
            key,
            self.ttl,
            json.dumps(score_data)
        )
    
    async def invalidate(self, property_id: str) -> None:
        """Invalidate cached score (e.g., after property update)."""
        key = f"fraud_score:{property_id}"
        await self.redis.delete(key)
```

---

## Summary

**Algorithms Implemented**:
1. ✅ Duplicate Image Detection (perceptual hashing)
2. ✅ Property Verification Score (weighted algorithm)
3. ✅ ML Anomaly Detection (Isolation Forest)
4. ✅ Fraud Ring Detection (graph analysis)
5. ✅ Caching layer (Redis)

**Performance Targets**:
- Duplicate detection: <500ms
- Verification scoring: <200ms
- ML prediction: <100ms (cached model)
- Graph analysis: Run offline (batch job)

**Next Steps**:
1. Integrate with FastAPI endpoints (see api-design.md)
2. Set up model training pipeline (weekly retraining)
3. Deploy Redis for caching
4. Configure alerting for high-risk detections
