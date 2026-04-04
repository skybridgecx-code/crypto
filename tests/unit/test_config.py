from pathlib import Path

from crypto_agent.config import Settings, dump_settings, load_settings


def test_load_settings_reads_expected_values() -> None:
    settings = load_settings(Path("config/default.yaml"))

    assert settings.mode == "research_only"
    assert settings.app.name == "crypto-agent"
    assert settings.paths.data_dir == Path("data")


def test_dump_settings_returns_plain_mapping() -> None:
    dumped = dump_settings(Settings())

    assert dumped["mode"] == "research_only"
    assert dumped["app"]["environment"] == "local"
