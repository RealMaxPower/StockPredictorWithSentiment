"""Reproduce the monthly study from explicit snapshots, or opt in to fresh downloads.

Run from the checkout root: ``python -m scripts.regenerate_results --help``.
No SQLite cache or news service is used. Every requested ticker, including failures,
appears in summary.json; an interrupted run remains visibly incomplete.

Manifest schema 2 hashes the stored ``configuration_identity`` as sorted, compact
JSON. It contains only canonical simulation settings, so output paths and source
mode do not affect the hash. The full runtime configuration is retained separately.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
from dataclasses import asdict, replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pandas as pd

from stockpredictor import config, data, pipeline, strategy
from stockpredictor.reproducibility import code_version
from stockpredictor.sanitize import sanitize_ticker
from stockpredictor.serialization import json_safe

DEFAULT_TICKERS = ("AAPL", "MSFT", "KO", "JNJ", "XOM", "JPM", "SPY", "PG")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--prices-dir", type=Path, help="Directory of TICKER.csv files with Date and adjusted Close"
    )
    source.add_argument(
        "--download", action="store_true", help="Explicitly allow fresh yfinance I/O"
    )
    parser.add_argument("--outdir", type=Path, required=True, help="New directory for this run")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default="2005-01-01", help="Inclusive start date")
    parser.add_argument("--end", default="2025-01-01", help="Exclusive end date")
    parser.add_argument("--source-label", default="user-supplied adjusted-close snapshots")
    parser.add_argument("--sizing", choices=("vol", "kelly"), default="vol")
    parser.add_argument("--rf-rate", type=float, default=config.RF_ANNUAL)
    parser.add_argument("--commission-bps", type=float, default=config.COMMISSION_BPS)
    parser.add_argument("--spread-bps", type=float, default=config.SPREAD_BPS)
    parser.add_argument("--slippage-bps", type=float, default=config.SLIPPAGE_BPS)
    parser.add_argument("--fixed-fee", type=float, default=config.FIXED_FEE)
    parser.add_argument("--initial-capital", type=float, default=config.INITIAL_CAPITAL)
    parser.add_argument("--target-vol", type=float, default=config.TARGET_VOL)
    parser.add_argument("--kelly-fraction", type=float, default=config.KELLY_FRACTION)
    parser.add_argument("--final-period", type=int, default=config.HOLDOUT_PERIODS)
    return parser


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(json_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def _versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for dependency in ("numpy", "pandas", "statsmodels", "yfinance"):
        try:
            versions[dependency] = version(dependency)
        except PackageNotFoundError:
            versions[dependency] = None
    return versions


def _read_snapshot(contents: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(contents), float_precision="round_trip")
    if not {"Date", "Close"} <= set(frame.columns):
        raise ValueError("snapshot must contain Date and Close columns; Close must be adjusted")
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="raise")
    close = pd.to_numeric(frame["Close"], errors="raise")
    return pd.DataFrame({"Close": close.to_numpy()}, index=pd.DatetimeIndex(dates))


def main(argv: list[str] | None = None, *, downloader: data.Downloader | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        tickers = [sanitize_ticker(ticker) for ticker in args.tickers.split(",") if ticker.strip()]
        if not tickers or len(tickers) != len(set(tickers)):
            raise ValueError("provide at least one ticker, without duplicates")
        settings = config.AppConfig(
            tickers=tickers,
            start=args.start,
            end=args.end,
            outdir=str(args.outdir),
            sentiment_enabled=False,
            use_cache=False,
            sizing_method=args.sizing,
            rf_annual=args.rf_rate,
            commission_bps=args.commission_bps,
            spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
            fixed_fee=args.fixed_fee,
            initial_capital=args.initial_capital,
            target_vol=args.target_vol,
            kelly_fraction=args.kelly_fraction,
            holdout_periods=args.final_period,
        )
        args.outdir.mkdir(parents=True, exist_ok=False)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    snapshot_dir = args.outdir / "prices"
    snapshot_dir.mkdir()
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    entries: list[dict[str, Any]] = [{"ticker": ticker, "status": "pending"} for ticker in tickers]
    summary: dict[str, Any] = {
        "schema_version": 2,
        "status": "running",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_version": code_version(),
        "script_sha256": script_hash,
        "dependencies": _versions(),
        "configuration": asdict(settings),
        "requested_tickers": tickers,
        "source_mode": "download" if args.download else "csv",
        "experiment_history": "Not consulted; earlier variants tried are unknown.",
        "final_period_note": "Descriptive tail included in full scorecard; not an independent holdout.",
        "results": entries,
        "disclaimer": config.DISCLAIMER,
    }
    summary_path = args.outdir / "summary.json"
    _write_json(summary_path, summary)

    for entry in entries:
        ticker = entry["ticker"]
        cfg = replace(settings, tickers=[ticker])
        configuration = asdict(cfg)
        identity = {
            "schema": "simulation-configuration-v1",
            "settings": strategy.variant_config(cfg),
        }
        entry["configuration_identity"] = identity
        entry["configuration_sha256"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        source: dict[str, Any] = {
            "mode": summary["source_mode"],
            "label": "yfinance fresh auto_adjust=True" if args.download else args.source_label,
            "adjusted_close": "provider-adjusted" if args.download else "required; user-supplied",
        }
        entry["source"] = source
        payload: dict[str, Any] = {}
        try:
            if args.download:
                raw = data.fetch_prices(
                    ticker, cfg.start, cfg.end, downloader=downloader or data._default_downloader
                )
                close = data._extract_close(raw, ticker)
                frame = pd.DataFrame({"Close": close})
                if frame.index.tz is not None:
                    frame.index = frame.index.tz_localize(None)
                contents = frame.to_csv(index_label="Date", float_format="%.17g").encode()
            else:
                path = args.prices_dir / f"{ticker}.csv"
                source["path"] = str(path.resolve())
                contents = path.read_bytes()
            source["sha256"] = hashlib.sha256(contents).hexdigest()
            source["snapshot"] = f"prices/{ticker}.csv"
            (snapshot_dir / f"{ticker}.csv").write_bytes(contents)
            # Both modes use exactly the retained bytes so their inputs can be replayed.
            frame = _read_snapshot(contents)
            frame = frame.loc[(frame.index >= cfg.start) & (frame.index < cfg.end)].sort_index()
            if frame.empty:
                raise ValueError("no price observations in the requested [start, end) window")
            entry["observed_daily_range"] = [
                frame.index.min().strftime("%Y-%m-%d"),
                frame.index.max().strftime("%Y-%m-%d"),
            ]
            monthly, warnings = data.to_monthly(frame, ticker, end=cfg.end)
            requested_months = pd.period_range(
                cfg.start, pd.Timestamp(cfg.end) - pd.Timedelta(days=1), freq="M"
            )
            complete_requested = requested_months[requested_months.end_time < pd.Timestamp(cfg.end)]
            if len(monthly) < len(complete_requested):
                warnings.append(
                    f"only {len(monthly)} of {len(complete_requested)} requested complete months have prices; "
                    "inspect source coverage before interpreting results"
                )
            report = pipeline.run_simulation(ticker, cfg, monthly=monthly)
            report.warnings = warnings + report.warnings
            payload = pipeline.simulation_payload(report, cfg)
            payload.update({"status": "ok", "source": source})
            entry.update(
                {
                    "status": "ok",
                    "variant_id": report.variant_id,
                    "data_fingerprint": report.data_fingerprint,
                    "monthly_observations": len(monthly),
                    "scorecard": payload["scorecard"],
                    "final_period": payload["final_period"],
                    "warnings": report.warnings,
                }
            )
        except Exception as exc:  # noqa: BLE001 - retain every failed ticker in the study
            error = {"type": type(exc).__name__, "message": str(exc)}
            entry.update({"status": "error", "error": error})
            payload = {
                "ticker": ticker,
                "status": "error",
                "error": error,
                "source": source,
                "configuration": configuration,
                "code_version": summary["code_version"],
            }
        entry["metrics"] = f"{ticker}_SIM_metrics.json"
        _write_json(args.outdir / entry["metrics"], payload)
        _write_json(summary_path, summary)

    failed = sum(entry["status"] == "error" for entry in entries)
    summary.update(
        {
            "status": "complete" if failed == 0 else "complete_with_errors",
            "attempted": len(entries),
            "succeeded": len(entries) - failed,
            "failed": failed,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_json(summary_path, summary)
    print(
        f"{len(entries) - failed}/{len(entries)} studies completed; {failed} failed. See {summary_path}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
