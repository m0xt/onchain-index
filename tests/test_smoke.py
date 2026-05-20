from __future__ import annotations

import importlib
import pkgutil

import onchain_pulse_index
from onchain_pulse_index import data


def test_import_every_package_module() -> None:
    prefix = onchain_pulse_index.__name__ + "."
    for module_info in pkgutil.walk_packages(onchain_pulse_index.__path__, prefix):
        importlib.import_module(module_info.name)


def test_data_entrypoint_dry_run(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("BMP_API_KEY", "test-key")

    result = data.main(["--dry-run", "--cache-dir", str(tmp_path)])

    assert result == 0
    assert "BMP_API_KEY present" in capsys.readouterr().out


def test_missing_secret_fails_fast(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BMP_API_KEY", raising=False)

    missing = tmp_path / ".env"
    try:
        data.validate_secrets(env_file=missing)
    except RuntimeError as exc:
        assert "BMP_API_KEY is missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing BMP_API_KEY should fail fast")
