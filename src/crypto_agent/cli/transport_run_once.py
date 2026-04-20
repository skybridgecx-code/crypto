from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from crypto_agent.transport.runner import run_local_transport_one_shot


def _parse_reason_codes(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one deterministic local transport attempt: pickup receipt, one boundary "
            "response artifact (ack or reject), and archive copy."
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
    parser.add_argument(
        "--response-kind",
        required=True,
        choices=("ack", "reject"),
        help="Boundary response kind to write.",
    )
    parser.add_argument(
        "--responded-at-epoch-ns",
        required=True,
        type=int,
        help="Deterministic response timestamp in epoch nanoseconds.",
    )
    parser.add_argument(
        "--reason-codes",
        default=None,
        help=(
            "Comma-separated reason codes for reject responses. "
            "Required when --response-kind=reject."
        ),
    )
    parser.add_argument(
        "--validation-error",
        default=None,
        help="Validation error message for reject responses.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.picked_up_at_epoch_ns < 0:
        print("transport_run_once_cli_error: picked_up_at_epoch_ns must be >= 0", file=sys.stderr)
        return 2
    if args.responded_at_epoch_ns < 0:
        print("transport_run_once_cli_error: responded_at_epoch_ns must be >= 0", file=sys.stderr)
        return 2

    try:
        result = run_local_transport_one_shot(
            handoff_request_path=Path(args.handoff_request_path),
            pickup_operator=args.pickup_operator,
            picked_up_at_epoch_ns=args.picked_up_at_epoch_ns,
            response_kind=args.response_kind,
            responded_at_epoch_ns=args.responded_at_epoch_ns,
            reason_codes=_parse_reason_codes(args.reason_codes),
            validation_error=args.validation_error,
        )
    except ValueError as exc:
        print(f"transport_run_once_cli_error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
