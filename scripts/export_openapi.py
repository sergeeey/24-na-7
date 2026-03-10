from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.api.main import app


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Reflexio OpenAPI schema")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
