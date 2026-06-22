"""SEC Form 4 insider transaction collector for TTWO."""
import time
import pandas as pd
from lxml import etree
import config
from ._retry import get_with_retry

_HEADERS = {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_INTER_FILING_PAUSE = 0.15  # seconds between filing XML requests (~6 req/sec, well within 10/s limit)


def _get_cik(ticker: str) -> str:
    r = get_with_retry(_TICKERS_URL, headers=_HEADERS, timeout=30, base_delay=20, label="sec/tickers")
    tickers = r.json()
    for entry in tickers.values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"CIK not found for {ticker}")


def _get_form4_filings(cik: str) -> list[dict]:
    url = _SUBMISSIONS_URL.format(cik=cik)
    r = get_with_retry(url, headers=_HEADERS, timeout=30, base_delay=20, label="sec/submissions")
    data = r.json()
    filings = data.get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    docs = filings.get("primaryDocument", [])

    results = []
    for form, date_, acc, doc in zip(forms, dates, accessions, docs):
        if form == "4":
            results.append({"date": date_, "accession": acc, "doc": doc})
    return results


def _parse_form4_xml(xml_bytes: bytes, filing_date: str) -> list[dict]:
    rows = []
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return rows

    def find(el, tag):
        result = el.find(tag)
        if result is None:
            result = el.find(f".//{tag}")
        return result

    def text(el, tag):
        node = find(el, tag)
        return node.text.strip() if node is not None and node.text else ""

    for tx in root.iter("nonDerivativeTransaction"):
        code = text(tx, "transactionCode")
        shares_str = text(tx, "transactionShares")
        price_str = text(tx, "transactionPricePerShare")
        plan_flag = text(tx, "deemedExecutionDate") or text(tx, "aff10b5One")

        try:
            shares = float(shares_str)
            price = float(price_str)
        except (ValueError, TypeError):
            continue

        rows.append({
            "filing_date": filing_date,
            "transaction_code": code,
            "usd": round(shares * price, 2),
            "is_sale": code == "S",
            "is_plan": bool(plan_flag),
        })

    return rows


def collect(existing: pd.DataFrame) -> list[dict]:
    cik = _get_cik(config.TICKER)

    sec_rows = (
        existing[existing["source"] == "sec"]
        if not existing.empty
        else pd.DataFrame()
    )
    known_dates = set(sec_rows["obs_date"].tolist()) if not sec_rows.empty else set()

    filings = _get_form4_filings(cik)
    output: list[dict] = []

    for filing in filings:
        filing_date = filing["date"]
        if filing_date in known_dates:
            continue

        acc_clean = filing["accession"].replace("-", "")
        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
            f"/{acc_clean}/{filing['doc']}"
        )
        try:
            time.sleep(_INTER_FILING_PAUSE)
            r = get_with_retry(xml_url, headers=_HEADERS, timeout=30, base_delay=20, label="sec/filing")
            transactions = _parse_form4_xml(r.content, filing_date)
        except Exception:
            continue

        if not transactions:
            continue

        sales = [t for t in transactions if t["is_sale"]]
        total_usd = round(sum(t["usd"] for t in sales), 2)
        discr_usd = round(sum(t["usd"] for t in sales if not t["is_plan"]), 2)

        note = filing["accession"]
        output += [
            {"obs_date": filing_date, "source": "sec", "metric": "insider_sale_usd", "value": total_usd, "unit": "usd", "note": note},
            {"obs_date": filing_date, "source": "sec", "metric": "insider_filing_count", "value": len(transactions), "unit": "count", "note": note},
            {"obs_date": filing_date, "source": "sec", "metric": "insider_discretionary_usd", "value": discr_usd, "unit": "usd", "note": note},
        ]

    return output
