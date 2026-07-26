# Dairy Farm Tracker — Backend Implementation Plan

**Product:** Loonkoo Dairy Farm Tracker (DFT)  
**Stack:** Django 6 + Django REST Framework + JWT  
**Workspace:** [`dft_backend/`](.)  
**Dev database:** SQLite (current scaffold) — models structured for a later PostgreSQL swap  
**Companion plan:** [`../dft-frontend/IMPLEMENTATION_PLAN.md`](../dft-frontend/IMPLEMENTATION_PLAN.md)

This document is the actionable backend blueprint derived from the project proposal. Implement in the phases below; keep each Django app independently testable.

**Deployment model:** One installation serves **one dairy farm**. There is no multi-tenant / multi-farm tenancy. A single `Farm` profile holds farm settings; operational data (cattle, milk, health, etc.) belongs to that farm implicitly and does **not** carry a `farm_id`.

---

## 1. Goals and scope

### In scope

- Single-farm management system (one Farm profile per deployment)
- Application roles: **Farm Owner**, **Worker**, **Veterinarian**
- Platform superuser: Django’s built-in `is_superuser` via `createsuperuser` / Django admin only — **not** an app role enum
- Core modules: farm profile, cattle, milk, health, breeding, finance, alerts
- REST JSON APIs consumed by the Next.js frontend
- Automated alerts for low milk yield (rule/threshold-based), vaccinations due, breeding milestones

### Out of scope (v1)

- Machine learning (milk yield prediction, disease prediction, image CNN) — deferred to a later release
- Multi-tenant / multi-farm SaaS (no `farm_id` isolation, no farm switcher)
- Government Official role or government dashboard APIs
- Custom `ADMIN` / super-admin app role (use Django superuser + `/admin/`)
- Native mobile apps
- Live payment gateway
- Live external government APIs
- Full Amharic / Afaan Oromo API localization (frontend-led later)

---

## 2. Roles and module access

### 2.1 Roles

| Role | Enum value | How created | Purpose |
|------|------------|-------------|---------|
| Farm Owner | `OWNER` | First registration / bootstrap | Full farm management |
| Worker | `WORKER` | Invited by Owner | Daily operational data entry |
| Veterinarian | `VETERINARIAN` | Invited by Owner | Animal health, vaccinations, treatments |
| Django superuser | *(not an app role)* | `python manage.py createsuperuser` | Django Admin, DB ops, break-glass |

`User.role` choices: `OWNER | WORKER | VETERINARIAN` only.  
Do not put `ADMIN` or `GOVERNMENT` in the role field. Superusers may also have an app role if they log into the API UI, but admin power comes from `is_superuser`, not from `role`.

### 2.2 Module access matrix

Legend: **F** = full CRUD · **R** = read · **W** = create/update (limited) · **—** = no access

| Module | Owner | Worker | Veterinarian |
|--------|:-----:|:------:|:------------:|
| **Dashboard / KPIs** | F (all KPIs) | R (ops KPIs: milk today, alerts, herd) | R (health KPIs: due vaccines, open treatments) |
| **Farm profile** (`/api/farm/`) | F | R | R |
| **User management** (invite workers & vets) | F | — | — |
| **Cattle** | F | R + limited W (status notes optional) | R |
| **Milk production** | F | F (log & edit own/day records) | R |
| **Health** (records, vaccinations, treatments) | F | W (log symptoms / basic records) + R | F |
| **Breeding & reproduction** | F | W (log mating) + R | R + W (pregnancy health notes / status) |
| **Finance** | F | — | — |
| **Alerts** | F (all farm alerts) | R/W own inbox (ops alerts) | R/W health & breeding alerts |
| **Django Admin** (`/admin/`) | — | — | — |

Django superuser accesses **Django Admin** and can bypass API permissions when needed for support; they are not listed as an application role above.

### 2.3 Role summaries

**Owner** — Settings, staff invites (workers + veterinarians), cattle, milk, health, breeding, finance, all alerts, full dashboard.

**Worker** — Day-to-day: milk logs, basic health logging, breeding event entry, cattle view, ops alerts. No finance, no staff management, no farm profile edits.

**Veterinarian** — Clinical focus: full health module, cattle read, milk read (context), breeding pregnancy health updates, health/breeding alerts. No finance, no staff management, no farm profile edits.

---

## 3. Architecture overview

```
Presentation (Next.js)
        │  JWT Bearer / refresh
        ▼
┌──────────────────────────────────────────┐
│  Django + DRF  (/api/...)                │
│  accounts · farm · cattle · milk         │
│  health · breeding · finance · alerts    │
└──────────────────────────────────────────┘
        │
        ▼
   SQLite (dev) / PostgreSQL (prod-ready)
```

**Communication:** RESTful JSON over HTTPS (HTTP in local dev).  
**Farm model:** Single farm per deployment. Users access data based on **role**.  
**Auth:** `djangorestframework-simplejwt`; passwords hashed by Django.

---

## 4. Project setup

### 4.1 Dependencies to add

| Package | Purpose |
|---------|---------|
| `djangorestframework` | REST APIs |
| `djangorestframework-simplejwt` | JWT auth |
| `django-cors-headers` | Frontend CORS |
| `django-filter` | Query filtering |
| `python-dotenv` / `django-environ` | Env-based settings |
| `Pillow` | Optional cattle/profile images |
| `pytest`, `pytest-django` | Preferred test runner (optional; unittest also fine) |

Pin versions in `requirements.txt` at the `dft_backend/` root.

### 4.2 Settings changes ([`dft_backend/settings.py`](dft_backend/settings.py))

- Split config via env: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`
- `INSTALLED_APPS`: DRF, simplejwt blacklist (optional), corsheaders, filter, all domain apps
- `AUTH_USER_MODEL = 'accounts.User'`
- `REST_FRAMEWORK` defaults: JWT auth, page size 20, filter backends, exception handler
- `SIMPLE_JWT`: access ~60m, refresh ~7d
- `CORS_ALLOWED_ORIGINS`: `http://localhost:3000` in dev
- `TIME_ZONE = 'Africa/Addis_Ababa'`
- Keep SQLite for local; document PostgreSQL `DATABASES` block for production

### 4.3 URL root ([`dft_backend/urls.py`](dft_backend/urls.py))

```
/api/auth/
/api/farm/
/api/cattle/
/api/milk/
/api/health/
/api/breeding/
/api/finance/
/api/alerts/
/admin/          # Django superuser only
```

---

## 5. Django apps

| App | Responsibility |
|-----|----------------|
| `accounts` | Custom User, registration, login, JWT, profile, invite workers & veterinarians |
| `farm` | Single Farm profile (settings singleton) |
| `cattle` | Herd registry |
| `milk` | Daily milk logs, feed linkage, production aggregates |
| `health` | Health logs, vaccinations, treatments |
| `breeding` | Mating, pregnancy, births |
| `finance` | Income/expense, profitability (Owner only) |
| `alerts` | Alert generation, inbox, acknowledge |

Shared helpers (`core/`):

- Permission classes: `IsOwner`, `IsWorker`, `IsVeterinarian`, `IsOwnerOrWorker`, `IsClinicalStaff` (Owner | Vet), etc.
- Pagination, exception formatting
- `get_farm()` singleton helper

---

## 6. Data model

### 6.1 Entity relationship (logical)

```
User (role: OWNER | WORKER | VETERINARIAN)
Farm  (singleton settings — 1 row)
Cattle ──< MilkRecord
Cattle ──< HealthRecord / Vaccination / Treatment
Cattle ──< BreedingEvent / Pregnancy / BirthRecord
FeedSchedule (optional)
Transaction (finance)
Alert ──> User, Cattle (optional)
```

### 6.2 Models by app

#### `accounts.User`

- Extends `AbstractUser`
- Fields: `email` (unique), `phone` (optional unique), `role`: `OWNER | WORKER | VETERINARIAN`
- Notes:
  - First Owner registration may bootstrap Farm profile
  - Owner invites staff via `/api/auth/staff/` (or separate `/workers/` and `/veterinarians/`)
  - Django superuser: `is_superuser=True` — independent of `role`

#### `farm.Farm`

- Singleton (at most one row)
- Fields: `name`, `location` / `region`, `woreda` (optional), `phone`, `notes`, timestamps

#### `cattle.Cattle`

- `tag_id` (unique), `name`, `breed`, `sex`, `date_of_birth`, `status` (`ACTIVE | SOLD | DEAD | CULLED`), optional parent FKs, `notes`

#### `milk.MilkRecord`

- `cattle`, `date`, morning/evening or session liters, `recorded_by`, `notes`
- Unique: one record per cattle per date (and session if split)

#### `milk.FeedSchedule` (optional)

- `cattle` nullable, `feed_type`, `quantity`, `date`, `quality_score`

#### `health.HealthRecord` / `Vaccination` / `Treatment`

- Standard clinical fields; `veterinarian_name` optional string; `recorded_by` → User

#### `breeding.BreedingEvent` / `Pregnancy` / `BirthRecord`

- Mating, pregnancy status, calving; birth may auto-create calf `Cattle`

#### `finance.Transaction`

- `INCOME | EXPENSE`, category, amount (`ETB`), date, optional milk link, `recorded_by`

#### `alerts.Alert`

- `user`, optional `cattle`, `category` (`MILK | HEALTH | BREEDING | FINANCE | SYSTEM`), `severity`, title/message, read/ack flags

### 6.3 Single-farm rules

1. No `farm` FKs on operational tables  
2. Authorization by `user.role` (+ `is_superuser` only for Django admin / emergency)  
3. Farm profile: GET for all authenticated app roles; PATCH Owner only; POST if none exists (Owner bootstrap)

---

## 7. API surface

### 7.1 Auth — `/api/auth/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| POST | `/register/` | Bootstrap Owner (+ optional farm name) | Public (first setup) |
| POST | `/login/` | JWT access + refresh | Public |
| POST | `/token/refresh/` | Refresh | Authenticated |
| POST | `/logout/` | Blacklist refresh | Authenticated |
| GET/PATCH | `/me/` | Profile | Authenticated |
| GET | `/staff/` | List workers & veterinarians | Owner |
| POST | `/staff/` | Invite user with `role=WORKER` or `VETERINARIAN` | Owner |
| PATCH/DELETE | `/staff/{id}/` | Update/deactivate staff | Owner |

### 7.2 Farm — `/api/farm/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | `/` | Farm profile | Owner, Worker, Veterinarian |
| POST | `/` | Create if missing | Owner |
| PATCH | `/` | Update profile | Owner |

### 7.3 Cattle — `/api/cattle/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | `/`, `/{id}/` | List / detail | Owner, Worker, Veterinarian |
| POST | `/` | Create | Owner (Worker optional limited) |
| PATCH/DELETE | `/{id}/` | Update / retire | Owner; Worker limited PATCH |

### 7.4 Milk — `/api/milk/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | `/records/`, `/summary/`, `/trends/` | Read | Owner, Worker, Veterinarian |
| POST/PATCH/DELETE | `/records/...` | Write | Owner, Worker |

### 7.5 Health — `/api/health/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | records, vaccinations, treatments, upcoming | Read | Owner, Worker, Veterinarian |
| POST/PATCH | records, vaccinations, treatments | Write | Owner, Veterinarian; Worker may POST basic health records only |

### 7.6 Breeding — `/api/breeding/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | events, pregnancies, births | Read | Owner, Worker, Veterinarian |
| POST | events | Log mating | Owner, Worker |
| PATCH | pregnancies | Status / clinical notes | Owner, Veterinarian |
| POST | births | Record birth + calf | Owner |

### 7.7 Finance — `/api/finance/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| * | `/transactions/`, `/summary/`, `/by-category/` | All | **Owner only** |

### 7.8 Alerts — `/api/alerts/`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| GET | `/`, `/unread-count/` | Inbox (filtered by role relevance) | Owner, Worker, Veterinarian |
| PATCH/POST | read / acknowledge | Mark handled | Same |

Filter defaults: Workers see `MILK`, `SYSTEM`, general ops; Veterinarians see `HEALTH`, `BREEDING`; Owners see all.

---

## 8. Alerts engine

1. **Signals:** MilkRecord below herd/cow average or configured threshold → `MILK`  
2. **Command `generate_alerts`:** vaccination due, calving due → `HEALTH` / `BREEDING`  

Delivery: persist rows; frontend polls. Dedup on `(category, cattle_id, date, title)`.

---

## 9. Serializers and business rules

- Milk liters ≥ 0; cattle `tag_id` unique  
- Workers/Vets cannot PATCH farm or manage staff  
- Workers/Vets cannot access finance  
- Birth creates calf with mother link  
- Enforce module matrix in permission classes (section 2.2)

---

## 10. Implementation phases

### Phase 0 — Foundation

- [ ] Deps, settings, CORS, DRF, JWT  
- [ ] Apps scaffolded  
- [ ] User (`OWNER|WORKER|VETERINARIAN`) + Farm singleton  
- [ ] Auth + staff invite endpoints  
- [ ] Role permission classes matching module matrix  
- [ ] Smoke: JWT + `/api/auth/me/` + `/api/farm/`

### Phase 1 — Core operations

- [ ] Cattle, milk, health, breeding, finance, alerts  
- [ ] Permission tests per role × module  
- [ ] Exit: Owner / Worker / Vet happy paths via API  

### Phase 2 — Analytics and alerts

- [ ] Milk summary/trends endpoints for charts  
- [ ] Threshold-based low-milk alerts + vaccination/breeding due alerts  

### Phase 3 — Polish

- [ ] Seed demo users (1 owner, 2 workers, 1 vet)  
- [ ] Indexes, OpenAPI optional  
- [ ] Document `createsuperuser` for Django Admin only  

### Phase 4 — Hardening

- [ ] Full matrix tests, rate limits, backups  

---

## 11. Directory layout

```
dft_backend/
  manage.py
  requirements.txt
  IMPLEMENTATION_PLAN.md
  dft_backend/
  accounts/
  farm/
  cattle/
  milk/
  health/
  breeding/
  finance/
  alerts/
  core/
  media/
```

No `government/` or `ml_services/` apps in v1.

---

## 12. Testing strategy

**Critical cases**

1. Worker → `403` on finance and staff invite  
2. Veterinarian → `403` on finance and milk write; `200` on health write  
3. Owner → full access  
4. Second Farm create rejected  
5. App role `ADMIN` / `GOVERNMENT` must not exist in choices  
6. JWT expired → 401  

---

## 13. Seed demo data

`seed_demo`:

- 1 Farm profile  
- 1 Owner, 2 Workers, 1 Veterinarian  
- Create Django superuser separately via `createsuperuser` (documented, not an app role)  
- Sample cattle, milk, health, breeding, finance  

---

## 14. Security checklist

- [ ] `DEBUG=False` in production  
- [ ] Env secrets; CORS allowlist; HTTPS  
- [ ] Role checks on every ViewSet per matrix  
- [ ] Django Admin restricted to superusers  
- [ ] No custom super-admin role in JWT payloads  

---

## 15. Alignment with frontend

- Role enums: `OWNER`, `WORKER`, `VETERINARIAN` only  
- Pagination + DRF error shapes as usual  
- No farm query/header; no government or ML routes  
- Nav and route guards must match section 2.2 module matrix  

---

## 16. Definition of done (backend v1)

1. Phase 0–2 APIs live with role matrix enforced  
2. Seed works (Owner, Worker, Vet)  
3. Alerts for vaccinations and low milk (rule-based)  
4. Frontend can complete all three role happy paths  
5. Django superuser used only for `/admin/`  
6. No ML endpoints or model artifacts shipped  
