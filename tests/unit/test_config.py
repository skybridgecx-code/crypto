from pathlib import Path

import pytest

from crypto_agent.config import Settings, dump_settings, load_settings
from crypto_agent.enums import Mode


def test_load_settings_reads_expected_values() -> None:
    settings = load_settings(Path("config/default.yaml"))

    assert settings.mode is Mode.RESEARCH_ONLY
    assert settings.app.name == "crypto-agent"
    assert settings.paths.data_dir == Path("data")
    assert settings.venue.allowed_symbols == ["BTCUSDT", "ETHUSDT"]
    assert settings.risk.risk_per_trade_fraction == 0.005
    assert settings.risk.max_open_positions == 3
    assert settings.policy.kill_switch_enabled is True
    assert settings.policy.max_consecutive_order_rejects == 3


def test_dump_settings_returns_plain_mapping() -> None:
    dumped = dump_settings(Settings())

    assert dumped["mode"] == "research_only"
    assert dumped["app"]["environment"] == "local"
    assert dumped["paths"]["schemas_dir"] == "schemas"


def test_load_settings_rejects_invalid_mode(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("mode: unsupported\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mode"):
        load_settings(config_file)


def test_load_settings_rejects_live_orders_outside_limited_live(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid_live_orders.yaml"
    config_file.write_text(
        "mode: paper\npolicy:\n  allow_live_orders: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allow_live_orders"):
        load_settings(config_file)
