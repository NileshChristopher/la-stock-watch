"""
LA Stock Watch — Build Script
Fetches market data for SoCal public companies,
computes weekly rankings, and generates static HTML pages.

Uses Yahoo Finance (via yfinance) — no API key required.
Weekly change is calculated by comparing current prices to stored
prices from the previous week's build.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"
OUTPUT_DIR = PROJECT_ROOT / "docs"
PRICE_HISTORY_FILE = DATA_DIR / "price_history.json"

# ---------------------------------------------------------------------------
# Anchor companies — must be present for build integrity
# These are SoCal's largest public companies by market cap.
# If any fail to fetch, we print a loud warning (but still generate the site).
# ---------------------------------------------------------------------------

ANCHOR_COMPANIES = {
    "DIS": "Walt Disney Co",
    "AMGN": "Amgen",
    "QCOM": "Qualcomm",
    "ILMN": "Illumina",
    "CMG": "Chipotle",
    "SRE": "Sempra",
    "DXCM": "Dexcom",
    "PSA": "Public Storage",
    "O": "Realty Income",
    "EW": "Edwards Lifesciences",
    "TTD": "The Trade Desk",
    "DECK": "Deckers",
    "RKLB": "Rocket Lab",
    "RMD": "ResMed",
    "NBIX": "Neurocrine",
}

# ---------------------------------------------------------------------------
# Price history (for true week-over-week comparison)
# ---------------------------------------------------------------------------


def load_price_history():
    """
    Load last week's prices from file.
    Returns dict of {ticker: price} or empty dict if no history exists.
    """
    if PRICE_HISTORY_FILE.exists():
        with open(PRICE_HISTORY_FILE) as f:
            data = json.load(f)
            return data.get("prices", {})
    return {}


def save_price_history(prices, build_date):
    """
    Save current prices for next week's comparison.
    prices: dict of {ticker: price}
    """
    data = {
        "saved_at": build_date.isoformat(),
        "prices": prices,
    }
    with open(PRICE_HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved prices for {len(prices)} tickers → {PRICE_HISTORY_FILE.name}")


# ---------------------------------------------------------------------------
# Data fetching (using yfinance — free, no API key)
# ---------------------------------------------------------------------------


def load_companies():
    """Load the curated list of SoCal tickers."""
    with open(DATA_DIR / "socal_companies.json") as f:
        return json.load(f)


def fetch_quotes(tickers):
    """
    Fetch quotes for all tickers using yfinance.
    yfinance can fetch multiple tickers at once efficiently.
    Returns list of quote dicts.
    """
    print(f"  Downloading data for {len(tickers)} tickers...")

    # yfinance can handle multiple tickers in one call
    tickers_str = " ".join(tickers)
    data = yf.download(
        tickers_str,
        period="5d",  # Get last 5 days
        group_by="ticker",
        progress=False,
        threads=True,
    )

    # Also get info for each ticker (P/E, market cap, etc.)
    all_quotes = []
    failed = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get current price from the download data
            if len(tickers) == 1:
                # Single ticker: data is not nested
                current_price = float(data["Close"].iloc[-1])
            else:
                # Multiple tickers: data is nested by ticker
                if ticker in data.columns.get_level_values(0):
                    current_price = float(data[ticker]["Close"].iloc[-1])
                else:
                    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            if current_price and current_price > 0:
                all_quotes.append({
                    "symbol": ticker,
                    "price": current_price,
                    "yearHigh": info.get("fiftyTwoWeekHigh", 0),
                    "yearLow": info.get("fiftyTwoWeekLow", 0),
                    "marketCap": info.get("marketCap", 0),
                    "pe": info.get("trailingPE"),
                    "volume": info.get("volume", 0),
                })
        except Exception as e:
            failed.append(ticker)

    if failed:
        print(f"  Warning: Failed to fetch {len(failed)} tickers: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}")

    return all_quotes


def validate_anchor_companies(quotes):
    """
    Check that all anchor companies were successfully fetched.
    Prints loud warnings for any missing anchors (but doesn't fail the build).
    Returns the list of missing anchor tickers.
    """
    fetched_tickers = {q["symbol"] for q in quotes}
    missing = []

    for ticker, name in ANCHOR_COMPANIES.items():
        if ticker not in fetched_tickers:
            missing.append((ticker, name))

    if missing:
        print()
        print("=" * 60)
        print("⚠️  ANCHOR COMPANY VALIDATION FAILED")
        print("=" * 60)
        for ticker, name in missing:
            print(f"  ⚠️  WARNING: Missing anchor company: {ticker} ({name})")
        print()
        print("These are major SoCal companies that should always be present.")
        print("Investigate why they failed to fetch before the next build.")
        print("=" * 60)
        print()

    return [t for t, n in missing]


def fetch_historical(ticker, days=7):
    """
    Fetch recent daily closing prices for sparkline charts.
    Returns a list of floats (oldest → newest).
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="7d")
        if not hist.empty:
            prices = hist["Close"].tolist()
            return [round(p, 2) for p in prices]
    except Exception as e:
        print(f"    Warning: Failed to fetch history for {ticker}: {e}")
    return []


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------


def build_rankings(companies, quotes, previous_prices):
    """
    Merge company info with quote data.
    Calculate week-over-week change using previous_prices.
    Return sorted gainers (top 25), losers (bottom 25), and all enriched data.
    """
    # Build a lookup from ticker → company metadata
    company_map = {c["ticker"]: c for c in companies}

    enriched = []
    current_prices = {}  # To save for next week

    for q in quotes:
        ticker = q.get("symbol", "")
        if ticker not in company_map:
            continue

        meta = company_map[ticker]
        current_price = q.get("price", 0) or 0
        current_prices[ticker] = current_price

        # Calculate week-over-week change
        if ticker in previous_prices and previous_prices[ticker] > 0:
            last_price = previous_prices[ticker]
            week_change = ((current_price - last_price) / last_price) * 100
        else:
            # No previous data — calculate from 52-week low as rough approximation
            # (This only happens on first run)
            year_low = q.get("yearLow", 0)
            if year_low and year_low > 0:
                week_change = ((current_price - year_low) / year_low) * 100 / 52  # Rough weekly avg
            else:
                week_change = 0

        enriched.append(
            {
                "rank": 0,
                "name": meta["name"],
                "ticker": ticker,
                "city": meta["city"],
                "price": current_price,
                "change_pct": round(week_change, 2),
                "year_high": q.get("yearHigh", 0),
                "year_low": q.get("yearLow", 0),
                "market_cap": q.get("marketCap", 0),
                "pe": q.get("pe"),
                "volume": q.get("volume", 0),
            }
        )

    # Sort by weekly change %
    enriched.sort(key=lambda x: x["change_pct"], reverse=True)

    # Top 25 gainers
    gainers = enriched[:25]
    for i, g in enumerate(gainers, 1):
        g["rank"] = i

    # Bottom 25 losers (worst first)
    losers = sorted(enriched, key=lambda x: x["change_pct"])[:25]
    for i, l in enumerate(losers, 1):
        l["rank"] = i

    return gainers, losers, enriched, current_prices


def compute_pe_extremes(enriched):
    """Find the 3 highest and 3 lowest P/E ratios (excluding None/0)."""
    with_pe = [s for s in enriched if s["pe"] and s["pe"] > 0]
    with_pe.sort(key=lambda x: x["pe"], reverse=True)
    highest = with_pe[:3]
    lowest = with_pe[-3:]
    return highest, lowest


def get_initials(name):
    """Get 1-2 character initials for avatar display."""
    words = name.replace(".", "").split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper()


def format_market_cap(value):
    """Format market cap as human-readable string."""
    if not value:
        return "N/A"
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.1f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.0f}M"
    return f"${value:,.0f}"


def format_price(value):
    """Format price with 2 decimal places."""
    if not value:
        return "$0.00"
    return f"${value:,.2f}"


def compute_52_week_change(stock):
    """Approximate 52-week change from year low to current price."""
    if stock["year_low"] and stock["year_low"] > 0:
        return round(
            ((stock["price"] - stock["year_low"]) / stock["year_low"]) * 100, 1
        )
    return 0


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def render_site(gainers, losers, pe_highest, pe_lowest, spotlight_gainer,
                spotlight_loser, gainer_sparkline, loser_sparkline, build_date,
                is_first_run=False):
    """Render Jinja2 templates to static HTML in docs/."""

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    env.filters["initials"] = get_initials
    env.filters["market_cap"] = format_market_cap
    env.filters["price"] = format_price

    common_context = {
        "build_date": build_date,
        "year": build_date.year,
        "is_first_run": is_first_run,
    }

    # --- Homepage ---
    index_tmpl = env.get_template("index.html")
    index_html = index_tmpl.render(
        spotlight_gainer=spotlight_gainer,
        spotlight_loser=spotlight_loser,
        gainer_sparkline=json.dumps(gainer_sparkline),
        loser_sparkline=json.dumps(loser_sparkline),
        pe_highest=pe_highest,
        pe_lowest=pe_lowest,
        **common_context,
    )

    # --- Rankings ---
    rankings_tmpl = env.get_template("rankings.html")
    rankings_html = rankings_tmpl.render(
        gainers=gainers,
        losers=losers,
        **common_context,
    )

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(index_html)
    (OUTPUT_DIR / "rankings.html").write_text(rankings_html)

    # Copy static assets
    static_out = OUTPUT_DIR / "static"
    if static_out.exists():
        shutil.rmtree(static_out)
    shutil.copytree(STATIC_DIR, static_out)

    print(f"✓ Site built → {OUTPUT_DIR}")
    print(f"  index.html    ({len(index_html):,} bytes)")
    print(f"  rankings.html ({len(rankings_html):,} bytes)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("LA Stock Watch — Building site with live data")
    print("=" * 50)

    companies = load_companies()
    tickers = [c["ticker"] for c in companies]

    # Load last week's prices for comparison
    previous_prices = load_price_history()
    is_first_run = len(previous_prices) == 0
    if is_first_run:
        print("  First run — no previous prices to compare")
        print("  (Next week's build will show true week-over-week change)")
    else:
        print(f"  Loaded {len(previous_prices)} previous prices for comparison")

    print(f"\nFetching market data for {len(tickers)} companies...")
    quotes = fetch_quotes(tickers)
    print(f"  Got quotes for {len(quotes)} companies")

    # Validate that anchor companies were fetched
    missing_anchors = validate_anchor_companies(quotes)

    if len(quotes) < 10:
        print("\n⚠ Too few quotes fetched. Check network connection.")
        return

    gainers, losers, enriched, current_prices = build_rankings(
        companies, quotes, previous_prices
    )
    pe_highest, pe_lowest = compute_pe_extremes(enriched)

    # Add 52-week change to all stocks
    for stock in gainers + losers:
        stock["year_change"] = compute_52_week_change(stock)

    # Spotlight: top gainer and top loser
    spotlight_gainer = gainers[0] if gainers else None
    spotlight_loser = losers[0] if losers else None

    print(f"\n  Top gainer: {spotlight_gainer['name']} ({spotlight_gainer['ticker']}) +{spotlight_gainer['change_pct']}%")
    print(f"  Top loser:  {spotlight_loser['name']} ({spotlight_loser['ticker']}) {spotlight_loser['change_pct']}%")

    # Fetch sparkline data (7-day price history for the chart)
    gainer_sparkline = []
    loser_sparkline = []
    if spotlight_gainer:
        print(f"\n  Fetching sparkline for {spotlight_gainer['ticker']}...")
        gainer_sparkline = fetch_historical(spotlight_gainer["ticker"])
    if spotlight_loser:
        print(f"  Fetching sparkline for {spotlight_loser['ticker']}...")
        loser_sparkline = fetch_historical(spotlight_loser["ticker"])

    build_date = datetime.now(timezone.utc)

    # Save current prices for next week's comparison
    print()
    save_price_history(current_prices, build_date)

    print()
    render_site(
        gainers, losers, pe_highest, pe_lowest,
        spotlight_gainer, spotlight_loser,
        gainer_sparkline, loser_sparkline,
        build_date,
        is_first_run=is_first_run,
    )


if __name__ == "__main__":
    main()
