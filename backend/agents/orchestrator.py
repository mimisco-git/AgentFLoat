"""
orchestrator.py
Master agent that receives a user task, breaks it into subtasks via Claude,
dispatches to specialist agents, collects results, and compiles final output.
Each dispatch triggers a real nanopayment on Arc.
"""

import time
import asyncio
import anthropic
from config import ANTHROPIC_API_KEY, DEMO_MODE, PRICES
from payments.circle_client import fire_nanopayment, redeem_usyc_to_usdc
from payments.usyc_treasury import AgentTreasury


DEMO_PLAN_TEMPLATE = [
    {"agent": "researcher", "action": "web_search",      "detail": "Search for key information on the topic"},
    {"agent": "researcher", "action": "web_search",      "detail": "Search for market data and statistics"},
    {"agent": "researcher", "action": "web_search",      "detail": "Search for competitor information"},
    {"agent": "researcher", "action": "data_extraction", "detail": "Extract structured data from sources"},
    {"agent": "researcher", "action": "data_extraction", "detail": "Extract pricing and feature data"},
    {"agent": "researcher", "action": "fact_check",      "detail": "Verify key claims and statistics"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze market positioning"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze competitive landscape"},
    {"agent": "analyst",    "action": "analyze",         "detail": "Analyze strengths and weaknesses"},
    {"agent": "analyst",    "action": "summarize",       "detail": "Summarize research findings"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write executive summary"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write competitive analysis section"},
    {"agent": "writer",     "action": "write_paragraph", "detail": "Write recommendations section"},
    {"agent": "writer",     "action": "compile_report",  "detail": "Compile and format final report"},
]


class Orchestrator:
    def __init__(self, wallet: dict, treasury: AgentTreasury, emit_fn=None):
        self.wallet    = wallet
        self.treasury  = treasury
        self.emit      = emit_fn or (lambda event, data: None)
        self._client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if not DEMO_MODE else None
        self.tx_log    = []

    def plan_task(self, task: str) -> list[dict]:
        """Use Claude to break a task into a structured action plan."""
        if DEMO_MODE:
            # Return template with task injected into first item
            plan = DEMO_PLAN_TEMPLATE.copy()
            plan[0]["detail"] = f"Search for: {task}"
            return plan

        prompt = f"""You are an AI orchestrator managing a team of specialist agents.
Break the following task into a list of discrete micro-actions.
Each action must specify: agent (researcher/analyst/writer), action type, and a brief detail.

Available action types and costs (in USDC):
{PRICES}

Task: {task}

Respond ONLY with a JSON array of objects with keys: agent, action, detail.
Maximum 20 items. Keep it focused."""

        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        import json, re
        raw = msg.content[0].text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        return json.loads(match.group()) if match else DEMO_PLAN_TEMPLATE

    def pay_agent(self, agent_id: str, agent_address: str, action: str, detail: str) -> dict:
        """Redeem USYC -> USDC then fire nanopayment to specialist agent."""
        amount = PRICES.get(action, 0.001)

        # 1. Redeem USYC to cover payment
        redemption = redeem_usyc_to_usdc(self.wallet["wallet_id"], amount)
        self.treasury.redeem_for_payment(amount)

        # 2. Fire nanopayment on Arc
        tx = fire_nanopayment(
            from_wallet_id=self.wallet["wallet_id"],
            to_address=agent_address,
            amount_usdc=amount,
            memo=f"{agent_id}:{action}:{detail[:40]}",
        )
        self.treasury.debit_usdc(amount)

        receipt = {
            **tx,
            "agent":      agent_id,
            "action":     action,
            "detail":     detail,
            "amount":     amount,
            "redemption": redemption,
        }
        self.tx_log.append(receipt)

        self.emit("transaction", {
            "tx_hash":  tx["tx_hash"],
            "agent":    agent_id,
            "action":   action,
            "amount":   amount,
            "total_tx": len(self.tx_log),
            "chain":    "Arc",
        })
        return receipt

    def run(self, task: str, specialists: dict) -> dict:
        """
        Full orchestration loop.
        specialists: {"researcher": AgentRunner, "analyst": AgentRunner, "writer": AgentRunner}
        """
        self.emit("status", {"message": "Planning task...", "phase": "planning"})
        plan = self.plan_task(task)

        self.emit("status", {
            "message": f"Plan ready: {len(plan)} micro-actions across {len(set(p['agent'] for p in plan))} agents",
            "phase":   "dispatching",
            "plan":    plan,
        })

        results = []
        for step in plan:
            agent_id = step["agent"]
            action   = step["action"]
            detail   = step["detail"]
            specialist = specialists.get(agent_id)

            if not specialist:
                continue

            # Pay the specialist before it works
            receipt = self.pay_agent(agent_id, specialist.wallet["address"], action, detail)

            # Specialist executes the action
            self.emit("agent_active", {"agent": agent_id, "action": action})
            result = specialist.execute(action, detail, task)
            results.append({"agent": agent_id, "action": action, "result": result})

            self.emit("agent_done", {
                "agent":  agent_id,
                "action": action,
                "result": result[:120] if result else "",
            })

            time.sleep(0.3)   # Realistic pacing

        # Final compile
        self.emit("status", {"message": "Compiling final report...", "phase": "compiling"})
        final = self._compile(task, results)

        return {
            "report":        final,
            "transactions":  self.tx_log,
            "tx_count":      len(self.tx_log),
            "total_cost":    round(sum(t["amount"] for t in self.tx_log), 6),
            "treasury":      self.treasury.snapshot(),
        }

    def _compile(self, task: str, results: list) -> str:
        """Compile all agent results into a final report."""
        if DEMO_MODE:
            sections = [r["result"] for r in results if r.get("result")]
            return "\n\n".join(sections[:8]) or "Demo report compiled successfully."

        content = "\n".join(
            f"[{r['agent'].upper()} / {r['action']}]: {r['result']}"
            for r in results if r.get("result")
        )
        msg = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"Compile these agent outputs into a clean, structured report for: '{task}'\n\n{content}"
            }],
        )
        return msg.content[0].text
