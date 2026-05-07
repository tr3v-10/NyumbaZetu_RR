# 🏠 NyumbaManager — Kenya House Management System

A comprehensive, production-ready property management platform built for the Kenyan ecosystem. M-Pesa native, bank-integrated, Data Protection Act 2019 compliant.

---

## Architecture

- **Backend:** Flask + Flask-SQLAlchemy + PostgreSQL
- **Auth:** Flask-Login + bcrypt + CSRF protection
- **Cache:** Flask-Caching (Redis)
- **Rate Limiting:** Flask-Limiter (Redis)
- **Real-time:** Flask-SocketIO (eventlet)
- **Payments:** Safaricom Daraja API (M-Pesa STK Push), Equity/KCB/Co-op Bank APIs
- **SMS:** Africa's Talking API
- **Forensics:** GeoIP2, user-agents, browser fingerprinting

---

## Quick Start

```bash
# 1. Clone and setup
git clone <repo>
cd house_management
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Database setup (PostgreSQL must be running)
createdb house_management_db
flask create-db

# 4. Create super admin
flask create-superadmin

# 5. (Optional) Seed demo data
flask seed-demo

# 6. Run development server
python run.py
```

Open [http://localhost:5000](http://localhost:5000)

---

## User Roles

| Role | Access |
|------|--------|
| **Super Admin** | Full system access, visitor forensics, audit logs, all users |
| **Landlord** | Portfolio dashboard, financial reports, lease/invoice management |
| **Tenant** | Pay rent (M-Pesa/Bank), submit maintenance, view documents |
| **Caretaker** | Work orders, inspections, purchase requests, receipts |
| **Agent** | Listings, leases, commission tracking, applicants |

---

## Theme System

- **Night Mode:** Black (#080d08) + Forest Green (#28a028)
- **Day Mode:** White/Cream (#f8f6ef) + Gold (#b8820a)
- Toggle: Top-right `☀️ Day` / `🌙 Night` buttons
- Preference saved in `localStorage`

---

## Payment Flow (No Wallet)

```
Tenant → M-Pesa PIN → Safaricom Daraja STK Push → Landlord Paybill/Till
                                          ↓
                              Callback URL → App records payment → Receipt SMS
```

```
Tenant → Bank Transfer (Ref: NYM0001A1) → Landlord Bank Account
                                            ↓
                             Bank API/SMS Capture → Auto-reconciliation
```

---

## Key Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis for caching/rate limiting |
| `MPESA_CONSUMER_KEY` | Safaricom Daraja consumer key |
| `MPESA_SHORTCODE` | M-Pesa Paybill/Till number |
| `MPESA_CALLBACK_URL` | Public HTTPS URL for M-Pesa callbacks |
| `AT_API_KEY` | Africa's Talking API key |
| `GEOIP_DATABASE_PATH` | Path to GeoLite2-City.mmdb |

---

## API Endpoints Summary

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/auth/login` | Login |
| POST | `/auth/register` | Register |
| POST | `/api/mpesa/callback` | Safaricom STK Push callback |
| GET | `/api/mpesa/stk-query/:id` | Query payment status |
| POST | `/api/bank/webhook/:bank` | Bank transaction webhook |
| GET | `/api/notifications` | Unread notifications |
| POST | `/api/fingerprint` | Browser fingerprint collection |
| GET | `/api/stats/landlord` | Landlord stats JSON |
| GET | `/api/stats/super-admin` | System stats JSON |
| GET | `/api/health` | Health check |

---

## Security Features

- CSRF protection on all POST endpoints
- bcrypt password hashing (rounds: 13 prod, 4 dev)
- Account lockout after 5 failed attempts (30 min)
- HTTP security headers (HSTS, CSP, X-Frame-Options, etc.)
- Rate limiting (200/hour global, 10/min for payments)
- Role-based access control (RBAC)
- Full audit logging
- Forensic visitor logging (IP, MAC, fingerprint, geolocation)
- HTTPS-only session cookies in production
- Kenya Data Protection Act 2019 compliant

---

## Forensic Data Collected (Super Admin Only)

- IPv4/IPv6 addresses (all proxy headers)
- MAC address (via custom `X-Device-Mac` header from native apps)
- Browser fingerprint (canvas + audio + WebGL hash)
- User-agent (browser, OS, device type, brand, model)
- GeoIP (country, city, latitude, longitude, ISP)
- Screen dimensions, color depth, pixel ratio
- Timezone, language, platform
- All HTTP request headers
- Session ID, referrer, response times

---

## Policy Pages

- `/policies/privacy` — Privacy Policy (DPA 2019)
- `/policies/terms` — Terms of Service
- `/policies/usage` — Software Usage Policy
- `/policies/data-protection` — Data Protection Policy
- `/policies/cookie-policy` — Cookie Policy
- `/policies/acceptable-use` — Acceptable Use Policy
- `/policies/refund-policy` — Refund Policy
- `/policies/sla` — Service Level Agreement

---

## Postman Collection

Import `NyumbaManager_API.postman_collection.json` into Postman.
Set collection variable `base_url` to your server URL.

---

## Production Deployment

```bash
# Using gunicorn + eventlet
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 run:app

# With nginx reverse proxy, enable:
# - SSL/TLS (Let's Encrypt)
# - HSTS headers
# - Rate limiting at nginx level too
```

---

## License

Proprietary — NyumbaManager Ltd, Nairobi, Kenya. All Rights Reserved.
