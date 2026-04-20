"""
orchestrator.py
Master agent with x402 payment middleware, ERC-8004 identity, and AIsa data integration.
"""

import time
import anthropic
from config import ANTHROPIC_API_KEY, DEMO_MODE, PRICES
from payments.circle_client import fire_nanopayment, redeem_usyc_to_usdc
from payments.usyc_treasury import AgentTreasury
from payments.x402 import X402Client
from payments.erc8004 import registry
from payments.aisa_client import AisaClient


DEMO_PLAN_TEMPLATE = [
    {"agent": "researcher", "action": "web_search",      "detail": "Search for key information on the topic"},
    {"agent": "researcher", "action": "web_search",      "detail": "Search for market data and statistics"},
    {"agent": "researcher", "action": "web_search",      "detail": "Search for competitor information"},
    {"agent": "researcher", "action": "data_extraction", "detail": "Extract structured data from sources"},
    {"agent": "researcher", "action": "data_extraction", "detail": "Extract pricing and feature comparisons"},
    {"agent": "researcher", "action": "fact_check",      "detail": "Verify key claims and data points"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze market positioning"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze competitive landscape"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze TAM, SAM, SOM metrics"},
    {"agent": "analyst",    "action": "summarize",       "detail": "Summarize research findings"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write executive summary"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write competitive analysis section"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write recommendations section"},
    {"agent": "writer",     "action": "compile_report",  "detail": "Compile and format final report"},
]


class Orchestrator:
    def __init__(self, wallet: dict, treasury: AgentTreasury, emit_fn=None):
        self.wallet   = wallet
        self.treasury = treasury
        self.emit     = emit_fn or (lambda e, d: None)
        self._client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if not DEMO_MODE else None
        self.tx_log   = []
        self.x402     = X402Client(wallet["wallet_id"], wallet["address"], treasury)
        self.identity = registry.get("orchestrator")

    def plan_task(self, task: str) -> list[dict]:
        if DEMO_MODE:
            plan = [dict(s) for s in DEMO_PLAN_TEMPLATE]
            plan[0]["detail"] = f"Search for: {task}"
            return plan
        import json, re
        prompt = f"""You are an AI orchestrator managing specialist agents.
Break this task into discrete micro-actions. Each must specify: agent (researcher/analyst/writer), action type, detail.

Available actions: {list(PRICES.keys())}
Task: {task}

Respond ONLY with a JSON array. Max 16 items."""
        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        return json.loads(match.group()) if match else DEMO_PLAN_TEMPLATE

    def pay_agent(self, agent_id: str, agent_address: str, action: str, detail: str) -> dict:
        amount = PRICES.get(action, 0.001)

        # Validate agent ERC-8004 identity before paying
        valid, reason = registry.validate(agent_id, min_trust=0)
        if not valid:
            self.emit("warning", {"message": f"Agent {agent_id} failed ERC-8004 validation: {reason}"})

        # Redeem USYC -> USDC
        redeem_usyc_to_usdc(self.wallet["wallet_id"], amount)
        self.treasury.redeem_for_payment(amount)

        # Fire nanopayment on Arc
        tx = fire_nanopayment(
            from_wallet_id=self.wallet["wallet_id"],
            to_address=agent_address,
            amount_usdc=amount,
            memo=f"{agent_id}:{action}:{detail[:40]}",
        )
        self.treasury.debit_usdc(amount)
        registry.record_payment("orchestrator", amount)

        receipt = {**tx, "agent": agent_id, "action": action, "detail": detail, "amount": amount}
        self.tx_log.append(receipt)

        self.emit("transaction", {
            "tx_hash":  tx["tx_hash"],
            "agent":    agent_id,
            "action":   action,
            "amount":   amount,
            "total_tx": len(self.tx_log),
            "chain":    "Arc",
            "x402":     False,
            "erc8004_verified": valid,
        })
        return receipt

    def run(self, task: str, specialists: dict) -> dict:
        self.emit("status", {"message": "Planning task...", "phase": "planning"})
        plan = self.plan_task(task)

        self.emit("status", {
            "message": f"Plan ready: {len(plan)} micro-actions across {len(set(p['agent'] for p in plan))} agents",
            "phase":   "dispatching",
            "plan":    plan,
        })

        results = []
        for step in plan:
            agent_id   = step["agent"]
            action     = step["action"]
            detail     = step["detail"]
            specialist = specialists.get(agent_id)
            if not specialist:
                continue

            receipt = self.pay_agent(agent_id, specialist.wallet["address"], action, detail)
            self.emit("agent_active", {"agent": agent_id, "action": action})
            result = specialist.execute(action, detail, task)
            results.append({"agent": agent_id, "action": action, "result": result})
            registry.record_success(agent_id, earned=receipt["amount"])

            self.emit("agent_done", {
                "agent":  agent_id,
                "action": action,
                "result": result[:120] if result else "",
            })
            time.sleep(0.3)

        self.emit("status", {"message": "Compiling final report...", "phase": "compiling"})
        final = self._compile(task, results)

        return {
            "report":       final,
            "transactions": self.tx_log,
            "tx_count":     len(self.tx_log),
            "total_cost":   round(sum(t["amount"] for t in self.tx_log), 6),
            "treasury":     self.treasury.snapshot(),
            "erc8004":      registry.all_agents(),
            "x402_calls":   self.x402.tx_log,
        }

    def _compile(self, task: str, results: list) -> str:
        if DEMO_MODE:
            return "\n\n".join(r["result"] for r in results if r.get("result"))[:2000] or "Demo report compiled."
        content = "\n".join(f"[{r['agent'].upper()}/{r['action']}]: {r['result']}" for r in results if r.get("result"))
        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1500,
            messages=[{"role": "user", "content": f"Compile these agent outputs into a clean report for: '{task}'\n\n{content}"}]
        )
        return msg.content[0].text
