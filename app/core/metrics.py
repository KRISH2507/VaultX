from prometheus_client import Counter, Histogram, Gauge

# Transfer Performance Metrics
TRANSFERS_TOTAL = Counter(
    "vaultx_transfers_total",
    "Total number of transfer attempts processed by VaultX",
    ["status"],  # committed, insufficient_balance, conflict, error
)

TRANSFER_DURATION_SECONDS = Histogram(
    "vaultx_transfer_duration_seconds",
    "End-to-end ACID transaction settlement duration in seconds",
    buckets=[0.001, 0.002, 0.005, 0.010, 0.015, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0],
)

# Distributed Idempotency Metrics
IDEMPOTENCY_HITS_TOTAL = Counter(
    "vaultx_idempotency_hits_total",
    "Total number of duplicate requests served from idempotency cache",
    ["tier"],  # redis, postgres
)

ACTIVE_TRANSFER_LOCKS = Gauge(
    "vaultx_active_transfer_locks",
    "Number of currently active in-flight transfer locks",
)

# Outbox Pipeline Metrics
OUTBOX_EVENTS_PROCESSED_TOTAL = Counter(
    "vaultx_outbox_events_processed_total",
    "Total outbox events dispatched by workers",
    ["event_type", "status"],  # success, failed
)
