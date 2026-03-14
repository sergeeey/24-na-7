"""Проверка Incident Memory System ledger.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from src.utils.incidents import (
        LEDGER_PATH,
        build_incident_summary,
        load_incident_ledger,
        validate_incident_ledger,
    )

    parser = argparse.ArgumentParser(description="Validate incident ledger policy")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=LEDGER_PATH,
        help="Path to ledger.yaml",
    )
    args = parser.parse_args()

    payload = load_incident_ledger(args.ledger)
    errors = validate_incident_ledger(payload)
    if errors:
        print("Incident ledger validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    summary = build_incident_summary(payload)
    print(
        "Incident ledger OK: "
        f"total={summary['total']} "
        f"open={summary['open']} "
        f"in_progress={summary['in_progress']} "
        f"closed={summary['closed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
