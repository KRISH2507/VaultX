import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// Pre-generated dummy account UUIDs for fallback if accounts.json is not present
const FALLBACK_ACCOUNTS = [
  '11111111-1111-1111-1111-111111111111',
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333',
  '44444444-4444-4444-4444-444444444444',
  '55555555-5555-5555-5555-555555555555',
];

let accounts = FALLBACK_ACCOUNTS;
try {
  const loaded = JSON.parse(open('./accounts.json'));
  if (loaded && loaded.length > 1) {
    accounts = loaded.map((a) => a.id);
  }
} catch (e) {
  // Use fallback if accounts.json not seeded yet
}

export const options = {
  scenarios: {
    high_throughput_transfers: {
      executor: 'ramping-arrival-rate',
      startRate: 500,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 2000,
      stages: [
        { target: 2000, duration: '15s' },  // Warm-up ramp
        { target: 5000, duration: '30s' },  // Scale
        { target: 10000, duration: '30s' }, // Peak benchmark target (10,000 RPS)
        { target: 1000, duration: '15s' },  // Cool down
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],             // Less than 1% failure
    http_req_duration: ['p(95)<8', 'p(99)<15'], // p95 < 8ms, p99 < 15ms target
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000/api/v1';

export default function () {
  // Pick random distinct source and destination accounts
  const srcIdx = Math.floor(Math.random() * accounts.length);
  let destIdx = Math.floor(Math.random() * accounts.length);
  while (destIdx === srcIdx) {
    destIdx = Math.floor(Math.random() * accounts.length);
  }

  const srcAccount = accounts[srcIdx];
  const destAccount = accounts[destIdx];
  const idempotencyKey = uuidv4();

  const payload = JSON.stringify({
    source_account_id: srcAccount,
    destination_account_id: destAccount,
    amount: '1.00',
    currency: 'INR',
    description: 'k6 high throughput benchmark',
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    timeout: '5s',
  };

  const res = http.post(`${BASE_URL}/transfers`, payload, params);

  check(res, {
    'status is 201': (r) => r.status === 201,
    'latency below 10ms': (r) => r.timings.duration < 10,
  });
}
