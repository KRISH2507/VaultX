"""
Script to seed accounts for k6 load testing.
Usage:
    python benchmarks/seed_accounts.py --count 1000 --balance 10000.00
"""
import argparse
import asyncio
import json
import uuid
import httpx

BASE_URL = "http://localhost:8000/api/v1"


async def create_account(client: httpx.AsyncClient, idx: int, initial_balance: str) -> dict:
    user_id = str(uuid.uuid4())
    payload = {
        "user_id": user_id,
        "currency": "INR",
        "initial_balance": initial_balance,
    }
    response = await client.post(f"{BASE_URL}/accounts", json=payload)
    if response.status_code == 201:
        data = response.json()
        return {"id": data["id"], "user_id": user_id, "balance": initial_balance}
    else:
        print(f"Failed to create account {idx}: {response.text}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="Seed accounts for VaultX load tests")
    parser.add_argument("--count", type=int, default=500, help="Number of accounts to create")
    parser.add_argument("--balance", type=str, default="100000.00", help="Initial balance per account")
    parser.add_argument("--out", type=str, default="benchmarks/accounts.json", help="Output file")
    args = parser.parse_args()

    print(f"Seeding {args.count} accounts with initial balance of {args.balance} INR...")

    accounts = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check health
        try:
            health = await client.get("http://localhost:8000/health")
            if health.status_code != 200:
                print("VaultX API is not reachable at http://localhost:8000")
                return
        except Exception as e:
            print(f"Cannot connect to VaultX API: {e}")
            return

        batch_size = 50
        for i in range(0, args.count, batch_size):
            tasks = [
                create_account(client, i + j, args.balance)
                for j in range(min(batch_size, args.count - i))
            ]
            results = await asyncio.gather(*tasks)
            accounts.extend([r for r in results if r is not None])
            print(f"Created {len(accounts)} / {args.count} accounts...")

    with open(args.out, "w") as f:
        json.dump(accounts, f, indent=2)

    print(f"Successfully seeded {len(accounts)} accounts. Saved to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
