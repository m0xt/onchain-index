from __future__ import annotations

import importlib
import pkgutil

import pandas as pd
import requests

import onchain_index
from onchain_index import data


def test_import_every_package_module() -> None:
    prefix = onchain_index.__name__ + "."
    for module_info in pkgutil.walk_packages(onchain_index.__path__, prefix):
        importlib.import_module(module_info.name)


def test_data_entrypoint_dry_run(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("BGEOMETRICS_TOKEN", raising=False)

    result = data.main(["--dry-run", "--cache-dir", str(tmp_path)])

    assert result == 0
    assert "no required secrets" in capsys.readouterr().out


def test_no_secret_required(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BGEOMETRICS_TOKEN", raising=False)
    assert data.validate_secrets(env_file=tmp_path / ".env") is None


def test_hodl_splice_level_shifts_live_series(monkeypatch, tmp_path) -> None:
    frozen = tmp_path / "hodl.csv"
    frozen.write_text("date,hodl_1yr_pct\n2026-08-29,61.0\n2026-08-30,61.1\n")

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return [
                {"d": "2026-08-30", "hodlOneYear": 0.70},
                {"d": "2026-08-31", "hodlOneYear": 0.71},
            ]

    monkeypatch.setattr(data.requests, "get", lambda *_args, **_kwargs: _Response())

    series = data.fetch_hodl_1y(token=None, frozen_csv=frozen)

    assert series.loc[pd.Timestamp("2026-08-30")] == 61.1
    assert series.loc[pd.Timestamp("2026-08-31")] == 62.1
    assert series.name == "hodl_1yr_pct"


def test_fetch_text_impersonates_browser_on_cloudflare_403(monkeypatch) -> None:
    class _Blocked:
        status_code = 403
        text = "challenge"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("403")

    class _Ok:
        text = "<html>flows</html>"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(data.requests, "get", lambda *_args, **_kwargs: _Blocked())
    import curl_cffi.requests as curl_requests

    monkeypatch.setattr(curl_requests, "get", lambda *_args, **_kwargs: _Ok())

    text = data._fetch_text("https://farside.co.uk/bitcoin-etf-flow-all-data/")
    assert text == "<html>flows</html>"


def test_binance_uses_vision_host_on_451(monkeypatch) -> None:
    calls: list[str] = []
    kline = [[1_791_331_200_000, "1", "1", "1", "83321.81", "1", 0, "0", 1, "0", "0", "0"]]

    class _Response:
        def __init__(self, status_code: int, body: list[list[object]]) -> None:
            self.status_code = status_code
            self._body = body

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(str(self.status_code))

        def json(self) -> list[list[object]]:
            return self._body

    def _get(url: str, **_kwargs: object) -> _Response:
        calls.append(url)
        if "binance.vision" in url:
            return _Response(200, kline)
        return _Response(451, [])

    monkeypatch.setattr(data.requests, "get", _get)

    frame = data._binance_daily_closes()

    assert calls == [data.BINANCE_KLINES_URL, data.BINANCE_VISION_KLINES_URL]
    assert frame.iloc[0]["binance"] == 83321.81
