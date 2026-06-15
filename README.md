# 🍛 THOOKU MADURAI

**Madurai's Hyperlocal Food Delivery Platform**  
*Real Prices. Real Restaurants. Delivered to Your Door.*

[![Domain](https://img.shields.io/badge/domain-thookumadurai.in-green)](https://thookumadurai.in)
[![Stack](https://img.shields.io/badge/stack-Flask%20%7C%20MongoDB%20%7C%20Bootstrap-blue)]()
[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()

---

## 🌟 What Makes Us Different

Unlike Swiggy & Zomato:
- **Zero menu markup** — customers pay exact restaurant prices
- **Transparent fees** — Food Amount + Distance Delivery Fee + Fixed ₹20 Platform Fee
- **Local first** — Built for Madurai, by Madurai

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3, Vanilla JS, Bootstrap 5 |
| Backend | Python 3.12, Flask |
| Server | Gunicorn + Gevent |
| Database | MongoDB Atlas |
| Cache | Redis |
| Storage | Cloudinary |
| Auth | JWT + OTP |
| Payments | Razorpay UPI |
| Calls | Exotel (IVR, Masked Calls) |
| Maps | Google Maps API |
| Notifications | WhatsApp Cloud API + SMTP |
| Monitoring | Sentry |
| Analytics | Google Analytics 4 |
| Hosting FE | Netlify |
| Hosting BE | Render |
| DNS | Cloudflare |

---

## 📁 Project Structure

```
thooku-madurai/
├── frontend/
│   ├── index.html              # Customer app
│   ├── restaurant-dashboard.html
│   ├── rider-dashboard.html
│   ├── admin-panel.html
│   ├── super-admin.html
│   ├── css/main.css
│   ├── robots.txt
│   └── sitemap.xml
├── backend/
│   ├── app.py                  # Flask app
│   ├── requirements.txt
│   ├── gunicorn.conf.py
│   └── api/v1/
│       ├── auth.py             # OTP auth, JWT
│       ├── customers.py
│       ├── restaurants.py
│       ├── riders.py
│       ├── orders.py           # Order flow, rider assignment
│       ├── payments.py         # Razorpay UPI
│       ├── admin.py
│       ├── tracking.py
│       └── analytics.py
├── database/schemas/
│   └── mongodb_schema.js       # All collections & indexes
├── deployment/
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── netlify.toml
├── .github/workflows/
│   ├── deploy-frontend.yml
│   └── deploy-backend.yml
├── .env.example
└── README.md
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- Node.js (optional, for live-server)
- MongoDB Atlas account
- Redis (local or cloud)

### 1. Clone & Setup Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit .env with your credentials
python app.py                  # Dev server on :5000
```

### 2. Run Frontend (Local)
```bash
# Option 1: Python simple server
cd frontend
python -m http.server 5500

# Option 2: VSCode Live Server
# Install "Live Server" extension and click "Go Live"
```

### 3. Run with Docker (Full Stack)
```bash
cp .env.example .env
docker-compose -f deployment/docker-compose.yml up -d
```

---

## 🌐 Deployment

### Frontend → Netlify
1. Push code to GitHub
2. Connect repo to Netlify
3. Set build directory: `frontend`
4. GitHub Actions auto-deploys on push

### Backend → Render
1. Create new Web Service on Render
2. Connect GitHub repo
3. Set root directory: `backend`
4. Set start command: `gunicorn -c gunicorn.conf.py app:app`
5. Add all environment variables from `.env.example`

### Database → MongoDB Atlas
1. Create Atlas cluster (M0 free or M10 paid)
2. Run `database/schemas/mongodb_schema.js` in Atlas shell
3. Copy connection string to `MONGO_URI` env var
4. Whitelist Render IP addresses

### Domain → Cloudflare
1. Add `thookumadurai.in` to Cloudflare
2. Set DNS A record → Netlify IP for frontend
3. Set DNS CNAME `api` → Render URL for backend
4. Enable SSL/TLS (Full Strict mode)
5. Enable "Always HTTPS" redirect

---

## 🔑 Environment Variables

See [.env.example](.env.example) for all required variables.

Critical variables:
- `MONGO_URI` — MongoDB Atlas connection string
- `JWT_SECRET` — Must be 32+ random chars
- `RAZORPAY_KEY_ID/SECRET` — For UPI payments
- `EXOTEL_*` — For phone ordering & IVR
- `GOOGLE_MAPS_API_KEY` — For maps & routing

---

## 📱 User Roles & Access

| Role | Access |
|------|--------|
| Customer | `/` — Order food, track delivery |
| Restaurant | `/restaurant-dashboard.html` — Manage orders & menu |
| Rider | `/rider-dashboard.html` — Accept deliveries, track earnings |
| Admin | `/admin-panel.html` — Full platform control |
| Super Admin | `/super-admin.html` — Manage admins, platform config |

---

## 💰 Revenue Model

```
Customer pays:
  Food Amount     →  Restaurant
  Delivery Fee    →  Rider
  ₹20 Platform Fee →  Thooku Madurai
```

---

## 🔒 Security Features

- JWT authentication with refresh tokens
- OTP-based login (no passwords for customers)
- Rate limiting (200 req/min per IP)
- Razorpay webhook signature verification
- Phone number masking (customers & riders never see each other's numbers)
- Input validation on all endpoints
- CORS restricted to production domains
- Security headers on all responses
- MongoDB injection prevention (pymongo sanitization)
- Idempotency keys to prevent duplicate payments/orders

---

## 📞 Phone Ordering (Exotel)

- Virtual number: `044-XXXXXXX`
- IVR: Press 1 (New Order), 2 (Status), 3 (Support)
- 4 concurrent agents
- 20 simultaneous call capacity
- Masked calling between customer ↔ rider
- Call recording stored in Exotel

---

## 📊 Scale Targets

| Metric | Target |
|--------|--------|
| Customers | 10,000+ |
| Restaurants | 100+ |
| Riders | 500+ |
| Daily orders | 1,000 |
| Concurrent users | 500 |

---

## 📄 API Documentation

Base URL: `https://api.thookumadurai.in/api/v1`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/send-otp` | POST | Send OTP |
| `/auth/verify-otp` | POST | Verify OTP & login |
| `/restaurants/` | GET | List restaurants |
| `/restaurants/:id/menu` | GET | Get menu |
| `/orders/create` | POST | Create order |
| `/orders/:id/status` | PATCH | Update status |
| `/payments/create-order` | POST | Create Razorpay order |
| `/payments/verify` | POST | Verify payment |
| `/payments/webhook` | POST | Razorpay webhook |
| `/tracking/order/:id` | GET | Live tracking |
| `/riders/status` | PATCH | Toggle online/offline |
| `/admin/dashboard` | GET | Admin stats |

---

## 📃 Legal

- **FSSAI License**: Required for all restaurants  
- **GST Registration**: Collected from restaurants  
- **Privacy Policy**: `/privacy-policy`  
- **Terms & Conditions**: `/terms`  
- **Refund Policy**: Refunds processed within 5-7 business days  

---

## 🤝 Contact

**Thooku Madurai Private Limited**  
Madurai, Tamil Nadu, India  
📧 support@thookumadurai.in  
📞 044-XXXXXXXX  
🌐 https://thookumadurai.in

---

*Built with ❤️ for Madurai*
