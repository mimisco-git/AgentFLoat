"""
specialists.py
Three specialist agents that execute micro-tasks.
Each runs as an independent service with its own Circle wallet and USYC treasury.
"""

import random
import anthropic
from config import ANTHROPIC_API_KEY, DEMO_MODE
from payments.usyc_treasury import AgentTreasury


# Demo responses for each action type
DEMO_RESPONSES = {
    "web_search": [
        "Found 12 relevant sources. Key players include leading SaaS companies with significant market share. Recent funding rounds totaling $2.3B noted in the sector.",
        "Market data shows 34% YoY growth. TAM estimated at $18.7B by 2027. Customer acquisition costs average $340 in this segment.",
        "Competitor analysis: 4 major players identified. Pricing ranges from $9/mo to $299/mo. Feature parity exists in core functionality.",
    ],
    "data_extraction": [
        "Extracted 47 data points. Structured into: pricing tiers (5), core features (23), integrations (19). CSV format ready.",
        "Customer review data extracted: NPS scores range 34-72. Top complaints: onboarding complexity, pricing transparency. Top praise: reliability, support.",
    ],
    "fact_check": [
        "Verified 8 of 9 claims. One statistic (market share 42%) could not be confirmed via primary sources. Recommend citing secondary only.",
    ],
    "analyze": [
        "Competitive positioning: Your solution has pricing advantage at mid-market segment. Feature gap exists in enterprise SSO and audit logs.",
        "Strengths: ease of onboarding, API-first design. Weaknesses: limited enterprise features, no native mobile app. Opportunity: SMB segment underserved.",
        "Landscape analysis: Market consolidating. Two acquisitions in last 18 months. New entrants focusing on vertical niches.",
    ],
    "summarize": [
        "Summary: Three clear market segments identified. Research confirms product-market fit hypothesis in SMB. Enterprise opportunity requires feature investment.",
    ],
    "write_paragraph": [
        "Executive Summary: Based on comprehensive market research and competitive analysis, the addressable market presents significant opportunity. Current competitive dynamics favor nimble, API-first solutions with strong developer experience.",
        "Competitive Analysis: The market features four primary competitors at different price points. Differentiation centers on integration depth, onboarding experience, and pricing transparency. Our solution's API-first architecture provides a sustainable technical advantage.",
        "Recommendations: Prioritize enterprise SSO integration to unlock the $50K+ ACV segment. Develop a partner ecosystem strategy to accelerate distribution. Consider vertical-specific packaging for legal and fintech customers.",
    ],
    "compile_report": [
        "Report compiled: 4 sections, 1,240 words, 12 data citations. Executive summary, market analysis, competitive landscape, and strategic recommendations included.",
    ],
}


class SpecialistAgent:
    def __init__(self, agent_id: str, wallet: dict, treasury: AgentTreasury):
        self.agent_id = agent_id
        self.wallet   = wallet
        self.treasury = treasury
        self._client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if not DEMO_MODE else None

    def execute(self, action: str, detail: str, context: str = "") -> str:
        """Execute a micro-task and return result string."""
        if DEMO_MODE:
            return self._demo_execute(action)
        return self._live_execute(action, detail, context)

    def _demo_execute(self, action: str) -> str:
        options = DEMO_RESPONSES.get(action, ["Task completed successfully."])
        return random.choice(options)

    def _live_execute(self, action: str, detail: str, context: str) -> str:
        system_prompts = {
            "researcher": "You are a research specialist. Be precise, cite data, keep responses under 150 words.",
            "analyst":    "You are a data analyst. Extract insights, identify patterns. Keep responses under 150 words.",
            "writer":     "You are a professional writer. Write clear, structured content. Keep responses under 200 words.",
        }
        system = system_prompts.get(self.agent_id, "You are a helpful AI assistant. Be concise.")

        prompt = f"""Task context: {context}
Action: {action}
Instruction: {detail}

Execute this micro-task now. Be specific and actionable."""

        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text


def build_specialist(agent_id: str, wallet: dict) -> SpecialistAgent:
    """Factory function to build a specialist with its own treasury."""
    treasury = AgentTreasury(wallet_id=wallet["wallet_id"], initial_usyc=5.0)
    return SpecialistAgent(agent_id=agent_id, wallet=wallet, treasury=treasury)
