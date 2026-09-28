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

### 2. Start Infrastructure
```bash
docker compose up -d postgres redis
```

### 3. Run Migrations
```bash
alembic upgrade head
```

### 4. Run Test Suite
```bash
pytest
```