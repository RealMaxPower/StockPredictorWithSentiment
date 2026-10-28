"""Offline dashboard interaction tests; optional with the app extra."""

from unittest.mock import Mock

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import app  # noqa: E402
from stockpredictor import config, pipeline  # noqa: E402
from stockpredictor.store import Store  # noqa: E402


@pytest.fixture
def dashboard(monkeypatch, tmp_path, fake_downloader):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    cfg = config.AppConfig(start="2020-01-01", end="2025-01-01", db_path=str(tmp_path / "app.db"))
    result = pipeline.run_ticker("AAPL", cfg, price_downloader=fake_downloader, run_backtest=False)
    fetch = Mock(return_value=(result, cfg))
    monkeypatch.setattr(app, "_run", fetch)
    app._simulate.clear()
    yield AppTest.from_string("import app\napp.main()", default_timeout=30), cfg, fetch
    app._simulate.clear()


def test_dashboard_keeps_results_when_settings_change(dashboard):
    at, _, fetch = dashboard
    at.run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 0
    at.button[0].click().run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    at.slider[0].set_value(10).run()
    assert len(at.get("plotly_chart")) == 1
    assert fetch.call_count == 1
    at.button[0].click().run()
    assert fetch.call_count == 2


def test_dashboard_simulation_cache_and_distinct_history(dashboard, monkeypatch):
    at, cfg, _ = dashboard
    compute = Mock(wraps=app.run_simulation)
    monkeypatch.setattr(app, "run_simulation", compute)
    at.run().button[0].click().run()
    at.checkbox[1].check().run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 2
    assert compute.call_count == 1
    at.slider[0].set_value(10).run()
    assert compute.call_count == 1
    with Store(cfg.db_path) as store:
        assert store.count_simulations("AAPL") == 1
        assert store.count_simulation_runs("AAPL") == 1
    at.selectbox[1].set_value("kelly").run()
    assert not at.exception
    assert compute.call_count == 2
    with Store(cfg.db_path) as store:
        assert store.count_simulations("AAPL") == 2


def test_dashboard_surfaces_failed_forecast_without_exception(dashboard):
    at, _, fetch = dashboard
    fetch.side_effect = ValueError("No complete monthly prices")
    at.run().button[0].click().run()
    assert not at.exception
    assert "No complete monthly prices" in at.error[0].value
    assert len(at.get("plotly_chart")) == 0


def test_dashboard_history_failure_remains_untracked(dashboard, monkeypatch):
    at, cfg, _ = dashboard
    at.run().button[0].click().run()
    at.checkbox[1].check().run()
    with Store(cfg.db_path) as store:
        assert store.count_simulations("AAPL") == 1

    def fail(*args, **kwargs):
        raise OSError("database is read-only")

    monkeypatch.setattr(Store, "save_simulation", fail)
    at.selectbox[1].set_value("kelly").run()
    assert not at.exception
    assert any("database is read-only" in warning.value for warning in at.warning)
    assert "untracked" in at.code[0].value
