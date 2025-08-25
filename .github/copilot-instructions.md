# Stock Predictor With Sentiment Analysis

**ALWAYS follow these instructions first and fallback to additional search and context gathering only if the information in the instructions is incomplete or found to be in error.**

This is a Python CLI application that fetches historical stock data, produces 12-month Holt-Winters forecasts, integrates sentiment analysis from news headlines, and generates visualization plots and data files.

## Working Effectively

### Environment Setup
- Ensure Python 3.8+ is available: `python3 --version`
- Use pip3 for package management: `which pip3`
- **Primary method**: Install all dependencies in one command (NEVER CANCEL - takes 2-3 minutes): 
  ```bash
  pip3 install yfinance pandas statsmodels matplotlib newsapi-python vaderSentiment
  ```
  - **TIMEOUT: Set to 300+ seconds for dependency installation**
  - Dependencies include data science packages with native extensions that require compilation time
- **Alternative method** (if pip fails due to network restrictions):
  ```bash
  # In environments where pip access to PyPI is restricted
  # Dependencies may need to be pre-installed or available via system packages
  # Contact system administrator for package availability
  ```

### Required Environment Variables
- **CRITICAL**: Set NEWSAPI_KEY environment variable before running:
  ```bash
  export NEWSAPI_KEY="your_api_key_here"
  ```
- Get API key from: https://newsapi.org
- Script will exit with error if NEWSAPI_KEY is not set

### Running the Application
- Basic usage: `python3 stock_forecast_with_sentiment.py --help`
- Full example command:
  ```bash
  python3 stock_forecast_with_sentiment.py \
    --tickers AAPL,NVDA,MSFT \
    --start 2023-01-01 \
    --end 2024-12-01 \
    --outdir ./stock_plots \
    --pagesize 5
  ```
- **EXECUTION TIME**: Processing takes 1-3 minutes per ticker depending on network speed
- Creates output directory automatically if it doesn't exist

## Validation and Testing

### Manual Validation Steps
**ALWAYS run these validation steps after making changes:**

1. **Basic functionality test**:
   ```bash
   python3 stock_forecast_with_sentiment.py --help
   ```
   Should display usage information without errors.

2. **Dependency validation**:
   ```bash
   python3 -c "import yfinance, pandas, statsmodels, matplotlib, newsapi, vaderSentiment; print('All dependencies available')"
   ```
   Expected output: "All dependencies available"

3. **Dependency status check** (if import fails):
   ```bash
   pip3 list | grep -E "(yfinance|pandas|statsmodels|matplotlib|newsapi|vader)"
   ```
   Should show installed versions of required packages.

4. **Environment variable test**:
   ```bash
   python3 stock_forecast_with_sentiment.py --tickers AAPL --start 2024-01-01 --end 2024-02-01
   ```
   Should fail with "Error: Set the NEWSAPI_KEY environment variable." if key not set.

5. **Full functionality test** (requires valid API key and network access):
   ```bash
   export NEWSAPI_KEY="your_key"
   python3 stock_forecast_with_sentiment.py --tickers AAPL --start 2024-01-01 --end 2024-02-01 --outdir ./test_output
   ```
   Should create plots and JSON files in test_output directory.

### Expected Outputs
- PNG plot files: `{TICKER}_forecasts.png`
- JSON news files: `{TICKER}_news.json`
- Console output showing processing progress and sentiment scores
- Files saved in specified output directory (default: `stock_plots`)

### Validation Scenarios
**Test these scenarios to ensure full functionality:**
1. **Single ticker**: Test with one stock symbol
2. **Multiple tickers**: Test with comma-separated list
3. **Different date ranges**: Test various start/end date combinations
4. **Output directory**: Verify files are created in correct location
5. **Error handling**: Test invalid tickers, date formats, missing API key

## Code Structure

### Main Script: `stock_forecast_with_sentiment.py`
- **fetch_and_forecast()**: Downloads stock data using yfinance, applies Holt-Winters forecasting
- **fetch_ticker_news()**: Retrieves news headlines via NewsAPI, computes VADER sentiment scores
- **adjust_forecast()**: Modifies forecast based on sentiment analysis
- **plot_and_save()**: Creates visualization plots and saves to PNG files
- **main()**: Command-line interface and orchestration

### Key Dependencies and Their Purposes
- `yfinance`: Yahoo Finance data fetching
- `pandas`: Data manipulation and time series handling
- `statsmodels`: Holt-Winters exponential smoothing models
- `matplotlib`: Plot generation and visualization
- `newsapi-python`: News headline retrieval
- `vaderSentiment`: Sentiment analysis of news text

## Common Issues and Troubleshooting

### Network and API Issues
- **Yahoo Finance access**: Requires internet connectivity to fetch stock data
- **NewsAPI rate limits**: Free tier has request limitations
- **DNS resolution**: Yahoo Finance uses external domains that may be blocked

### Environment Issues
- **Python version**: Requires Python 3.8+ for compatibility with all dependencies
- **Missing dependencies**: Run dependency installation command if import errors occur
- **PyPI connectivity**: pip install may fail in restricted network environments (use pre-installed packages when available)
- **API key format**: Ensure NEWSAPI_KEY is set as environment variable, not hardcoded

### Sandbox Environment Limitations
- **No external network**: Cannot fetch real stock or news data in isolated environments
- **PyPI access restrictions**: pip install may fail with timeout errors in restricted environments
- **Limited validation**: Full testing requires network access and valid API credentials
- **Error simulation**: Use invalid API keys to test error handling paths
- **Dependency persistence**: Once installed, dependencies should persist between sessions

## File Organization

### Repository Root
```
.
├── README.md                           # Basic usage instructions
├── LICENSE                            # GPL-3.0 license
├── stock_forecast_with_sentiment.py   # Main application script
└── .github/
    └── copilot-instructions.md        # This file
```

### Generated Output Structure
```
stock_plots/                   # Default output directory
├── AAPL_forecasts.png        # Stock forecast visualization
├── AAPL_news.json           # News sentiment analysis data
├── MSFT_forecasts.png       # Additional ticker results
└── MSFT_news.json           # Additional ticker results
```

## Development Guidelines

### Making Changes
- **No build process**: This is a script-based project, no compilation required
- **No tests**: Add validation by running manual test scenarios above
- **Code style**: Follow existing Python conventions in the script
- **Dependencies**: Avoid adding new dependencies unless absolutely necessary

### Before Committing Changes
1. Run basic validation steps listed above
2. Test with multiple tickers if modifying core logic
3. Verify error handling with invalid inputs
4. Check that output files are generated correctly

### Performance Considerations
- Processing time scales linearly with number of tickers
- Network latency affects Yahoo Finance data fetching
- NewsAPI requests are rate-limited on free tier
- Matplotlib plot generation is CPU-intensive for large datasets

## CRITICAL WARNINGS

- **NEVER CANCEL** dependency installation - compilation of native extensions takes time
- **ALWAYS** test with valid NEWSAPI_KEY when modifying news/sentiment functionality  
- **NETWORK REQUIRED** for full functionality testing - script cannot work offline
- **API LIMITS** apply to NewsAPI free tier - avoid excessive testing requests
