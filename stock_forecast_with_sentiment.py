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

import yfinance as yf
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import matplotlib.pyplot as plt
from newsapi import NewsApiClient
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def fetch_and_forecast(ticker: str, start: str, end: str):
    """
    Download daily closing prices for `ticker`, resample to monthly averages,
    fit a Holt–Winters model, and forecast 12 months ahead.
    Returns (monthly_series, forecast_series).
    """
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df.empty:
        raise ValueError(f"No data fetched for ticker '{ticker}'")
    monthly = df['Close'].resample('M').mean().dropna()
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
                      page_size: int = 5):
    """
    Fetch top `page_size` headlines mentioning the ticker,
    compute VADER sentiment for each, and return list of dicts.
    """
    resp = newsapi.get_top_headlines(
        q=ticker,
        category='business',
        page_size=page_size
    )
    articles = resp.get('articles', [])
    results = []
    sentiments = []
    for art in articles:
        title = art.get('title', '')
        desc = art.get('description') or ''
        combined = f"{title}. {desc}"
        score = sentiment_analyzer.polarity_scores(combined)['compound']
        sentiments.append(score)
        results.append({
            'title': title,
            'description': desc,
            'url': art.get('url'),
            'sentiment': score
        })
    return results, (sum(sentiments) / len(sentiments)) if sentiments else 0.0


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

    for ticker in tickers:
        try:
            print(f"Processing {ticker} from {args.start} to {args.end}...")
            monthly, forecast = fetch_and_forecast(ticker, args.start, args.end)

            # Fetch news and compute sentiment
            news_items, avg_sentiment = fetch_ticker_news(
                newsapi, sentiment_analyzer, ticker, page_size=args.pagesize
            )
            news_path = os.path.join(args.outdir, f"{ticker}_news.json")
            with open(news_path, 'w') as nf:
                json.dump(news_items, nf, indent=2)
            print(f"Saved news: {news_path} (avg sentiment: {avg_sentiment:.3f})")

            # Adjust forecast
            adjusted = adjust_forecast(forecast, avg_sentiment)

            # Plot and save
            plot_and_save(monthly, forecast, adjusted, ticker, args.outdir)

        except Exception as ex:
            print(f"Failed {ticker}: {ex}", file=sys.stderr)

if __name__ == '__main__':
    main()
