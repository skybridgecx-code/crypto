from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from crypto_agent.transport.archive import write_local_transport_archive


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read canonical local transport artifacts for an attempt and archive them "
            "under archive/<correlation_id>/<attempt_id>/."
        )
    )
    parser.add_argument(
        "handoff_request_path",
        help="Path to the canonical inbound handoff_request.json artifact.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = write_local_transport_archive(
            handoff_request_path=Path(args.handoff_request_path),
        )
    except ValueError as exc:
        print(f"transport_archive_cli_error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
