#!/bin/bash
set -e

echo "=========================================================="
echo " VaultX: High-Concurrency Benchmark Suite Execution"
echo "=========================================================="

echo -e "\n[Step 1/4] Seeding 500 Test Accounts..."
python benchmarks/seed_accounts.py --count 500 --balance 100000.00

echo -e "\n[Step 2/4] Executing 10k RPS High-Throughput Transfer Benchmark..."
k6 run benchmarks/01_high_throughput_transfers.js

echo -e "\n[Step 3/4] Executing Hot Account Contention Benchmark (Zero Deadlocks)..."
k6 run benchmarks/02_hot_account_contention.js

echo -e "\n[Step 4/4] Executing Idempotency Retry Storm Benchmark..."
k6 run benchmarks/03_idempotency_retry_storm.js

echo -e "\n=========================================================="
echo " Benchmark Suite Complete! Inspect metrics in Grafana at:"
echo " http://localhost:3000 (Credentials: admin / admin)"
echo "=========================================================="
