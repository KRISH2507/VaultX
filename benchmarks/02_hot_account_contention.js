import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// Hot Account: all users transfer into this central merchant account simultaneously
const MERCHANT_ACCOUNT = '00000000-0000-0000-0000-000000000001';

const FALLBACK_USERS = [
  '11111111-1111-1111-1111-111111111111',
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333',
  '44444444-4444-4444-4444-444444444444',
  '55555555-5555-5555-5555-555555555555',
];

let userAccounts = FALLBACK_USERS;
try {
  const loaded = JSON.parse(open('./accounts.json'));
  if (loaded && loaded.length > 2) {
    userAccounts = loaded.slice(1).map((a) => a.id);
  }
} catch (e) {}

export const options = {
  scenarios: {
    hot_account_stress: {
      executor: 'constant-vus',
      vus: 500,          // 500 concurrent threads hammering 1 merchant account
      duration: '30s',
    },
  },
  thresholds: {
    // Zero deadlocks: status must NOT be 500
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000/api/v1';

export default function () {
  const userAccount = userAccounts[Math.floor(Math.random() * userAccounts.length)];
  const idempotencyKey = uuidv4();

  const payload = JSON.stringify({
    source_account_id: userAccount,
    destination_account_id: MERCHANT_ACCOUNT,
    amount: '0.50',
    currency: 'INR',
    description: 'Hot account contention stress test',
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
    'no deadlock (not 500)': (r) => r.status !== 500,
    'status is 201 or 422': (r) => r.status === 201 || r.status === 422,
  });
}
