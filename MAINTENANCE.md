# LA Stock Watch — Maintenance Guide

This document covers routine maintenance tasks to keep LA Stock Watch accurate and up-to-date.

---

## 1. Weekly (Automatic)

The site rebuilds automatically every Monday at 6:00 AM Pacific via GitHub Actions. **No action needed.**

To verify builds are running:
1. Go to your GitHub repo → **Actions** tab
2. Check the "Build LA Stock Watch" workflow
3. Green checkmark = success, red X = failure

---

## 2. Quarterly (Manual)

GitHub will create an issue on Jan 1, Apr 1, Jul 1, and Oct 1 reminding you to check for new IPOs.

### Check for New SoCal IPOs

Search these sources for recent IPOs headquartered in Southern California:

- [LA Business Journal](https://labusinessjournal.com/) — Covers LA metro area
- [San Diego Business Journal](https://www.sdbj.com/) — Covers San Diego companies
- [Orange County Business Journal](https://www.ocbj.com/) — Covers OC companies
- [SEC EDGAR S-1 Filings](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1) — Search for CA addresses

### Review Build Logs

1. Go to **Actions** → Recent "Build LA Stock Watch" runs
2. Click into a run and expand "Build site"
3. Look for any warnings about failed tickers or missing anchor companies

### Clean Up Delisted Companies

Companies may be removed if they:
- Were acquired (e.g., merged into another company)
- Were delisted from exchanges
- Moved headquarters outside SoCal

See "How to Remove a Company" below.

---

## 3. How to Add a Company

### Step 1: Get the ticker symbol
Find the company's NYSE/NASDAQ ticker (e.g., "NVDA" for NVIDIA).

### Step 2: Edit socal_companies.json
Open `data/socal_companies.json` and add a new entry:

```json
{"ticker": "XXXX", "name": "Company Name", "city": "City Name"}
```

**Important:**
- Maintain alphabetical order by ticker, or add to the end
- City should be the SoCal city where HQ is located
- Use the official company name

### Step 3: Test locally

```bash
python build.py
```

Check that:
- No errors appear for the new ticker
- The company shows up in `docs/rankings.html`

### Step 4: Commit and push

```bash
git add data/socal_companies.json
git commit -m "Add [Company Name] to stock tracker"
git push
```

The site will rebuild on the next scheduled run (or trigger manually via Actions → Run workflow).

---

## 4. How to Remove a Company

### When to remove:
- Company was acquired or merged
- Company was delisted from stock exchanges
- Company moved headquarters out of SoCal
- Ticker symbol changed (remove old, add new)

### Step 1: Edit socal_companies.json
Open `data/socal_companies.json` and delete the line for that company.

### Step 2: Test locally

```bash
python build.py
```

Verify the build completes without errors.

### Step 3: Commit and push

```bash
git add data/socal_companies.json
git commit -m "Remove [Company Name] — [reason: acquired/delisted/moved]"
git push
```

---

## 5. Troubleshooting

### "Build failed" in GitHub Actions

1. Go to Actions → Failed run → Click "Build site" step
2. Read the error message
3. Common causes:
   - **yfinance rate limited**: Wait and retry, or run manually later
   - **Network timeout**: Transient; re-run the workflow
   - **Python error**: Check the traceback for file/line info

To re-run: Actions → Select failed run → "Re-run all jobs"

### "Company showing $0 price"

This usually means:
- The ticker symbol is wrong
- The stock was delisted
- yfinance temporarily failed for that ticker

**Fix:** Verify the ticker on [Yahoo Finance](https://finance.yahoo.com). If valid, it may resolve on next build. If the company was delisted, remove it.

### "yfinance broke" (API changes)

Yahoo Finance occasionally changes their API, breaking yfinance. Signs:
- All or most stocks fail to fetch
- Import errors mentioning yfinance

**Fix:**
1. Check [yfinance GitHub issues](https://github.com/ranaroussi/yfinance/issues) for known problems
2. Update yfinance: `pip install --upgrade yfinance`
3. If widespread, wait for a yfinance patch release

### "Missing anchor company" warning

If you see warnings like:
```
⚠️ WARNING: Missing anchor company: DIS (Walt Disney Co)
```

This means a major SoCal company failed to fetch. The site still builds, but investigate:
1. Is yfinance having issues? (check other tickers)
2. Did the ticker change? (check Yahoo Finance)
3. Was the company acquired?

---

## Quick Reference

| Task | Frequency | Action |
|------|-----------|--------|
| Site rebuild | Weekly (auto) | None needed |
| Check for IPOs | Quarterly | Review business journals |
| Review build logs | Quarterly | Check Actions tab |
| Update yfinance | As needed | `pip install --upgrade yfinance` |

---

*Last updated: February 2026*
