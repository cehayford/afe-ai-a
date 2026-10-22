# House Agent - Product Roadmap & Timeline

> **Superseded:** the timeline in this file is replaced by Section 11 of `Afe_Project_Statement_v3.3.docx`.
> **Stack update (STACK-001, Sept 2026):** backend = Python (FastAPI) + Rust native modules (`afe_native`, via PyO3); mobile = native Android (Kotlin + Jetpack Compose) and iOS (Swift + SwiftUI), replacing Flutter. See `Afe_Stack_Amendment_STACK-001.docx` and `Afe_Project_Statement_v3.3.docx`.

**Vision**: Build Africa's most trusted property platform with built-in fraud prevention

---

## 🎯 Product Phases

```
Phase 1: MVP          Phase 2: Beta        Phase 3: Launch      Phase 4: Scale
(Weeks 1-6)          (Weeks 7-12)         (Weeks 13-16)        (Months 5-12)
    │                    │                    │                    │
    ├─ Auth              ├─ Mobile App        ├─ Marketing         ├─ Multi-region
    ├─ Properties        ├─ Messaging         ├─ 1000 users        ├─ Microservices
    ├─ Search            ├─ ML Fraud          ├─ Performance       ├─ AI Features
    ├─ Escrow            ├─ Analytics         ├─ Security Audit    ├─ Enterprise
    └─ Admin             └─ Agent Tools       └─ Go Live           └─ White-label
```

---

## Phase 1: MVP (Weeks 1-6) - Foundation

**Goal**: Validate core value proposition with 100 beta users

### Week 1-2: Infrastructure Setup ⚙️
```
Monday    Tuesday   Wednesday Thursday  Friday
────────────────────────────────────────────────
AWS Setup → DB Init → Redis    → Docker  → CI/CD
Domains   → Schemas → Celery   → Testing → Deploy
SSL Certs → Seed    → Search   → Docs    → Monitor
```

**Deliverables**:
- [x] AWS account + VPC configured
- [x] PostgreSQL RDS with PostGIS
- [x] Redis ElastiCache
- [x] Docker images built
- [x] GitHub Actions CI/CD
- [x] Staging environment live

**Team**: 1 DevOps engineer

---

### Week 3-4: Core Backend 🔧
```
Authentication     Properties         Fraud Detection
     │                 │                    │
     ├─ Register       ├─ Create            ├─ Image Hash
     ├─ Login          ├─ Edit              ├─ Verify Score
     ├─ JWT            ├─ Delete            ├─ Duplicate Check
     ├─ OAuth          ├─ Search            └─ Auto-approve
     └─ 2FA            └─ Filter
```

**API Endpoints** (20+):
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/properties/search
- POST /api/v1/properties
- PUT /api/v1/properties/:id
- POST /api/v1/escrow
- GET /api/v1/fraud/score/:id

**Deliverables**:
- [x] User authentication working
- [x] Property CRUD complete
- [x] Search with filters (city, price, type)
- [x] Fraud detection (basic scoring)
- [x] API documentation (Swagger)

**Team**: 2 backend engineers

---

### Week 5-6: Frontend MVP 🎨
```
Public Site              Web App               Admin
    │                       │                    │
    ├─ Homepage             ├─ Dashboard         ├─ Users
    ├─ Search Results       ├─ My Properties     ├─ Properties
    ├─ Property Detail      ├─ Messages          ├─ Moderation
    └─ Register/Login       └─ Settings          └─ Analytics
```

**Pages** (15):
- Public: 5 pages
- Web app: 7 screens
- Admin: 3 dashboards

**Deliverables**:
- [x] SvelteKit app deployed
- [x] Responsive design (mobile + desktop)
- [x] Property search working
- [x] User registration flow
- [x] Admin can moderate listings

**Team**: 1 frontend engineer + 1 designer

---

### Week 6: Testing & Polish ✨
**Focus**: Bug fixes, performance, UX improvements

**Testing Checklist**:
- [ ] Unit tests (80%+ coverage)
- [ ] Integration tests (API endpoints)
- [ ] E2E tests (critical user flows)
- [ ] Load testing (100 concurrent users)
- [ ] Security scanning (OWASP)
- [ ] Accessibility (WCAG 2.1 AA)

**Performance Targets**:
- API response: <200ms (P95)
- Page load: <2.5s (3G network)
- Search: <100ms

**Deliverables**:
- [x] 100 beta users invited
- [x] First 10 properties listed
- [x] Feedback collected
- [x] Bugs prioritized

---

## Phase 2: Beta (Weeks 7-12) - Product-Market Fit

**Goal**: Reach 1,000 active users, validate fraud prevention

### Week 7-8: Mobile App 📱
```
Native Apps (Android: Kotlin + Compose, iOS: Swift + SwiftUI)
    │
    ├─ Authentication (OAuth)
    ├─ Property Search (Map view)
    ├─ Favorites & Saved Searches
    ├─ Real-time Messaging
    ├─ Push Notifications
    └─ Offline Mode (PWA)
```

**Screens** (20+):
- Onboarding (3 slides)
- Auth (login, register, forgot password)
- Main tabs (5): Home, Search, Favorites, Messages, Profile
- Property detail (with image gallery)
- Agent profile
- Messaging threads
- Payment flow

**Deliverables**:
- [x] iOS app in TestFlight
- [x] Android app in internal testing
- [x] 50 mobile beta testers
- [x] Push notifications working
- [x] Offline property viewing

**Team**: 1 mobile engineer

---

### Week 9-10: Advanced Fraud Detection 🕵️
```
ML Pipeline
    │
    ├─ Data Collection (6 months history)
    ├─ Feature Engineering (8 features)
    ├─ Model Training (Isolation Forest)
    ├─ Model Evaluation (95%+ accuracy)
    └─ Deployment (Real-time scoring)

Graph Analysis
    │
    ├─ Build User Network
    ├─ Detect Fraud Rings
    ├─ Community Detection
    └─ Alert System
```

**ML Features**:
- Price per sqm
- Listing duration
- Agent reputation
- Photo quality
- Description sentiment
- GPS accuracy
- Price deviation
- Behavior patterns

**Deliverables**:
- [x] ML model trained (Isolation Forest)
- [x] Graph fraud detection live
- [x] 10+ fraud rings detected
- [x] 95%+ fraud detection accuracy
- [x] Automated moderation working

**Team**: 1 ML engineer

---

### Week 11-12: Agent Tools & Analytics 📊
```
Agent Portal
    │
    ├─ CRM (Client Management)
    ├─ Lead Pipeline (Kanban)
    ├─ Performance Dashboard
    ├─ Marketing Tools
    └─ Commission Tracker

Analytics
    │
    ├─ User Growth
    ├─ Property Metrics
    ├─ Conversion Funnels
    ├─ Fraud Prevention Impact
    └─ Revenue Tracking
```

**Agent Features**:
- Manage multiple listings
- Track inquiries
- Schedule inspections
- Generate property flyers
- WhatsApp integration
- Commission calculator

**Deliverables**:
- [x] Agent portal live
- [x] 50 agents onboarded
- [x] Analytics dashboard
- [x] Conversion tracking
- [x] A/B testing framework

**Team**: 1 backend engineer + 1 frontend engineer

---

## Phase 3: Launch (Weeks 13-16) - Go to Market

**Goal**: Launch in Nigeria (Lagos), reach 5,000 users

### Week 13: Performance & Security 🔒
```
Performance Optimization          Security Hardening
        │                                │
        ├─ Database indexes              ├─ Penetration testing
        ├─ Query optimization            ├─ OWASP compliance
        ├─ Redis caching                 ├─ Rate limiting
        ├─ CDN setup                     ├─ DDoS protection
        └─ Load testing (10k users)      └─ Security audit
```

**Performance Checklist**:
- [ ] Database queries <50ms
- [ ] API response <200ms (P95)
- [ ] Page load <2.5s (LCP)
- [ ] Handles 10k concurrent users
- [ ] CDN cache hit ratio >80%

**Security Checklist**:
- [ ] Penetration test passed
- [ ] OWASP Top 10 addressed
- [ ] SSL/TLS configured
- [ ] Rate limiting active
- [ ] Audit logs enabled
- [ ] Backup tested (daily)

**Deliverables**:
- [x] Performance targets met
- [x] Security audit passed
- [x] Bug bounty program launched
- [x] Incident response plan

**Team**: 1 DevOps + 1 security consultant

---

### Week 14-15: Marketing & Growth 📣
```
Marketing Channels
    │
    ├─ Content Marketing
    │   ├─ Blog posts (10)
    │   ├─ Property guides
    │   └─ SEO optimization
    │
    ├─ Social Media
    │   ├─ Instagram (property photos)
    │   ├─ Twitter (tips, news)
    │   └─ Facebook (groups)
    │
    ├─ Partnerships
    │   ├─ Real estate agencies
    │   ├─ Property developers
    │   └─ Banks (mortgages)
    │
    └─ Paid Advertising
        ├─ Google Ads
        ├─ Facebook Ads
        └─ Instagram Ads
```

**Growth Tactics**:
1. **Referral Program**: ₦10,000 for each agent referred
2. **Content**: "How to spot rental scams in Lagos"
3. **Partnerships**: 10 agencies onboarded
4. **Events**: Lagos property expo booth
5. **PR**: TechCabal, Techpoint Africa coverage

**Deliverables**:
- [x] 1,000 users acquired
- [x] 500 properties listed
- [x] 50 agents active
- [x] Press coverage (3 articles)
- [x] Social media (5k followers)

**Team**: 1 growth marketer + 1 content creator

---

### Week 16: Launch! 🚀
```
Launch Day Checklist
    │
    ├─ 8am: Press release sent
    ├─ 10am: Website traffic surge
    ├─ 12pm: Mobile app featured
    ├─ 2pm: First escrow payment
    ├─ 4pm: Support team active
    └─ 6pm: Monitoring dashboards
```

**Launch Metrics** (24 hours):
- Target: 500 new signups
- Target: 100 properties listed
- Target: 10 agents registered
- Target: 5 successful transactions
- Target: 99.9% uptime

**Deliverables**:
- [x] Public launch (Lagos, Nigeria)
- [x] App stores (iOS + Android)
- [x] Press coverage live
- [x] Support team ready
- [x] Monitoring active

**Team**: Full team (8 people)

---

## Phase 4: Scale (Months 5-12) - Expansion

**Goal**: Multi-country expansion, 50,000 users, profitability

### Month 5-6: Ghana Expansion 🇬🇭
```
Localization
    │
    ├─ Currency: GHS
    ├─ Payments: Flutterwave, Paystack
    ├─ Languages: English, Twi, Ga
    ├─ Property Types: Chamber & Hall, Self-contained
    └─ Compliance: Data Protection Act 2012
```

**Deliverables**:
- [x] Ghana launched (Accra)
- [x] 5,000 users (Ghana)
- [x] 50 agents (Ghana)
- [x] Local payment methods
- [x] Twi language support

---

### Month 7-8: Kenya Expansion 🇰🇪
```
M-Pesa Integration
    │
    ├─ Consumer Key/Secret
    ├─ Shortcode setup
    ├─ STK Push
    ├─ C2B payments
    └─ Balance checks
```

**Deliverables**:
- [x] Kenya launched (Nairobi)
- [x] M-Pesa working
- [x] Swahili language
- [x] 10,000 users (Kenya)

---

### Month 9-10: Microservices & Performance ⚡
```
Architecture Evolution
    │
    ├─ FastAPI (Business logic)
    ├─ Go (Real-time feed, WebSockets)
    ├─ GraphQL (Mobile API)
    ├─ gRPC (Internal services)
    └─ Event streaming (Kafka)
```

**Deliverables**:
- [x] Hot paths migrated to Go
- [x] GraphQL API for mobile
- [x] Event-driven architecture
- [x] Handles 50k concurrent users

---

### Month 11-12: AI & Enterprise 🤖
```
AI Features
    │
    ├─ Property recommendations
    ├─ Price predictions
    ├─ Virtual staging
    ├─ Chatbot support
    └─ Smart matching

Enterprise
    │
    ├─ White-label solution
    ├─ API for partners
    ├─ Custom domains
    ├─ Dedicated support
    └─ SLA guarantees
```

**Deliverables**:
- [x] AI recommendations live
- [x] 5 enterprise clients
- [x] $1M monthly GMV
- [x] Profitability achieved

---

## 📊 Success Metrics by Phase

> **Withdrawn (Sept 2026):** the revenue figures in the table below were written before the plan changed and have no
> working behind them. Use Section 12.4 of the Statement and `Afe_Unit_Economics_Model.xlsx` instead.

| Phase | Users | Properties | Transactions | Revenue/Month |
|-------|-------|------------|--------------|---------------|
| **MVP** (Week 6) | 100 | 50 | 5 | $500 |
| **Beta** (Week 12) | 1,000 | 500 | 50 | $5,000 |
| **Launch** (Week 16) | 5,000 | 2,000 | 200 | $20,000 |
| **Scale** (Month 6) | 25,000 | 10,000 | 1,000 | $100,000 |
| **Expansion** (Month 12) | 50,000 | 25,000 | 2,500 | $250,000 |

---

## 👥 Team Evolution

### Phase 1: MVP (6 people)
- 1 Product Manager
- 2 Backend Engineers (Python/FastAPI; at least one with Rust)
- 1 Frontend Engineer (SvelteKit)
- 1 Android Engineer (Kotlin)
- 1 iOS Engineer (Swift) — can join after foundations
- 1 DevOps Engineer

### Phase 2: Beta (8 people)
- +1 ML Engineer
- +1 Designer

### Phase 3: Launch (12 people)
- +1 Growth Marketer
- +1 Content Creator
- +1 Customer Support
- +1 Security Consultant (contract)

### Phase 4: Scale (20 people)
- +2 Backend Engineers
- +1 Frontend Engineer
- +1 Mobile Engineer (Android or iOS, whichever lags)
- +2 Customer Support
- +1 Data Analyst
- +1 Sales Manager

---

## 💰 Budget Breakdown

### Phase 1: MVP ($50k)
- Team salaries: $35k
- Infrastructure: $2k
- Tools & software: $3k
- Legal & compliance: $5k
- Marketing: $5k

### Phase 2: Beta ($80k)
- Team salaries: $60k
- Infrastructure: $5k
- Marketing: $10k
- Other: $5k

### Phase 3: Launch ($150k)
- Team salaries: $90k
- Infrastructure: $10k
- Marketing: $40k
- Events & PR: $10k

### Phase 4: Scale ($500k)
- Team salaries: $300k
- Infrastructure: $50k
- Marketing: $100k
- Expansion: $50k

**Total Year 1 Budget**: ~$780k

---

## 🎯 Exit Criteria per Phase

### MVP → Beta
- [ ] 100 active users
- [ ] 50 properties listed
- [ ] 5 successful transactions
- [ ] Fraud detection working
- [ ] 80%+ user satisfaction

### Beta → Launch
- [ ] 1,000 active users
- [ ] 500 properties
- [ ] 50 transactions
- [ ] Mobile app in stores
- [ ] ML model trained

### Launch → Scale
- [ ] 5,000 users
- [ ] 2,000 properties
- [ ] 200 transactions
- [ ] $20k/month revenue
- [ ] Security audit passed

### Scale → Profitability
- [ ] 50,000 users
- [ ] 25,000 properties
- [ ] 2,500 transactions
- [ ] $250k/month revenue
- [ ] Profitable (cash flow positive)

---

## 🚀 Critical Path

```
Week 1-2: Infrastructure ─┐
                          │
Week 3-4: Backend API ────┼─► Week 5-6: Frontend ─► Week 6: MVP Launch
                          │
Week 7-8: Mobile App ─────┘

Week 9-10: ML Fraud ──┐
                       │
Week 11-12: Analytics ┴─► Week 13: Performance ─► Week 16: Public Launch

Month 5-6: Ghana ──┐
                    │
Month 7-8: Kenya ───┼─► Month 9-10: Microservices ─► Month 12: Profitability
                    │
Month 11: AI ───────┘
```

---

## 📅 Key Milestones

| Date | Milestone | Impact |
|------|-----------|--------|
| **Week 6** | MVP Launch | Product validation |
| **Week 12** | Beta Complete | Product-market fit |
| **Week 16** | Public Launch | Market entry (Nigeria) |
| **Month 6** | Ghana Launch | Multi-country proof |
| **Month 9** | 25k Users | Scale validation |
| **Month 12** | Profitability | Business validation |

---

**This roadmap is aggressive but achievable with the right team and execution.** 🚀
