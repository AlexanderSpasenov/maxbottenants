"""Replay MAX webhook fixture to local endpoint.

Usage (Increment 3+):
  python scripts/replay_webhook.py app/integrations/max/fixtures/message_created.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--url", default="http://localhost:8000/webhook/max")
    parser.add_argument("--secret", default="")
    args = parser.parse_args()

    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    headers = {}
    if args.secret:
        headers["X-Max-Bot-Api-Secret"] = args.secret
    response = httpx.post(args.url, json=payload, headers=headers, timeout=10.0)
    print(response.status_code)
    print(response.text)


if __name__ == "__main__":
    main()
