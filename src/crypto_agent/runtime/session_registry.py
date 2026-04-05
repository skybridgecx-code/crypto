from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.runtime.models import (
    ForwardPaperRuntimeRegistry,
    ForwardPaperRuntimeRegistryEntry,
    ForwardPaperRuntimeStatus,
)


def load_forward_paper_registry(path: str | Path) -> ForwardPaperRuntimeRegistry:
    registry_path = Path(path)
    if not registry_path.exists():
        return ForwardPaperRuntimeRegistry(
            registry_path=registry_path,
            runtime_count=0,
            runtimes=[],
        )
    return ForwardPaperRuntimeRegistry.model_validate(
        json.loads(registry_path.read_text(encoding="utf-8"))
    )


def write_forward_paper_registry(
    path: str | Path,
    registry: ForwardPaperRuntimeRegistry,
) -> Path:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_runtimes = sorted(registry.runtimes, key=lambda entry: entry.runtime_id)
    payload = registry.model_copy(
        update={
            "registry_path": registry_path,
            "runtime_count": len(ordered_runtimes),
            "runtimes": ordered_runtimes,
        }
    )
    registry_path.write_text(
        json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return registry_path


def registry_entry_from_status(
    status: ForwardPaperRuntimeStatus,
) -> ForwardPaperRuntimeRegistryEntry:
    return ForwardPaperRuntimeRegistryEntry(
        runtime_id=status.runtime_id,
        mode=status.mode,
        market_source=status.market_source,
        replay_path=status.replay_path,
        live_symbol=status.live_symbol,
        live_interval=status.live_interval,
        runtime_dir=status.status_path.parent,
        status_path=status.status_path,
        history_path=status.history_path,
        sessions_dir=status.sessions_dir,
        live_market_status_path=status.live_market_status_path,
        venue_constraints_path=status.venue_constraints_path,
        starting_equity_usd=status.starting_equity_usd,
        session_interval_seconds=status.session_interval_seconds,
        status=status.status,
        next_session_number=status.next_session_number,
        active_session_id=status.active_session_id,
        last_session_id=status.last_session_id,
        updated_at=status.updated_at,
    )


def upsert_forward_paper_registry_entry(
    path: str | Path,
    status: ForwardPaperRuntimeStatus,
) -> Path:
    registry = load_forward_paper_registry(path)
    entry = registry_entry_from_status(status)
    runtimes = [runtime for runtime in registry.runtimes if runtime.runtime_id != status.runtime_id]
    runtimes.append(entry)
    return write_forward_paper_registry(
        path,
        ForwardPaperRuntimeRegistry(
            registry_path=Path(path),
            runtime_count=len(runtimes),
            runtimes=runtimes,
        ),
    )
