"""Create a trial account via the backend API."""
import argparse
import os
import sys

import requests


def main():
    parser = argparse.ArgumentParser(description="Create a trial account")
    parser.add_argument(
        "--url",
        default=os.getenv("API_URL", "http://localhost:8000"),
        help="Base API URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--secret",
        default=os.getenv("TRIAL_ADMIN_SECRET", ""),
        help="Admin secret (or set TRIAL_ADMIN_SECRET env var)",
    )
    args = parser.parse_args()

    if not args.secret:
        print("Error: admin secret is required (--secret or TRIAL_ADMIN_SECRET env)", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        f"{args.url}/api/auth/create-trial",
        json={"admin_secret": args.secret},
    )
    if resp.ok:
        data = resp.json()
        print(f"Trial account created successfully!")
        print(f"  Email:    {data['email']}")
        print(f"  Password: {data['password']}")
    else:
        print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
