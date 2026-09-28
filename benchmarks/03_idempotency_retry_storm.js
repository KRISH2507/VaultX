import http from 'k6/http';
import { check } from 'k6';

const SRC_ACCOUNT = '11111111-1111-1111-1111-111111111111';
const DEST_ACCOUNT = '22222222-2222-2222-2222-222222222222';
const STATIC_IDEMPOTENCY_KEY = 'static-idemp-storm-test-uuid-9999';

export const options = {
  scenarios: {
    retry_storm: {
      executor: 'shared-iterations',
      vus: 100,               // 100 concurrent workers
      iterations: 1000,       // 1,000 total repeated requests with the EXACT same idempotency key
      maxDuration: '20s',
    },
  },
  thresholds: {
    // All requests must return either 201 (initial commit) or 200/409 (cached/in-progress) without 500 error
    http_req_failed: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000/api/v1';

export default function () {
  const payload = JSON.stringify({
    source_account_id: SRC_ACCOUNT,
    destination_account_id: DEST_ACCOUNT,
    amount: '10.00',
    currency: 'INR',
    description: 'Idempotency retry storm benchmark',
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': STATIC_IDEMPOTENCY_KEY,
    },
    timeout: '5s',
  };

  const res = http.post(`${BASE_URL}/transfers`, payload, params);

  check(res, {
    'valid idempotency handling (200, 201, or 409)': (r) =>
      r.status === 200 || r.status === 201 || r.status === 409,
    'zero 500 internal errors': (r) => r.status !== 500,
  });
}
