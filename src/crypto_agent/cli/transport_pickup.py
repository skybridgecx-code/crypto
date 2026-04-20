from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from crypto_agent.transport.pickup import write_local_transport_pickup_receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read a local handoff_request.json and write a deterministic "
            "local transport pickup receipt."
        )
    )
    parser.add_argument(
        "handoff_request_path",
        help="Path to the canonical inbound handoff_request.json artifact.",
    )
    parser.add_argument(
        "--pickup-operator",
        required=True,
        help="Operator identifier recorded in the pickup receipt.",
    )
    parser.add_argument(
        "--picked-up-at-epoch-ns",
        required=True,
        type=int,
        help="Deterministic pickup timestamp in epoch nanoseconds.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.picked_up_at_epoch_ns < 0:
        print("transport_pickup_cli_error: picked_up_at_epoch_ns must be >= 0", file=sys.stderr)
        return 2

    try:
        result = write_local_transport_pickup_receipt(
            handoff_request_path=Path(args.handoff_request_path),
            pickup_operator=args.pickup_operator,
            picked_up_at_epoch_ns=args.picked_up_at_epoch_ns,
        )
    except ValueError as exc:
        print(f"transport_pickup_cli_error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
