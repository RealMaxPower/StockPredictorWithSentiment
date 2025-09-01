#!/usr/bin/env python3
"""
stock_forecast_with_sentiment.py

CLI app to fetch historical stock data, produce a 12‑month Holt–Winters forecast,
fetch top 5 news headlines for each ticker, analyze sentiment, adjust the forecast based
on sentiment, and save plots + news JSON to disk.
"""
import argparse
import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any

import yfinance as yf
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import matplotlib.pyplot as plt
from newsapi import NewsApiClient
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def ticker_to_company_name(ticker: str) -> str:
    """
    Convert stock ticker to company name for better news search results.
    Returns company name if mapping exists, otherwise returns the original ticker.
    """
    ticker_mapping = {
        'AAPL': 'Apple',
        'MSFT': 'Microsoft',
        'GOOGL': 'Google',
        'GOOG': 'Google',
        'AMZN': 'Amazon',
        'TSLA': 'Tesla',
        'META': 'Meta',
        'NVDA': 'NVIDIA',
        'NFLX': 'Netflix',
        'BA': 'Boeing',
        'JPM': 'JPMorgan',
        'JNJ': 'Johnson & Johnson',
        'V': 'Visa',
        'PG': 'Procter & Gamble',
        'UNH': 'UnitedHealth',
        'HD': 'Home Depot',
        'MA': 'Mastercard',
        'PFE': 'Pfizer',
        'DIS': 'Disney',
        'VZ': 'Verizon',
        'ADBE': 'Adobe',
        'NFLX': 'Netflix',
        'KO': 'Coca-Cola',
        'PEP': 'PepsiCo',
        'T': 'AT&T',
        'CVX': 'Chevron',
        'WMT': 'Walmart',
        'XOM': 'ExxonMobil',
        'INTC': 'Intel',
        'IBM': 'IBM',
        'ORCL': 'Oracle',
        'CSCO': 'Cisco',
        'CRM': 'Salesforce',
        'AVGO': 'Broadcom',
        'GME': 'GameStop',
        'AMC': 'AMC Entertainment',
        'BB': 'BlackBerry',
        'NOK': 'Nokia',
        'PLTR': 'Palantir',
        'RBLX': 'Roblox'
    }
    return ticker_mapping.get(ticker.upper(), ticker)


def create_date_specific_output_dir(base_dir: str) -> str:
    """
    Create a date-specific subdirectory within the base output directory.
    Returns the path to the date-specific directory.
    """
    current_date = datetime.now().strftime('%Y-%m-%d')
    date_dir = os.path.join(base_dir, current_date)
    os.makedirs(date_dir, exist_ok=True)
    return date_dir


def fetch_ticker_news_with_retry(newsapi: NewsApiClient,
                                sentiment_analyzer: SentimentIntensityAnalyzer,
                                ticker: str,
                                start_date: str = None,
                                end_date: str = None,
                                page_size: int = 5,
                                max_retries: int = 3,
                                timeout: int = 10) -> Tuple[List[Dict[str, Any]], float]:
    """
    Fetch headlines with retry/backoff. First try last 30 days (UTC) for NewsAPI,
    then fall back to no date filters if the plan rejects the range.
    """
    # Force last 30 days window (first attempt)
    end_dt = datetime.utcnow().date()
    start_dt = end_dt - timedelta(days=30)
    # Use YYYY-MM-DD format only
    forced_from = start_dt.isoformat()  
    forced_to   = end_dt.isoformat()    

    company = ticker_to_company_name(ticker.upper())
    query = f"\"{company}\" OR {ticker.upper()}"
    print(f"NewsAPI query for {ticker}: {query}")
    print(f"NewsAPI date window for {ticker}: {forced_from} to {forced_to}")

    tried_without_dates = False

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait = 2 ** attempt
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)

            kwargs = {
                "q": query,
                "language": "en",
                "sort_by": "relevancy",
                "page_size": page_size,
            }
            # Include date filters on first passes; drop if plan rejects them
            if not tried_without_dates:
                kwargs["from_param"] = forced_from
                kwargs["to"] = forced_to

            resp = newsapi.get_everything(**kwargs)

            # Explicitly handle error-style responses from NewsAPI
            if resp.get("code"):
                code = resp.get("code", "")
                msg = resp.get("message", "")
                print(f"NewsAPI error ({code}): {msg}")
                if (code == "parameterInvalid" and "far in the past" in msg) and not tried_without_dates:
                    print("Retrying without date filters due to NewsAPI plan limits...")
                    tried_without_dates = True
                    continue
                # For any other error, try next attempt (or exit on last)
                if attempt == max_retries - 1:
                    return [], 0.0
                continue

            articles = (resp or {}).get("articles", []) or []
            if not articles:
                # If no results with dates, try once without dates
                if not tried_without_dates:
                    print("No articles with date filters; retrying without date filters...")
                    tried_without_dates = True
                    continue
                if attempt < max_retries - 1:
                    print("No articles; retrying...")
                    continue

            results, sentiments = [], []
            for art in articles:
                title = art.get("title", "") or ""
                desc = art.get("description") or ""
                combined = f"{title}. {desc}".strip(". ")
                score = sentiment_analyzer.polarity_scores(combined)["compound"]
                sentiments.append(score)
                results.append({
                    "title": title,
                    "description": desc,
                    "url": art.get("url"),
                    "source": (art.get("source") or {}).get("name"),
                    "publishedAt": art.get("publishedAt"),
                    "sentiment": score,
                })

            avg_sentiment = (sum(sentiments) / len(sentiments)) if sentiments else 0.0
            print(f"Successfully fetched {len(results)} articles for {ticker}")
            return results, avg_sentiment

        except Exception as e:
            msg = str(e)
            print(f"Attempt {attempt + 1} failed for {ticker}: {msg}")
            if (("parameterInvalid" in msg) or ("too far in the past" in msg)) and not tried_without_dates:
                print("Retrying without date filters due to NewsAPI plan limits...")
                tried_without_dates = True
                continue
            if attempt == max_retries - 1:
                print(f"All attempts failed for {ticker}, using empty news data")
                return [], 0.0

    return [], 0.0


def fetch_and_forecast(ticker: str, start: str, end: str):
    """
    Download daily closing prices for `ticker`, resample to monthly averages,
    fit a Holt–Winters model, and forecast 12 months ahead.
    Returns (monthly_series, forecast_series).
    """
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df.empty:
        raise ValueError(f"No data fetched for ticker '{ticker}'")
    monthly = df['Close'].resample('ME').mean().dropna()
    model = ExponentialSmoothing(
        monthly,
        trend='add',
        seasonal='add',
        seasonal_periods=12
    )
    fit = model.fit(optimized=True)
    forecast = fit.forecast(12)
    return monthly, forecast


def fetch_ticker_news(newsapi: NewsApiClient,
                      sentiment_analyzer: SentimentIntensityAnalyzer,
                      ticker: str,
                      start_date: str = None,
                      end_date: str = None,
                      page_size: int = 5):
    """
    Wrapper kept for compatibility. Ignores provided dates and uses last 30 days.
    """
    return fetch_ticker_news_with_retry(newsapi, sentiment_analyzer, ticker, None, None, page_size)


def adjust_forecast(forecast: pd.Series, sentiment_score: float):
    """
    Adjust the forecast values based on sentiment score.
    A positive sentiment_score (>0) increases forecast proportionally,
    negative decreases it.
    """
    # Simple adjustment: multiply by (1 + sentiment_score)
    return forecast * (1 + sentiment_score)


def plot_and_save(monthly: pd.Series,
                  forecast: pd.Series,
                  adjusted: pd.Series,
                  ticker: str,
                  out_dir: str,
                  dpi: int = 150):
    """
    Plot historical, raw forecast, and sentiment-adjusted forecast for `ticker`,
    then save the figure under `out_dir`.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(monthly.index, monthly.values, label='Historical')
    ax.plot(forecast.index, forecast.values, label='Forecast')
    ax.plot(adjusted.index, adjusted.values, label='Sentiment‑Adjusted')
    ax.set_title(f"{ticker}: Historical & 12‑Month Forecast with Sentiment")
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    plt.tight_layout()

    filepath = os.path.join(out_dir, f"{ticker}_forecasts.png")
    fig.savefig(filepath, dpi=dpi)
    plt.close(fig)
    print(f"Saved plot: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description='Fetch, forecast, adjust with sentiment, and save results.'
    )
    parser.add_argument(
        '-t', '--tickers', required=True,
        help='Comma-separated stock tickers, e.g. GME,AAPL,MSFT'
    )
    parser.add_argument(
        '-s', '--start', required=True,
        help='Start date in YYYY-MM-DD format'
    )
    parser.add_argument(
        '-e', '--end', required=True,
        help='End date in YYYY-MM-DD format'
    )
    parser.add_argument(
        '-o', '--outdir', default='stock_plots',
        help='Directory for saving plots and news JSON'
    )
    parser.add_argument(
        '--pagesize', type=int, default=5,
        help='Number of news headlines to fetch per ticker'
    )
    args = parser.parse_args()

    # Prepare output directory
    os.makedirs(args.outdir, exist_ok=True)
    
    # Create date-specific subdirectory for this run
    date_specific_dir = create_date_specific_output_dir(args.outdir)
    print(f"Saving outputs to date-specific directory: {date_specific_dir}")

    # Check NewsAPI key
    news_api_key = os.getenv('NEWSAPI_KEY')
    if not news_api_key:
        print('Error: Set the NEWSAPI_KEY environment variable.', file=sys.stderr)
        sys.exit(1)
    newsapi = NewsApiClient(api_key=news_api_key)
    sentiment_analyzer = SentimentIntensityAnalyzer()

    tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    if not tickers:
        print('Error: No valid tickers provided.', file=sys.stderr)
        sys.exit(1)

    for i, ticker in enumerate(tickers):
        try:
            print(f"Processing {ticker} from {args.start} to {args.end}...")
            
            # Add a small delay between tickers to be nice to APIs (except for first ticker)
            if i > 0:
                print("Waiting 1 second between API calls...")
                time.sleep(1)
            
            monthly, forecast = fetch_and_forecast(ticker, args.start, args.end)

            # Fetch news and compute sentiment (do NOT pass CLI dates)
            news_items, avg_sentiment = fetch_ticker_news(
                newsapi, sentiment_analyzer, ticker, page_size=args.pagesize
            )
            news_path = os.path.join(date_specific_dir, f"{ticker}_news.json")
            with open(news_path, 'w') as nf:
                json.dump(news_items, nf, indent=2)
            print(f"Saved news: {news_path} (avg sentiment: {avg_sentiment:.3f})")

            # Adjust forecast
            adjusted = adjust_forecast(forecast, avg_sentiment)

            # Plot and save
            plot_and_save(monthly, forecast, adjusted, ticker, date_specific_dir)

        except Exception as ex:
            print(f"Failed {ticker}: {ex}", file=sys.stderr)

if __name__ == '__main__':
    main()
