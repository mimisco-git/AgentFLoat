"""
specialists.py
Specialist agents using x402 payments, ERC-8004 identity, and AIsa real data.
"""

import random
import anthropic
from config import ANTHROPIC_API_KEY, DEMO_MODE
from payments.usyc_treasury import AgentTreasury
from payments.x402 import X402Client
from payments.aisa_client import AisaClient
from payments.erc8004 import registry

DEMO_RESPONSES = {
    "web_search": [
        "AIsa Search Result: Found 12 relevant sources. Key players include leading SaaS companies with significant market share. Recent funding rounds totaling $2.3B noted in the sector. x402 payment verified on Arc.",
        "AIsa Market Data: 34% YoY growth confirmed. TAM estimated at $18.7B by 2027. SAM at $4.2B. Customer acquisition costs average $340 in this segment.",
        "AIsa Competitive Intel: 4 major competitors identified. Pricing $9-$299/mo. Feature parity in core functionality. API-first players growing 3x faster.",
    ],
    "data_extraction": [
        "AIsa Structured Extract: 47 data points captured. Pricing tiers (5), core features (23), integrations (19). NPS scores range 34-72 across competitors.",
        "AIsa Profile Data: Customer reviews extracted from 3 platforms. Top complaints: onboarding complexity, pricing transparency. Top praise: reliability, API quality.",
    ],
    "fact_check": ["AIsa Fact Verification: 8 of 9 claims verified against primary sources. One statistic (42% market share) flagged as unconfirmed — recommend secondary citation only."],
    "analyze": [
        "Analysis: Competitive positioning shows pricing advantage at mid-market. Feature gap in enterprise SSO and audit logs. Opportunity in underserved SMB segment.",
        "Analysis: Market consolidating. Two acquisitions in 18 months. New entrants focusing on vertical niches — legal, fintech, healthcare. API-first architecture is key differentiator.",
        "TAM/SAM/SOM Analysis: TAM $18.7B, SAM $4.2B (API-first segment), SOM $420M (realistic 3-yr capture). CAGR 34%. NRR benchmark 118%.",
    ],
    "summarize": ["Summary: Three clear market segments identified. Research confirms product-market fit in SMB. Enterprise opportunity requires feature investment in SSO and compliance tooling."],
    "write_paragraph": [
        "Executive Summary: Comprehensive market research confirms a significant addressable opportunity. Current competitive dynamics favor API-first, developer-friendly solutions. AgentFloat's sub-cent payment infrastructure positions it uniquely to serve the agentic economy layer.",
        "Competitive Analysis: Four primary competitors operate at different price points. Differentiation centers on integration depth and developer experience. Key USP: our USYC yield model means the platform becomes cheaper at scale — no competitor offers this.",
        "Recommendations: Prioritize enterprise SSO to unlock $50K+ ACV segment. Build partner ecosystem for distribution acceleration. Consider vertical packaging for legal and fintech verticals.",
    ],
    "compile_report": ["Final Report compiled: 4 sections, 1,240 words, 12 data citations from AIsa paid endpoints. Executive summary, market analysis, competitive landscape, and strategic recommendations included. All data sourced via x402 nanopayments on Arc."],
    "fact_check": ["AIsa Verification: 8 of 9 claims verified. Market share figure (42%) flagged — recommend citing secondary source only."],
}


class SpecialistAgent:
    def __init__(self, agent_id: str, wallet: dict, treasury: AgentTreasury):
        self.agent_id = agent_id
        self.wallet   = wallet
        self.treasury = treasury
        self._client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if not DEMO_MODE else None
        self.x402     = X402Client(wallet["wallet_id"], wallet["address"], treasury)
        self.aisa     = AisaClient(self.x402)
        self.identity = registry.get(agent_id)

    def execute(self, action: str, detail: str, context: str = "") -> str:
        if DEMO_MODE:
            return self._demo_execute(action, detail, context)
        return self._live_execute(action, detail, context)

    def _demo_execute(self, action: str, detail: str, context: str) -> str:
        # Researcher uses AIsa endpoints for real data
        if self.agent_id == "researcher":
            if action == "web_search":
                result = self.aisa.web_search(detail)
                items = result.get("results", [])
                if items:
                    return f"AIsa Search [{detail[:40]}]: " + " | ".join(
                        i.get("snippet", i.get("title", ""))[:80] for i in items[:2]
                    )
            elif action == "data_extraction":
                result = self.aisa.market_data(context)
                items = result.get("results", [])
                if items:
                    return "AIsa Data: " + items[0].get("summary", "Data extracted successfully.")
            elif action == "fact_check":
                result = self.aisa.news_sentiment(context)
                arts = result.get("articles", [])
                if arts:
                    return f"AIsa Sentiment [{len(arts)} articles]: " + " | ".join(
                        f"{a['headline']} ({a['sentiment']})" for a in arts[:2]
                    )
        options = DEMO_RESPONSES.get(action, ["Task completed successfully."])
        return random.choice(options)

    def _live_execute(self, action: str, detail: str, context: str) -> str:
        system_map = {
            "researcher": "You are a research specialist. Use data, be precise, cite sources. Max 150 words.",
            "analyst":    "You are a data analyst. Extract insights, identify patterns. Max 150 words.",
            "writer":     "You are a professional writer. Clear, structured, impactful. Max 200 words.",
        }
        # Researcher calls real AIsa endpoints
        extra_context = ""
        if self.agent_id == "researcher":
            if action == "web_search":
                data = self.aisa.web_search(detail)
                extra_context = f"\nAIsa search results: {data}"
            elif action == "data_extraction":
                data = self.aisa.market_data(context)
                extra_context = f"\nAIsa market data: {data}"

        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=300,
            system=system_map.get(self.agent_id, "You are a helpful AI assistant. Be concise."),
            messages=[{"role": "user", "content": f"Context: {context}\nAction: {action}\nInstruction: {detail}{extra_context}\n\nExecute this micro-task now."}]
        )
        return msg.content[0].text


def build_specialist(agent_id: str, wallet: dict) -> SpecialistAgent:
    treasury = AgentTreasury(wallet_id=wallet["wallet_id"], initial_usyc=5.0)
    return SpecialistAgent(agent_id=agent_id, wallet=wallet, treasury=treasury)
