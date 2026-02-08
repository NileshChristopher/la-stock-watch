"""
LA Stock Watch: Top 25 — Build Script
Publication-grade data for SoCal's largest public companies by market cap.

Generates:
  - docs-top25/index.html (styled website)
  - docs-top25/top25.json (data handoff file)
  - docs-top25/verification.txt (validation log)
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

# Validation thresholds
MIN_MARKET_CAP = 1_000_000_000      # $1B
MAX_MARKET_CAP = 500_000_000_000    # $500B
MAX_WEEKLY_CHANGE = 60              # ±60%

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def load_companies():
    """Load the curated Top 25 list."""
    with open(DATA_DIR / "top25_companies.json") as f:
        return json.load(f)


def fetch_quotes(tickers):
    """
    Fetch quotes for all tickers using yfinance.
    Returns list of quote dicts with price, market cap, P/E, and weekly change.
    """
    print(f"  Fetching data for {len(tickers)} tickers...")

    # Fetch 7 calendar days for true weekly comparison
    tickers_str = " ".join(tickers)
    data = yf.download(
        tickers_str,
        period="7d",
        group_by="ticker",
        progress=False,
        threads=True,
    )

    all_quotes = []
    failed = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get current and week-ago prices from history
            if len(tickers) == 1:
                current_price = float(data["Close"].iloc[-1])
                week_ago_price = float(data["Close"].iloc[0])
            else:
                if ticker in data.columns.get_level_values(0):
                    ticker_data = data[ticker]["Close"].dropna()
                    if len(ticker_data) >= 2:
                        current_price = float(ticker_data.iloc[-1])
                        week_ago_price = float(ticker_data.iloc[0])
                    else:
                        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                        week_ago_price = None
                else:
                    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                    week_ago_price = None

            if current_price and current_price > 0:
                all_quotes.append({
                    "symbol": ticker,
                    "price": current_price,
                    "week_ago_price": week_ago_price,
                    "yearHigh": info.get("fiftyTwoWeekHigh", 0),
                    "yearLow": info.get("fiftyTwoWeekLow", 0),
                    "marketCap": info.get("marketCap", 0),
                    "pe": info.get("trailingPE"),
                    "volume": info.get("volume", 0),
                })
        except Exception as e:
            failed.append(ticker)

    if failed:
        print(f"  WARNING: Failed to fetch: {', '.join(failed)}")

    return all_quotes, failed


def fetch_historical(ticker, days=7):
    """Fetch recent daily closing prices for sparkline charts."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="7d")
        if not hist.empty:
            prices = hist["Close"].tolist()
            return [round(p, 2) for p in prices]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------


def build_enriched_data(companies, quotes):
    """
    Merge company info with quote data.
    Returns list sorted by market cap (descending).
    """
    company_map = {c["ticker"]: c for c in companies}
    quote_map = {q["symbol"]: q for q in quotes}

    enriched = []
    for company in companies:
        ticker = company["ticker"]
        if ticker not in quote_map:
            continue

        q = quote_map[ticker]
        current_price = q.get("price", 0) or 0
        week_ago_price = q.get("week_ago_price")

        # Calculate 7-day change
        if week_ago_price and week_ago_price > 0:
            week_change = ((current_price - week_ago_price) / week_ago_price) * 100
        else:
            week_change = 0

        enriched.append({
            "rank": 0,
            "name": company["name"],
            "ticker": ticker,
            "city": company["city"],
            "county": company["county"],
            "price": current_price,
            "change_pct": round(week_change, 2),
            "year_high": q.get("yearHigh", 0),
            "year_low": q.get("yearLow", 0),
            "market_cap": q.get("marketCap", 0),
            "pe": q.get("pe"),
            "yahoo_url": f"https://finance.yahoo.com/quote/{ticker}/",
        })

    # Sort by market cap (descending)
    enriched.sort(key=lambda x: x["market_cap"] or 0, reverse=True)

    # Assign ranks
    for i, stock in enumerate(enriched, 1):
        stock["rank"] = i

    return enriched


def find_spotlight_stocks(enriched):
    """Find the top gainer and top loser by 7-day change."""
    sorted_by_change = sorted(enriched, key=lambda x: x["change_pct"], reverse=True)
    gainer = sorted_by_change[0] if sorted_by_change else None
    loser = sorted_by_change[-1] if sorted_by_change else None
    return gainer, loser


def compute_pe_extremes(enriched):
    """Find highest and lowest P/E ratios."""
    with_pe = [s for s in enriched if s["pe"] and s["pe"] > 0]
    with_pe.sort(key=lambda x: x["pe"], reverse=True)
    highest = with_pe[0] if with_pe else None
    lowest = with_pe[-1] if with_pe else None
    return highest, lowest


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_data(enriched, failed_tickers):
    """
    Run validation checks. Returns (passed, log_lines).
    """
    log = []
    passed = True

    # Check 1: All 25 tickers fetched
    fetched = len(enriched)
    if fetched == 25:
        log.append(f"Tickers fetched: {fetched}/25 OK")
    else:
        log.append(f"Tickers fetched: {fetched}/25 FAILED")
        if failed_tickers:
            log.append(f"  Missing: {', '.join(failed_tickers)}")
        passed = False

    # Check 2: All prices positive
    prices = [s["price"] for s in enriched]
    if all(p > 0 for p in prices):
        log.append(f"Price range: ${min(prices):.2f} - ${max(prices):.2f} OK")
    else:
        log.append("Price range: Some prices are zero or negative FAILED")
        passed = False

    # Check 3: Market caps in expected range
    caps = [s["market_cap"] for s in enriched if s["market_cap"]]
    if caps:
        min_cap = min(caps)
        max_cap = max(caps)
        cap_ok = min_cap >= MIN_MARKET_CAP and max_cap <= MAX_MARKET_CAP
        if cap_ok:
            log.append(f"Market cap range: ${min_cap/1e9:.1f}B - ${max_cap/1e9:.1f}B OK")
        else:
            log.append(f"Market cap range: ${min_cap/1e9:.1f}B - ${max_cap/1e9:.1f}B WARNING (outside expected)")

    # Check 4: Flag extreme movers
    extreme_movers = [s for s in enriched if abs(s["change_pct"]) > MAX_WEEKLY_CHANGE]
    if extreme_movers:
        for s in extreme_movers:
            log.append(f"Extreme mover: {s['ticker']} ({s['change_pct']:+.1f}%) - flagged for review")
    else:
        log.append("No extreme movers (within +/-60%)")

    return passed, log


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


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


def format_pe(value):
    """Format P/E ratio."""
    if not value:
        return "N/A"
    return f"{value:.1f}x"


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def render_site(enriched, gainer, loser, pe_high, pe_low,
                gainer_sparkline, loser_sparkline, build_date, validation_log):
    """Render the single-page site."""

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    env.filters["initials"] = get_initials
    env.filters["market_cap"] = format_market_cap
    env.filters["price"] = format_price
    env.filters["pe"] = format_pe

    template = env.get_template("top25.html")
    html = template.render(
        companies=enriched,
        spotlight_gainer=gainer,
        spotlight_loser=loser,
        pe_highest=pe_high,
        pe_lowest=pe_low,
        gainer_sparkline=json.dumps(gainer_sparkline),
        loser_sparkline=json.dumps(loser_sparkline),
        build_date=build_date,
        year=build_date.year,
    )

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write HTML
    (OUTPUT_DIR / "index.html").write_text(html)

    # Write JSON data file for handoff
    json_data = {
        "build_date": build_date.isoformat(),
        "companies": enriched,
    }
    (OUTPUT_DIR / "top25.json").write_text(json.dumps(json_data, indent=2))

    # Write verification log
    log_content = [
        f"Build: {build_date.strftime('%Y-%m-%d %H:%M')} UTC",
        "-" * 40,
    ] + validation_log
    (OUTPUT_DIR / "verification.txt").write_text("\n".join(log_content))

    # Copy static assets
    static_out = OUTPUT_DIR / "static"
    if static_out.exists():
        shutil.rmtree(static_out)
    shutil.copytree(STATIC_DIR, static_out)

    print(f"\nSite built -> {OUTPUT_DIR}")
    print(f"  index.html        ({len(html):,} bytes)")
    print(f"  top25.json        (data handoff)")
    print(f"  verification.txt  (validation log)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 50)
    print("LA Stock Watch: Top 25 — Building site")
    print("=" * 50)

    companies = load_companies()
    tickers = [c["ticker"] for c in companies]

    print(f"\nFetching market data for {len(tickers)} companies...")
    quotes, failed_tickers = fetch_quotes(tickers)
    print(f"  Got quotes for {len(quotes)} companies")

    if len(quotes) < 20:
        print("\nERROR: Too few quotes fetched. Build aborted.")
        return

    enriched = build_enriched_data(companies, quotes)
    gainer, loser = find_spotlight_stocks(enriched)
    pe_high, pe_low = compute_pe_extremes(enriched)

    # Validation
    print("\nValidating data...")
    passed, validation_log = validate_data(enriched, failed_tickers)
    for line in validation_log:
        print(f"  {line}")

    if not passed:
        print("\nERROR: Validation failed. Build aborted.")
        return

    # Fetch sparklines for spotlight stocks
    gainer_sparkline = []
    loser_sparkline = []
    if gainer:
        print(f"\n  Fetching sparkline for {gainer['ticker']}...")
        gainer_sparkline = fetch_historical(gainer["ticker"])
    if loser:
        print(f"  Fetching sparkline for {loser['ticker']}...")
        loser_sparkline = fetch_historical(loser["ticker"])

    build_date = datetime.now(timezone.utc)

    # Summary
    print(f"\n  Top gainer: {gainer['name']} ({gainer['ticker']}) +{gainer['change_pct']}%")
    print(f"  Top loser:  {loser['name']} ({loser['ticker']}) {loser['change_pct']}%")
    print(f"  P/E high:   {pe_high['name']} ({pe_high['pe']:.1f}x)" if pe_high else "  P/E high: N/A")
    print(f"  P/E low:    {pe_low['name']} ({pe_low['pe']:.1f}x)" if pe_low else "  P/E low: N/A")

    render_site(
        enriched, gainer, loser, pe_high, pe_low,
        gainer_sparkline, loser_sparkline,
        build_date, validation_log
    )


if __name__ == "__main__":
    main()
