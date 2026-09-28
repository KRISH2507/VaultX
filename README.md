# VaultX: Distributed Financial Transaction & Ledger Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)

**VaultX** is a high-throughput, distributed **Double-Entry Financial & Digital Asset Ledger Engine** engineered for sub-10ms p99 write latency, strict ACID consistency, guaranteed distributed idempotency, and deadlock-free high concurrency (mirroring TigerBeetle and Stripe Ledger core principles).

---

## Core Invariants

1. **Double-Entry Balance Invariance**:
   $$\sum \text{Debits} \equiv \sum \text{Credits}$$
   Money cannot be created or destroyed within a transaction.
2. **Immutable Append-Only Ledger**:
   Postings are append-only. No updates or deletions; corrections require compensating reversal transactions.
3. **Strict Non-Negative Balances**:
   Enforced via database `CHECK (balance >= 0.00)` constraints and application-level checks.
4. **Deadlock-Free Concurrency**:
   Deterministic lexicographical sorting of account IDs prior to acquiring PostgreSQL row locks eliminates circular wait deadlocks.
5. **Distributed Idempotency**:
   Two-tier deduplication via Redis atomic locks (`SETNX`) and PostgreSQL unique constraints on SHA-256 request payload hashes.

---

## Architecture Overview

```
                                    +-----------------------+
                                    |      Client Apps      |
                                    +-----------+-----------+
                                                | POST /transactions
                                                v
+------------------------+          +-----------+-----------+
|  Redis 7               |<-------->|  FastAPI (AsyncIO)    |
|  - Idempotency Locks   |          |  - Pydantic v2        |
|  - Rate Limiter        |          |  - Ledger Validator   |
+------------------------+          +-----------+-----------+
                                                | ACID Commit
                                                v
                                    +-----------+-----------+
                                    |  PostgreSQL 16 (async)|
                                    |  - accounts           |
                                    |  - transactions       |
                                    |  - postings           |
                                    |  - outbox_events      |
                                    +-----------+-----------+
                                                |
                                                v
                                    +-----------+-----------+
                                    |  Celery Outbox Worker |
                                    |  (Async Webhooks/Logs)|
                                    +-----------------------+
```

---

## Database Schema (PostgreSQL)

- **`accounts`**: UUID PK, `user_id`, `balance` (Numeric 15,2 with non-negative check), `currency` (default 'INR'), `version` for optimistic locking, timestamps.
- **`transactions`**: UUID PK, `idempotency_key` (unique), `source_account_id`, `destination_account_id`, `amount`, `status` (PENDING, COMMITTED, REVERSED, FAILED), timestamps.
- **`postings`**: UUID PK, `transaction_id`, `account_id`, `direction` (DEBIT, CREDIT), `amount`, `balance_after`, `sequence_num`, timestamps.
- **`idempotency_keys`**: `key` PK, `request_hash`, `response_code`, `response_body`, `status`, `locked_until`, timestamps.
- **`outbox_events`**: UUID PK, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `status`, `retry_count`, timestamps.

---

## API Endpoints

| Method | Endpoint | Description | Headers |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Liveness health check | - |
| `GET` | `/metrics` | Prometheus metrics scrape target | - |
| `POST` | `/api/v1/accounts` | Create financial account | - |
| `GET` | `/api/v1/accounts/{id}` | Retrieve account details | - |
| `GET` | `/api/v1/accounts/{id}/balance` | Real-time balance and version | - |
| `POST` | `/api/v1/accounts/{id}/deposit` | Deposit funds | `Idempotency-Key` (optional) |
| `POST` | `/api/v1/transfers` | Execute atomic double-entry transfer | `Idempotency-Key` (required) |
| `GET` | `/api/v1/transfers/{id}` | Get transaction details with postings | - |

---

## Getting Started

### 1. Setup Virtual Environment
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Start Infrastructure (Docker)
```bash
docker compose up -d postgres redis
```

### 3. Run Migrations
```bash
alembic upgrade head
```

### 4. Run Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive Swagger UI will be available at: `http://localhost:8000/api/v1/docs`

### 5. Run Celery Workers & Periodic Beat Scheduler
```bash
# Terminal 1: Run Celery Worker
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# Terminal 2: Run Celery Beat Scheduler (polls pending Outbox events)
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

### 6. Run Complete Stack via Docker Compose
Includes API, PostgreSQL, Redis, Celery Worker, Celery Beat, Prometheus, and Grafana:
```bash
docker compose up -d --build
```
- **FastAPI Documentation:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **Prometheus Metrics Target:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Grafana Live Dashboard:** [http://localhost:3000](http://localhost:3000) (User: `admin`, Password: `admin`)

### 7. Run Test Suite
```bash
pytest
```

---

## High-Concurrency Benchmark Suite (k6)

VaultX includes a comprehensive k6 load testing suite designed to stress-test ACID properties, row lock contention, and idempotency mechanisms under extreme traffic:

### 1. Benchmark 1: High-Throughput Transfers (10,000+ RPS)
Simulates sustained concurrent balance transfers across accounts, validating sub-10ms p99 settlement latency:
```bash
k6 run benchmarks/01_high_throughput_transfers.js
```

### 2. Benchmark 2: "Hot Account" Contention (500 Concurrent Threads)
Simulates a high-traffic merchant receiving transfers from 500 concurrent workers simultaneously, proving mathematically and experimentally that our lexicographical row-locking (`sort_account_ids_for_locking`) results in **zero PostgreSQL deadlocks**:
```bash
k6 run benchmarks/02_hot_account_contention.js
```

### 3. Benchmark 3: Idempotency Retry Storm (1,000 Duplicate Requests)
Simulates network failure replay storms sending identical `Idempotency-Key` headers, proving exact single-execution semantics and zero double-debiting:
```bash
k6 run benchmarks/03_idempotency_retry_storm.js
```

### Run Entire Benchmark Suite Automatically:
```bash
# Windows PowerShell
.\benchmarks\run_benchmarks.ps1

# Linux / macOS
./benchmarks/run_benchmarks.sh
```