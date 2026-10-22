# House Agent - Complete Page Structure & Sitemap

**Platform**: African Property SaaS (Web + Mobile + Admin)  
**Version**: 1.0  
**Last Updated**: 2024

---

## Table of Contents
1. [Public Marketing Website](#public-marketing-website)
2. [Web Application (Authenticated)](#web-application)
3. [Mobile Application Screens](#mobile-application)
4. [Admin Dashboard](#admin-dashboard)
5. [API Documentation Portal](#api-documentation)
6. [Agent Portal](#agent-portal)

---

## 1. Public Marketing Website

### Homepage (`/`)
**Purpose**: Convert visitors to users  
**Components**:
- Hero section with property search bar
- Trust indicators (verification badges, user count, transaction volume)
- Featured properties (6-8 listings)
- How it works (3-step process)
- Safety features highlight (fraud detection, escrow)
- Testimonials (carousel)
- Download app CTAs (iOS + Android)
- Footer with links

**CTAs**: "Find a Home", "List Your Property", "Download App"

---

### Search Results (`/search`)
**Purpose**: Browse and filter properties  
**URL Pattern**: `/search?city=Lagos&type=apartment&max_price=500000`

**Components**:
- Filter sidebar:
  - Location (city, state)
  - Price range (slider)
  - Property type (dropdown)
  - Bedrooms/bathrooms
  - Amenities (checkboxes)
  - Verification score filter (>60, >80)
- Map view toggle
- List/grid view toggle
- Sort options (price, date, verification score)
- Property cards (image, title, price, location, verification badge)
- Pagination
- Save search option (authenticated users)

**Sticky Elements**: Filter bar, sort dropdown

---

### Property Detail (`/properties/:id`)
**Purpose**: Full property information  
**URL Pattern**: `/properties/uuid-123`

**Components**:
- Image gallery (lightbox, 360° view if available)
- Property title + verification score badge
- Price + currency
- Key details grid:
  - Bedrooms, bathrooms, area
  - Property type, listing type
  - Furnishing status
- Location map (interactive)
- Amenities list (icons)
- Description
- Verification details:
  - Documents (if verified)
  - GPS verification status
  - Fraud score breakdown (for transparency)
- Agent/Landlord card:
  - Name, photo, reputation score
  - Completed transactions
  - Response time
  - Contact button
- Similar properties
- Report property button
- Share buttons (WhatsApp, Twitter, Facebook)

**CTAs**: "Contact Agent", "Schedule Inspection", "Save to Favorites"

---

### About Us (`/about`)
**Components**:
- Mission statement
- Team photos + bios
- Company values
- Milestones (properties listed, users, transactions)
- Press mentions
- Contact information

---

### How It Works (`/how-it-works`)
**Sections**:
1. For Tenants:
   - Search verified properties
   - Contact agents
   - Secure payment via escrow
2. For Landlords:
   - List properties
   - Verification process
   - Get paid safely
3. For Agents:
   - Manage multiple listings
   - Build reputation
   - Commission structure

---

### Safety & Trust (`/safety`)
**Components**:
- Fraud detection explanation
- Verification process
- Escrow system breakdown
- User protection policies
- Success stories
- Fraud statistics (how many prevented)

---

### Pricing (`/pricing`)
**Tiers**:
1. **Free** (Tenants):
   - Unlimited property search
   - Contact agents
   - Save favorites

2. **Landlord/Agent** (Commission-based):
   - 3.5% platform fee on successful transactions (rate pending decision D6 - RFC-002 says 2.5%; one rate must win)
   - No upfront cost
   - Unlimited listings

3. **Premium Agent** (Monthly subscription):
   - $50/month or local equivalent (GHS price pending decision D22)
   - Featured listings
   - Analytics dashboard
   - Priority support
   - Verified badge

---

### Help Center (`/help`)
**Structure**:
- Search bar
- Categories:
  - Getting Started
  - Finding Properties
  - Listing Properties
  - Payments & Escrow
  - Account Settings
  - Safety & Security
  - Troubleshooting
- Popular articles
- Contact support (chat widget)

**Example Articles**:
- "How to verify a property is real"
- "Understanding verification scores"
- "How escrow payments work"
- "What to do if you suspect fraud"

---

### Blog (`/blog`)
**Categories**:
- Property Market Insights
- Renting Tips
- Landlord Guides
- African Real Estate News
- Platform Updates
- Safety Tips

**URL Pattern**: `/blog/:category/:slug`

---

### Careers (`/careers`)
**Components**:
- Company culture
- Open positions (job board)
- Benefits
- Application form

---

### Legal Pages
- Terms of Service (`/terms`)
- Privacy Policy (`/privacy`)
- Cookie Policy (`/cookies`)
- NDPR/GDPR Compliance (`/compliance`)
- Dispute Resolution (`/disputes`)

---

## 2. Web Application (Authenticated Users)

### Authentication

#### Sign Up (`/signup`)
**Forms**:
- Email + password
- First name, last name
- Phone number (with country code)
- Role selection (Tenant, Landlord, Agent)
- Country selection
- OAuth options (Google, Facebook)
- Terms acceptance checkbox

**Flow**: Email verification → Profile setup → Onboarding

---

#### Login (`/login`)
**Components**:
- Email + password
- "Remember me" checkbox
- Forgot password link
- OAuth options
- Two-factor authentication (if enabled)

---

#### Forgot Password (`/forgot-password`)
**Flow**: Enter email → Check inbox → Reset password page

---

### User Dashboard

#### Dashboard Home (`/dashboard`)
**For Tenants**:
- Saved properties (grid)
- Recent searches
- Recommended properties (based on preferences)
- Scheduled inspections
- Inquiry status tracker
- Notifications bell

**For Landlords**:
- Active listings (table)
- Pending verifications
- Inquiry inbox
- Payment requests
- Analytics (views, inquiries, conversions)

**For Agents**:
- All listings (multi-property view)
- Lead pipeline (kanban board)
- Commission tracker
- Performance metrics
- Client management

---

#### My Properties (`/dashboard/properties`)
**For Landlords/Agents**:
- All properties table (status, views, inquiries)
- Filters (status, date, verification)
- Actions: Edit, Duplicate, Archive, Delete
- Create new property button

---

#### Create/Edit Property (`/dashboard/properties/new` or `/dashboard/properties/:id/edit`)
**Multi-step Form**:

**Step 1: Basic Information**
- Title
- Description (rich text editor)
- Property type
- Listing type (rent/sale)

**Step 2: Location**
- Address (autocomplete)
- City, state
- GPS pin on map (drag to adjust)

**Step 3: Details**
- Bedrooms, bathrooms
- Area (square meters)
- Furnished (yes/no)
- Amenities (multi-select)

**Step 4: Pricing**
- Price
- Currency
- Negotiable (checkbox)
- Deposit amount (for rentals)
- Rent period

**Step 5: Media**
- Image upload (drag & drop, max 15)
- Image reordering
- Video upload (optional)
- Virtual tour URL

**Step 6: Documents**
- Title deed upload
- Ownership proof
- Other documents

**Step 7: Review & Submit**
- Preview how listing will appear
- Fraud score estimation
- Submit for review

**Auto-save**: Save draft every 30 seconds

---

#### Favorites (`/dashboard/favorites`)
**Components**:
- Saved properties grid
- Organize into collections/folders
- Share collection link
- Remove from favorites
- Compare properties (checkbox select)

---

#### Messages (`/dashboard/messages`)
**Inbox Layout**:
- Conversation list (sidebar)
- Message thread (center)
- Property context card (right sidebar)

**Features**:
- Real-time messaging (WebSocket)
- Image sharing
- Schedule inspection button
- Report user button
- Archive conversation
- Mark as spam

---

#### Inspections (`/dashboard/inspections`)
**Calendar View**:
- Upcoming inspections
- Past inspections
- Schedule new inspection
- Add to Google Calendar
- Inspection checklist (PDF download)

**Table View**:
- Property, date, time, agent, status
- Reschedule, cancel options

---

#### Payments (`/dashboard/payments`)
**Sections**:

**Payment History** (Table):
- Date, property, amount, status, receipt
- Filter by status, date range

**Active Escrow** (Cards):
- Property details
- Amount locked
- Release conditions progress bar
- Time remaining until release
- Dispute button

**Saved Payment Methods**:
- Cards, bank accounts
- Add new method
- Set default

---

#### Profile Settings (`/dashboard/settings`)
**Tabs**:

**1. Personal Information**
- Name, email, phone
- Avatar upload
- Bio (for agents/landlords)
- Social media links

**2. Verification**
- ID upload (front, back)
- Verification status
- Business documents (for agents)
- Bank account details

**3. Security**
- Change password
- Two-factor authentication
- Login history
- Active sessions

**4. Preferences**
- Language
- Currency
- Email notifications (toggles)
- SMS notifications
- Push notifications

**5. Privacy**
- Profile visibility
- Contact preferences
- Data download (GDPR)
- Delete account

---

#### Notifications (`/dashboard/notifications`)
**Types**:
- New inquiry on your property
- Property verification complete
- Payment received
- Inspection scheduled
- Message from [user]
- Fraud alert
- System announcements

**Features**:
- Mark as read/unread
- Mark all as read
- Filter by type
- Clear all

---

#### Analytics (Agents/Landlords) (`/dashboard/analytics`)
**Metrics**:
- Total views (graph over time)
- Inquiries (conversion rate)
- Verification score distribution
- Top performing properties
- Traffic sources
- User demographics (city, age)
- Response time tracking

**Export**: PDF, CSV

---

## 3. Mobile Application Screens

> Built as native apps: Android (Kotlin + Jetpack Compose) and iOS (Swift + SwiftUI). Screen list unchanged.

### Onboarding Flow
1. **Splash Screen**: Logo + loading
2. **Welcome Slides** (3 screens):
   - "Find verified homes"
   - "Pay safely with escrow"
   - "Trust our fraud detection"
3. **Sign Up / Login**
4. **Permission Requests**:
   - Location (for nearby properties)
   - Notifications
   - Camera (for property photos)

---

### Main Navigation (Bottom Tab Bar)
1. **Home** (🏠)
2. **Search** (🔍)
3. **Favorites** (❤️)
4. **Messages** (💬)
5. **Profile** (👤)

---

### Home Tab
**Components**:
- Search bar (tap to open search screen)
- Location selector (current city)
- Quick filters (pills): Rent, Sale, <500k, 2BR
- Featured properties (horizontal scroll)
- Recently viewed
- Recommended for you
- Nearby properties (with map snippet)

**Actions**: Pull to refresh

---

### Search Screen
**Components**:
- Search bar (property name, location)
- Filter chips (price, type, bedrooms)
- Filter button (opens filter modal)
- Map/List toggle
- Sort dropdown
- Property cards (infinite scroll)

**Filter Modal** (Bottom sheet):
- All search filters
- Apply/Reset buttons

---

### Property Detail Screen
**Layout**:
- Image carousel (fullscreen swipe)
- Property title + verification badge
- Price (large, bold)
- Quick actions: Share, Save, Report
- Key stats (grid): Bedrooms, bathrooms, area
- Location (mini map, tap to expand)
- Amenities (icon grid)
- Description (expandable)
- Agent card (tap to view profile)
- Similar properties (horizontal scroll)

**Sticky Bottom Bar**:
- "Contact Agent" button
- "Schedule Inspection" button

---

### Agent Profile Screen
**Components**:
- Agent photo + name
- Verification badge
- Reputation score (5-star + number)
- Stats: Properties, transactions, response time
- About/Bio
- Active listings (grid)
- Reviews from clients
- "Contact" button

---

### Favorites Tab
**Views**:
- Grid of saved properties
- Empty state: "No favorites yet"
- Actions: Remove, Share

---

### Messages Tab
**Conversation List**:
- Agent/landlord avatar + name
- Last message preview
- Timestamp
- Unread badge
- Property thumbnail (right side)

**Conversation Screen**:
- Property header (tap to view property)
- Message bubbles
- Image sharing
- "Schedule Inspection" quick action
- Report/Block options (menu)

---

### Profile Tab
**Sections**:
- User avatar + name
- Verification status banner
- Menu items:
  - My Listings (landlords/agents)
  - Inspections
  - Payments & Escrow
  - Settings
  - Help Center
  - Logout

---

### Camera/Upload Screen
**For property listing**:
- Camera viewfinder
- Gallery import
- Image reordering (drag & drop)
- Add captions
- Delete images
- Continue button

---

### Map View
**Full-screen map**:
- Property pins (clustered)
- Property card sheet (bottom)
- Swipe through properties
- "List View" button

---

### Payment/Escrow Screen
**Escrow Details**:
- Property card
- Amount breakdown (visual):
  - Total amount
  - Platform fee
  - Agent commission
  - Seller amount
- Release conditions (checklist)
- Progress bar
- "Initiate Payment" button

**Payment Gateway** (WebView):
- Flutterwave/Paystack integration
- Card entry
- Mobile money options
- USSD code display

---

### Inspection Scheduler
**Calendar View**:
- Available dates/times
- Select time slot
- Add notes
- Confirm booking

---

### Notifications Screen
**List**:
- Notification cards (icon, text, time)
- Tap to navigate to relevant screen
- Clear button

---

## 4. Admin Dashboard

**URL**: `/admin` (Django Admin or custom)

### Dashboard Home (`/admin/dashboard`)
**Metrics Cards**:
- Total users (graph)
- Active properties
- Pending verifications
- Fraud reports (last 24h)
- Revenue (this month)
- System health

**Recent Activity**:
- New registrations
- Property submissions
- Fraud detections
- Payments

---

### User Management (`/admin/users`)
**Table Columns**:
- Name, email, role, country
- Verification status
- Reputation score
- Registration date
- Actions: View, Edit, Suspend, Delete

**Filters**: Role, verification status, country, date range

**User Detail Page**:
- Full profile
- Activity log
- Properties owned/managed
- Transactions
- Fraud reports (if any)
- Edit details
- Send notification
- Suspend/ban user

---

### Property Management (`/admin/properties`)
**Table**:
- Title, owner, status, verification score
- Created date, views
- Actions: Approve, Suspend, Delete

**Property Moderation Page**:
- Property details
- Verification score breakdown
- Fraud flags (if any)
- Duplicate detection results
- Approve/Reject buttons
- Add moderation notes

---

### Fraud Detection (`/admin/fraud`)
**Tabs**:

**1. Reports** (user-submitted):
- Reporter, reported property/user, category
- Status (pending, investigating, resolved)
- Assign to investigator
- View evidence

**2. Automated Detections**:
- Duplicate properties (similarity %)
- Anomaly detections (ML scores)
- Fraud rings (network visualization)
- Take action: Suspend, flag, ignore

**3. Fraud Network Graph**:
- Interactive graph visualization
- Nodes = users
- Edges = connections (shared IP, device, etc.)
- Cluster highlighting
- Export data

---

### Payments & Escrow (`/admin/payments`)
**Sections**:

**Active Escrow**:
- Property, buyer, seller, amount
- Lock status, release conditions
- Dispute flag
- Manual release override

**Transaction History**:
- Date, type, amount, status
- Payment provider
- Refund/dispute actions

**Revenue Analytics**:
- Platform fees collected
- By country, by month
- Commission tracking

---

### Verification Queue (`/admin/verifications`)
**Table**:
- User/property, type (ID, property docs)
- Submitted date, status
- Assign to reviewer

**Verification Detail**:
- Document viewer (PDF, images)
- Comparison tools (for ID verification)
- Approve/Reject
- Request more information

---

### Analytics & Reports (`/admin/analytics`)
**Dashboards**:
- User growth (graphs)
- Property listings (by type, location)
- Conversion funnel
- Fraud prevention impact
- Payment volume
- Geographic heatmap

**Export**: PDF, Excel, CSV

---

### Content Management (`/admin/content`)
- Edit homepage
- Manage blog posts
- FAQs
- Email templates
- Push notification templates

---

### System Settings (`/admin/settings`)
**Sections**:
- Platform configuration
- Feature flags (enable/disable features)
- Payment gateway settings
- Fraud detection thresholds
- Email/SMS providers
- API keys management

---

### Audit Logs (`/admin/audit`)
**Table**:
- User, action, entity, timestamp
- Old/new values (diff view)
- IP address
- Filter by user, action, date

---

## 5. API Documentation Portal

**URL**: `/docs` (Swagger UI auto-generated by FastAPI)

### Sections:
1. **Authentication**:
   - POST /api/auth/register
   - POST /api/auth/login
   - POST /api/auth/refresh

2. **Properties**:
   - GET /api/properties/search
   - GET /api/properties/:id
   - POST /api/properties
   - PUT /api/properties/:id
   - DELETE /api/properties/:id

3. **Users**:
   - GET /api/users/me
   - PUT /api/users/me
   - GET /api/users/:id (public profile)

4. **Payments**:
   - POST /api/escrow
   - GET /api/escrow/:id
   - POST /api/escrow/:id/release

5. **Fraud**:
   - POST /api/fraud/report
   - GET /api/fraud/score/:propertyId

**Features**:
- Try it out (live API calls)
- Code examples (cURL, Python, JavaScript)
- Authentication (API key input)
- Response schemas

---

## 6. Agent Portal (Premium)

**URL**: `/agents`

### Enhanced Dashboard (`/agents/dashboard`)
**Widgets**:
- Lead pipeline (kanban: New, Contacted, Viewing, Negotiating, Closed)
- Commission tracker (monthly, yearly)
- Performance metrics vs other agents
- Upcoming inspections (calendar)
- Client management

---

### CRM (`/agents/clients`)
**Table**:
- Client name, contact, properties interested in
- Stage (lead, prospect, client)
- Last contact date
- Notes
- Actions: Email, Call, Schedule follow-up

**Client Detail**:
- Contact information
- Conversation history
- Properties viewed
- Offers made
- Activity timeline
- Add notes

---

### Marketing Tools (`/agents/marketing`)
**Features**:
- Generate property flyers (PDF)
- Social media post templates
- WhatsApp broadcast lists
- Email campaigns
- QR code generator (for properties)

---

### Performance Analytics (`/agents/analytics`)
**Metrics**:
- Listing-to-close ratio
- Average days to close
- Commission earned
- Client acquisition cost
- Response time tracking
- Satisfaction ratings

---

## Navigation Hierarchy

```
Public Site
├── / (Homepage)
├── /search
│   └── /properties/:id
├── /about
├── /how-it-works
├── /safety
├── /pricing
├── /help
├── /blog
│   └── /blog/:category/:slug
├── /careers
└── Legal
    ├── /terms
    ├── /privacy
    └── /compliance

Web App (Authenticated)
├── /dashboard
├── /dashboard/properties
│   ├── /new
│   └── /:id/edit
├── /dashboard/favorites
├── /dashboard/messages
├── /dashboard/inspections
├── /dashboard/payments
├── /dashboard/settings
├── /dashboard/notifications
└── /dashboard/analytics

Mobile App (Tab Navigation)
├── Home
├── Search
│   ├── Map View
│   └── List View
├── Favorites
├── Messages
│   └── Conversation
└── Profile
    ├── My Listings
    ├── Inspections
    ├── Payments
    └── Settings

Admin Panel
├── /admin/dashboard
├── /admin/users
├── /admin/properties
├── /admin/fraud
├── /admin/payments
├── /admin/verifications
├── /admin/analytics
├── /admin/content
├── /admin/settings
└── /admin/audit

API Documentation
└── /docs (Swagger UI)

Agent Portal
├── /agents/dashboard
├── /agents/clients
├── /agents/marketing
└── /agents/analytics
```

---

## URL Patterns Summary

| Pattern | Example | Purpose |
|---------|---------|---------|
| `/` | `/` | Homepage |
| `/page` | `/about`, `/pricing` | Static pages |
| `/search?params` | `/search?city=Lagos` | Search with filters |
| `/properties/:id` | `/properties/uuid-123` | Property detail |
| `/blog/:category/:slug` | `/blog/tips/first-time-renter` | Blog post |
| `/dashboard/:section` | `/dashboard/messages` | User dashboard |
| `/dashboard/:section/:id` | `/dashboard/properties/uuid-456/edit` | Edit entity |
| `/admin/:section` | `/admin/users` | Admin panel |
| `/api/:version/:resource` | `/api/v1/properties` | API endpoints |

---

## Responsive Design Breakpoints

```css
/* Mobile: 0-767px */
@media (max-width: 767px) { }

/* Tablet: 768px-1023px */
@media (min-width: 768px) and (max-width: 1023px) { }

/* Desktop: 1024px+ */
@media (min-width: 1024px) { }

/* Large Desktop: 1440px+ */
@media (min-width: 1440px) { }
```

---

## Page Load Performance Targets

| Page Type | Target LCP | Target FID | Target CLS |
|-----------|-----------|------------|------------|
| Homepage | <2.5s | <100ms | <0.1 |
| Search | <2.5s | <100ms | <0.1 |
| Property Detail | <3.0s | <100ms | <0.1 |
| Dashboard | <2.0s | <100ms | <0.1 |

---

## Accessibility (WCAG 2.1 AA)

**Requirements**:
- ✅ Keyboard navigation (all interactive elements)
- ✅ Screen reader support (ARIA labels)
- ✅ Color contrast ratio ≥4.5:1
- ✅ Focus indicators
- ✅ Alt text for images
- ✅ Form labels and error messages
- ✅ Skip to main content link

---

## Offline-First (PWA)

**Cacheable Pages**:
- Homepage
- Search results (last query)
- Property details (last 10 viewed)
- User dashboard
- Favorites

**Service Worker Strategy**:
- Network-first for API calls
- Cache-first for static assets
- Background sync for form submissions

---

This comprehensive page structure provides a complete blueprint for building the House Agent platform across all interfaces.
