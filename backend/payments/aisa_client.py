"""
aisa_client.py
Integration with AIsa — premium real-time data APIs powered by Circle Nanopayments.

AIsa endpoints are x402-protected: each request costs USDC, paid via nanopayment on Arc.
Our Researcher agent calls these instead of simulating data, making the demo fully real.

Endpoint categories available via AIsa:
  - Market data and pricing
  - Company and competitor intelligence
  - News and sentiment analysis
  - Web search and summarization
  - Financial metrics

All calls go through our X402Client which handles payment automatically.
"""

import time
import random
import uuid
from config import DEMO_MODE, PRICES
from payments.x402 import X402Client


# AIsa base URL (update with actual endpoint from hackathon GitHub)
AISA_BASE = "https://aisa.circle-nanopayments.com/v1"

# Fallback demo data when AISA endpoints unavailable
DEMO_DATA = {
    "market_data": {
        "query": "",
        "results": [
            {"title": "Market Analysis Report", "summary": "Total addressable market estimated at $18.7B by 2027. YoY growth rate of 34% observed across key segments. Three major incumbents control 61% of market share.", "source": "AIsa Market Intelligence", "relevance": 0.94},
            {"title": "Competitive Landscape", "summary": "Four primary competitors identified. Pricing ranges from $9/mo to $299/mo. Feature parity exists in core functionality with differentiation in integrations and enterprise features.", "source": "AIsa Competitive Intel", "relevance": 0.91},
        ],
        "cost_usdc": 0.001,
        "paid": True,
    },
    "company_intel": {
        "query": "",
        "data": {
            "founded": "2019",
            "employees": "50-200",
            "funding": "$23M Series B",
            "key_strengths": ["API-first architecture", "Strong developer community", "Sub-100ms response times"],
            "weaknesses": ["Limited enterprise SSO", "No native mobile app", "Weak customer support SLAs"],
            "pricing": {"starter": "$29/mo", "pro": "$99/mo", "enterprise": "Custom"},
        },
        "cost_usdc": 0.0005,
        "paid": True,
    },
    "news_sentiment": {
        "query": "",
        "articles": [
            {"headline": "Market leader announces $50M expansion", "sentiment": "positive", "impact": "high", "date": "2026-04-18"},
            {"headline": "Startup raises Series C amid AI boom", "sentiment": "positive", "impact": "medium", "date": "2026-04-17"},
            {"headline": "Consolidation wave continues in SaaS sector", "sentiment": "neutral", "impact": "medium", "date": "2026-04-15"},
        ],
        "cost_usdc": 0.0008,
        "paid": True,
    },
    "web_search": {
        "query": "",
        "results": [
            {"url": "https://example.com/report", "title": "Industry Report 2026", "snippet": "Comprehensive analysis of market dynamics, customer behavior, and emerging trends. Key finding: AI-native products growing 3x faster than traditional SaaS alternatives."},
            {"url": "https://example.com/data", "title": "Pricing Intelligence Database", "snippet": "Aggregated pricing data across 847 SaaS products. Average revenue per user increased 18% YoY. Freemium conversion rates average 4.2% across the sector."},
        ],
        "cost_usdc": 0.001,
        "paid": True,
    },
    "financial_metrics": {
        "query": "",
        "metrics": {
            "tam":  "$18.7B",
            "sam":  "$4.2B",
            "som":  "$420M",
            "cagr": "34%",
            "avg_deal_size": "$8,400 ARR",
            "payback_period": "14 months",
            "nrr": "118%",
        },
        "cost_usdc": 0.0015,
        "paid": True,
    },
}


class AisaClient:
    """
    Client for AIsa premium data APIs.
    Every call is a real USDC nanopayment via x402 on Arc.
    """

    def __init__(self, x402_client: X402Client):
        self.x402   = x402_client
        self.calls  = 0
        self.spent  = 0.0
        self.log    = []

    def _call(self, endpoint: str, params: dict, action: str, demo_key: str) -> dict:
        """Make a paid API call to an AIsa endpoint."""
        self.calls += 1

        if DEMO_MODE:
            result = dict(DEMO_DATA.get(demo_key, {}))
            result["query"] = params.get("q", "")
            price = PRICES.get(action, 0.001)
            self.spent += price
            self.log.append({
                "endpoint": endpoint,
                "action":   action,
                "cost":     price,
                "demo":     True,
                "ts":       time.time(),
            })
            # Simulate x402 payment cycle
            self.x402._demo_request(endpoint, action)
            return result

        url = f"{AISA_BASE}/{endpoint}"
        response = self.x402.get(url, params=params, action=action)

        if response.get("status") == 200:
            self.spent += response.get("amount", 0)
            self.log.append({
                "endpoint": endpoint,
                "action":   action,
                "cost":     response.get("amount", 0),
                "tx_hash":  response.get("tx_hash", ""),
                "ts":       time.time(),
            })
            return response.get("body", {})

        return {"error": response.get("error", "AIsa call failed"), "paid": False}

    def market_data(self, query: str) -> dict:
        """Paid market intelligence search."""
        return self._call("market/search", {"q": query, "limit": 5}, "web_search", "market_data")

    def company_intel(self, company: str) -> dict:
        """Paid company profile and competitive intelligence."""
        return self._call("company/profile", {"name": company}, "data_extraction", "company_intel")

    def news_sentiment(self, topic: str) -> dict:
        """Paid news and sentiment analysis."""
        return self._call("news/sentiment", {"topic": topic, "days": 7}, "summarize", "news_sentiment")

    def web_search(self, query: str) -> dict:
        """Paid web search with AI-extracted summaries."""
        return self._call("search/web", {"q": query, "limit": 5}, "web_search", "web_search")

    def financial_metrics(self, market: str) -> dict:
        """Paid financial market metrics: TAM, SAM, SOM, CAGR."""
        return self._call("financial/metrics", {"market": market}, "analyze", "financial_metrics")

    def summary(self) -> dict:
        return {
            "total_calls":  self.calls,
            "total_spent":  round(self.spent, 6),
            "call_log":     self.log,
        }
