"""
Extra market endpoints:
  GET /api/market/trending   — top 20 trending stocks (cached 30 min)
  GET /api/market/portfolio  — live quotes for all user portfolio tickers
"""

from typing import Annotated
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user, User

router = APIRouter(prefix="/api/market", tags=["market"])

# 20 well-known tickers spanning US, Indian, and crypto markets
TRENDING_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META",
    "TSLA", "AMZN", "BTC-USD", "ETH-USD",
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "NIFTYBEES.NS", "BAJFINANCE.NS", "WIPRO.NS", "SBIN.NS",
    "TATAMOTORS.NS", "ADANIENT.NS",
]


@router.get("/trending")
async def get_trending():
    """
    Returns live price + change% for the 20 trending tickers.
    Uses MongoDB cache (5-min TTL per ticker) so repeated calls are fast.
    """
    import asyncio
    from app.tools.market import get_market_analysis

    async def fetch_one(ticker: str) -> dict:
        try:
            data = await get_market_analysis(ticker)
            if "error" in data:
                return None
            return {
                "ticker":               data["ticker"],
                "company_name":         data.get("company_name", ticker),
                "price":                data.get("price", 0),
                "change_percent_today": data.get("change_percent_today", 0),
                "currency":             data.get("currency", "USD"),
                "exchange":             data.get("exchange", ""),
                "rsi_14":               data.get("rsi_14"),
                "trend":                data.get("trend", ""),
                "sector":               data.get("sector", ""),
            }
        except Exception:
            return None

    results = await asyncio.gather(*[fetch_one(t) for t in TRENDING_TICKERS])
    return [r for r in results if r is not None]


@router.get("/portfolio-quotes")
async def get_portfolio_quotes(current_user: Annotated[User, Depends(get_current_user)]):
    """
    Returns live quotes for all tickers in the authenticated user's portfolio.
    """
    import asyncio
    from app.db.mongo import get_portfolio
    from app.tools.market import get_market_analysis

    portfolio = await get_portfolio(current_user.id)
    holdings  = portfolio.get("holdings", [])
    if not holdings:
        return []

    async def fetch_one(holding: dict) -> dict:
        ticker = holding.get("yahoo_symbol") or holding.get("ticker")
        try:
            data = await get_market_analysis(ticker)
            if "error" in data:
                return {
                    "ticker":       holding["ticker"],
                    "company_name": holding.get("company_name", holding["ticker"]),
                    "shares":       holding["shares"],
                    "avg_buy_price":holding["avg_buy_price"],
                    "error":        True,
                }
            cost_basis   = holding["shares"] * holding["avg_buy_price"]
            market_value = holding["shares"] * data["price"]
            gain_loss    = market_value - cost_basis
            gain_pct     = round((gain_loss / cost_basis) * 100, 2) if cost_basis else 0
            return {
                "ticker":               holding["ticker"],
                "company_name":         data.get("company_name", holding.get("company_name", ticker)),
                "shares":               holding["shares"],
                "avg_buy_price":        holding["avg_buy_price"],
                "price":                data["price"],
                "change_percent_today": data.get("change_percent_today", 0),
                "currency":             data.get("currency", "USD"),
                "cost_basis":           round(cost_basis, 2),
                "market_value":         round(market_value, 2),
                "gain_loss":            round(gain_loss, 2),
                "gain_pct":             gain_pct,
                "rsi_14":               data.get("rsi_14"),
                "trend":                data.get("trend", ""),
            }
        except Exception:
            return None

    results = await asyncio.gather(*[fetch_one(h) for h in holdings])
    return [r for r in results if r is not None]