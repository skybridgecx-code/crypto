from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from crypto_agent.transport.boundary_response import write_local_transport_boundary_response


def _parse_reason_codes(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read a local handoff request and matching pickup receipt, then write one "
            "canonical boundary response artifact (ack or reject)."
        )
    )
    parser.add_argument(
        "handoff_request_path",
        help="Path to the canonical inbound handoff_request.json artifact.",
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

    if args.responded_at_epoch_ns < 0:
        print(
            "transport_boundary_response_cli_error: responded_at_epoch_ns must be >= 0",
            file=sys.stderr,
        )
        return 2

    try:
        result = write_local_transport_boundary_response(
            handoff_request_path=Path(args.handoff_request_path),
            response_kind=args.response_kind,
            responded_at_epoch_ns=args.responded_at_epoch_ns,
            reason_codes=_parse_reason_codes(args.reason_codes),
            validation_error=args.validation_error,
        )
    except ValueError as exc:
        print(f"transport_boundary_response_cli_error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
