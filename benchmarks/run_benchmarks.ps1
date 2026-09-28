# PowerShell script to execute the full k6 load benchmark suite

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " VaultX: High-Concurrency Benchmark Suite Execution" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$baseUrl = "http://localhost:8000/api/v1"

# 1. Seed Accounts
Write-Host "`n[Step 1/4] Seeding 500 Test Accounts..." -ForegroundColor Yellow
python benchmarks/seed_accounts.py --count 500 --balance 100000.00

# 2. Benchmark 1: High-Throughput Transfers (10,000 RPS Target)
Write-Host "`n[Step 2/4] Executing 10k RPS High-Throughput Transfer Benchmark..." -ForegroundColor Yellow
k6 run benchmarks/01_high_throughput_transfers.js

# 3. Benchmark 2: Hot Account Contention (500 Concurrent Threads)
Write-Host "`n[Step 3/4] Executing Hot Account Contention Benchmark (Zero Deadlocks)..." -ForegroundColor Yellow
k6 run benchmarks/02_hot_account_contention.js

# 4. Benchmark 3: Idempotency Retry Storm (1,000 Concurrent Replays)
Write-Host "`n[Step 4/4] Executing Idempotency Retry Storm Benchmark..." -ForegroundColor Yellow
k6 run benchmarks/03_idempotency_retry_storm.js

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " Benchmark Suite Complete! Inspect metrics in Grafana at:" -ForegroundColor Green
Write-Host " http://localhost:3000 (Credentials: admin / admin)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
