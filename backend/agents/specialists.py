"""
specialists.py — uses unified AI client (Groq or Anthropic)
"""

import random
from config import DEMO_MODE
from payments.usyc_treasury import AgentTreasury
from payments.x402 import X402Client
from payments.aisa_client import AisaClient
from payments.erc8004 import registry
from agents.ai_client import get_client, chat

DEMO_RESPONSES = {
    "web_search":      ["AIsa Search: 12 sources found. Market leaders control 61% share. $2.3B in recent funding.","AIsa Market: 34% YoY growth. TAM $18.7B. SAM $4.2B. CAC avg $340.","AIsa Intel: 4 competitors. Pricing $9-$299/mo. API-first growing 3x faster."],
    "data_extraction": ["AIsa Extract: 47 data points. Pricing (5 tiers), features (23), integrations (19).","AIsa Profile: NPS 34-72. Top complaint: onboarding. Top praise: reliability."],
    "fact_check":      ["AIsa Verify: 8/9 claims confirmed. Market share stat (42%) flagged as unverified."],
    "analyze":         ["Analysis: Pricing advantage at mid-market. Feature gap in enterprise SSO.","Analysis: Market consolidating. 2 acquisitions in 18 months. Verticals underserved.","TAM/SAM/SOM: $18.7B / $4.2B / $420M. CAGR 34%. NRR 118%."],
    "summarize":       ["Summary: 3 segments identified. PMF confirmed in SMB. Enterprise needs SSO + compliance."],
    "write_paragraph": ["Executive Summary: Significant addressable opportunity confirmed. API-first solutions growing 3x. Sub-cent payments position AgentFloat uniquely for the agentic economy.","Competitive Analysis: 4 competitors at different price points. Key USP: USYC yield model means costs decrease at scale.","Recommendations: Prioritize enterprise SSO. Build partner ecosystem. Consider vertical packaging for legal and fintech."],
    "compile_report":  ["Report compiled: 4 sections, 1,240 words, 12 AIsa citations. Executive summary, market analysis, competitive landscape, recommendations."],
}

SYSTEM_PROMPTS = {
    "researcher": "You are a research specialist. Be precise, cite data, keep responses under 150 words.",
    "analyst":    "You are a data analyst. Extract insights and patterns. Keep responses under 150 words.",
    "writer":     "You are a professional writer. Write clear structured content. Keep responses under 200 words.",
}


class SpecialistAgent:
    def __init__(self, agent_id: str, wallet: dict, treasury: AgentTreasury):
        self.agent_id = agent_id
        self.wallet   = wallet
        self.treasury = treasury
        self._client  = get_client()
        self.x402     = X402Client(wallet["wallet_id"], wallet["address"], treasury)
        self.aisa     = AisaClient(self.x402)

    def execute(self, action: str, detail: str, context: str = "") -> str:
        if DEMO_MODE or self._client is None:
            return self._demo(action, detail, context)
        return self._live(action, detail, context)

    def _demo(self, action, detail, context):
        if self.agent_id == "researcher":
            if action == "web_search":
                r = self.aisa.web_search(detail)
                items = r.get("results", [])
                if items:
                    return "AIsa: " + " | ".join(i.get("snippet","")[:80] for i in items[:2])
            elif action == "data_extraction":
                r = self.aisa.market_data(context)
                items = r.get("results", [])
                if items:
                    return "AIsa Data: " + items[0].get("summary","Data extracted.")
        return random.choice(DEMO_RESPONSES.get(action, ["Task completed."]))

    def _live(self, action, detail, context):
        extra = ""
        if self.agent_id == "researcher":
            if action == "web_search":
                data  = self.aisa.web_search(detail)
                extra = f"\nAIsa data: {data.get('results', '')}"
            elif action == "data_extraction":
                data  = self.aisa.market_data(context)
                extra = f"\nAIsa market data: {data}"
        system = SYSTEM_PROMPTS.get(self.agent_id, "You are a helpful AI assistant. Be concise.")
        prompt = f"Context: {context}\nAction: {action}\nInstruction: {detail}{extra}\n\nExecute now."
        return chat(self._client, system, prompt, max_tokens=300)


def build_specialist(agent_id: str, wallet: dict) -> SpecialistAgent:
    treasury = AgentTreasury(wallet_id=wallet["wallet_id"], initial_usyc=5.0)
    return SpecialistAgent(agent_id=agent_id, wallet=wallet, treasury=treasury)
