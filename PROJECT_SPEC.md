# VaultX: Distributed Financial Transaction & Ledger Engine
**Target System:** High-concurrency, immutable double-entry ledger backend (TigerBeetle / Stripe core model).

---

## 1. Domain & Scope (What We Are Building)
VaultX is a high-throughput financial transaction engine designed to transfer balances between accounts with absolute data integrity and zero double-spending under concurrent bursts.

- **Primary Goal:** Sub-10ms p99 write latency, strict ACID consistency, guaranteed idempotency, and automated recovery from network timeouts.
- **Explicit Non-Goals (DO NOT IMPLEMENT):**
  - NO Secret/Key Management (No KMS, HashiCorp Vault, or Shamir's Secret Sharing).
  - NO custom crypto engines (Use standard tokens/JWTs for auth).
  - NO Raft/etcd distributed consensus clusters.
  - NO secondary analytical DBs (No ClickHouse or TimescaleDB).
  - NO React/Vue frontend (The primary interface is OpenAPI/Swagger + k6 benchmarks).

---

## 2. Core Architecture & Tech Stack
- **API Runtime:** Python 3.12+ with FastAPI (AsyncIO, ASGI).
- **Type Validation:** Pydantic v2 (Strict decimal precision for financial units; no floating-point arithmetic).
- **Primary Database:** PostgreSQL 16+ via SQLAlchemy 2.0 (asyncpg driver).
- **Caching & Distributed Locks:** Redis 7+ (redis-py async).
- **Asynchronous Task Queue:** Celery (or ARQ) with Redis broker for side effects (notifications, statement generation).
- **Observability:** Prometheus client metrics (`prometheus-fastapi-instrumentator`) + Grafana dashboard config.
- **Containerization:** Docker & Docker Compose (API replicas, Nginx gateway, Postgres, Redis, Celery worker).

---

## 3. Data Model & Concurrency Invariants

### Database Schema (PostgreSQL)
1. **`accounts` Table:**
   - `id`: UUID (Primary Key)
   - `user_id`: UUID (Indexed)
   - `balance`: NUMERIC(15, 2) NOT NULL (Check constraint: `balance >= 0.00`)
   - `currency`: VARCHAR(3) (Default 'INR')
   - `version`: INT (Optimistic lock fallback)
   - `created_at`, `updated_at`: TIMESTAMPTZ

2. **`transactions` Table (Double-Entry Ledger):**
   - `id`: UUID (Primary Key)
   - `idempotency_key`: VARCHAR(64) UNIQUE NOT NULL (Indexed)
   - `source_account_id`: UUID (Foreign Key -> accounts.id)
   - `destination_account_id`: UUID (Foreign Key -> accounts.id)
   - `amount`: NUMERIC(15, 2) NOT NULL (Check constraint: `amount > 0.00`)
   - `status`: ENUM ('PENDING', 'COMMITTED', 'REVERSED', 'FAILED')
   - `created_at`: TIMESTAMPTZ NOT NULL

### Concurrency Rules
- **Deadlock Prevention:** When locking multiple accounts in a single transfer transaction, always sort account IDs lexicographically:
  ```python
  first_id, second_id = sorted([src_id, dest_id])