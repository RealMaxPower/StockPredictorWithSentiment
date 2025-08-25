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
from datetime import datetime
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
                                page_size: int = 5,
                                max_retries: int = 3,
                                timeout: int = 10) -> Tuple[List[Dict[str, Any]], float]:
    """
    Fetch top `page_size` headlines mentioning the ticker with retry logic and timeout handling.
    Includes exponential backoff for failed requests.
    """
    # Convert ticker to company name for better news search results
    company_name = ticker_to_company_name(ticker)
    search_term = company_name if company_name != ticker else ticker
    
    for attempt in range(max_retries):
        try:
            print(f"Fetching news for {ticker} (searching for '{search_term}') (attempt {attempt + 1}/{max_retries})...")
            
            # Note: newsapi-python doesn't directly support timeout, but we can add a delay
            # to simulate rate limiting and reduce the chance of timeouts
            if attempt > 0:
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            
            resp = newsapi.get_top_headlines(
                q=search_term,
                category='business',
                page_size=page_size
            )
            
            if resp is None:
                raise Exception("NewsAPI returned None response")
                
            articles = resp.get('articles', [])
            if not articles and attempt < max_retries - 1:
                print(f"No articles found for {search_term}, retrying...")
                continue
                
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
            
            avg_sentiment = (sum(sentiments) / len(sentiments)) if sentiments else 0.0
            print(f"Successfully fetched {len(results)} articles for {ticker}")
            return results, avg_sentiment
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {ticker}: {e}")
            if attempt == max_retries - 1:
                print(f"All attempts failed for {ticker}, using empty news data")
                return [], 0.0
            
    # This should never be reached, but included for completeness
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
    Legacy wrapper for backward compatibility.
    Fetch top `page_size` headlines mentioning the ticker,
    compute VADER sentiment for each, and return list of dicts.
    """
    return fetch_ticker_news_with_retry(newsapi, sentiment_analyzer, ticker, page_size)


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

            # Fetch news and compute sentiment
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
