"""
orchestrator.py
Master agent — x402, ERC-8004, AIsa, USYC, SpendingGuard, Gateway.
"""

import time
import json
import re
from config import DEMO_MODE, PRICES
from payments.circle_client import fire_nanopayment, redeem_usyc_to_usdc
from payments.usyc_treasury import AgentTreasury
from payments.x402 import X402Client
from payments.erc8004 import registry
from payments.aisa_client import AisaClient
from payments.spending_guard import guard, default_policy
from payments.gateway_client import get_gateway_balance, gateway_pool_summary
from agents.ai_client import get_client, chat

DEMO_PLAN = [
    {"agent":"researcher","action":"web_search","detail":"Search for key information on the topic"},
    {"agent":"researcher","action":"web_search","detail":"Search for market data and statistics"},
    {"agent":"researcher","action":"web_search","detail":"Search for competitor information"},
    {"agent":"researcher","action":"data_extraction","detail":"Extract structured data from sources"},
    {"agent":"researcher","action":"data_extraction","detail":"Extract pricing and feature comparisons"},
    {"agent":"researcher","action":"fact_check","detail":"Verify key claims and data points"},
    {"agent":"analyst","action":"analyze","detail":"Analyze market positioning"},
    {"agent":"analyst","action":"analyze","detail":"Analyze competitive landscape"},
    {"agent":"analyst","action":"analyze","detail":"Analyze TAM SAM SOM metrics"},
    {"agent":"analyst","action":"summarize","detail":"Summarize research findings"},
    {"agent":"writer","action":"write_paragraph","detail":"Write executive summary"},
    {"agent":"writer","action":"write_paragraph","detail":"Write competitive analysis section"},
    {"agent":"writer","action":"write_paragraph","detail":"Write recommendations section"},
    {"agent":"writer","action":"compile_report","detail":"Compile and format final report"},
]


class Orchestrator:
    def __init__(self, wallet: dict, treasury: AgentTreasury, emit_fn=None):
        self.wallet   = wallet
        self.treasury = treasury
        self.emit     = emit_fn or (lambda e, d: None)
        self._client  = get_client()
        self.tx_log   = []
        self.x402     = X402Client(wallet["wallet_id"], wallet["address"], treasury)
        self.identity = registry.get("orchestrator")

        # Register spending policy for orchestrator
        guard.set_policy(default_policy("orchestrator"))
        guard.reset_pipeline("orchestrator")

    def plan_task(self, task: str) -> list:
        if DEMO_MODE or self._client is None:
            plan = [dict(s) for s in DEMO_PLAN]
            plan[0]["detail"] = f"Search for: {task}"
            return plan
        system = "You are an AI orchestrator. Break tasks into micro-actions for specialist agents."
        prompt = f"""Break this task into micro-actions.
Each must have: agent (researcher/analyst/writer), action ({list(PRICES.keys())}), detail.
Task: {task}
Respond ONLY with a JSON array. Max 14 items."""
        try:
            raw   = chat(self._client, system, prompt, max_tokens=600)
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            return json.loads(match.group()) if match else DEMO_PLAN
        except Exception:
            return DEMO_PLAN

    def pay_agent(self, agent_id: str, agent_address: str, action: str, detail: str) -> dict:
        amount = PRICES.get(action, 0.001)

        # ── SpendingGuard check ──────────────────────────────────────────────
        guard_result = guard.check("orchestrator", amount, action, agent_address)
        if not guard_result["allowed"]:
            self.emit("guard_blocked", {
                "agent":  agent_id,
                "action": action,
                "amount": amount,
                "reason": guard_result["reason"],
            })
            # Skip this payment but continue pipeline
            return {"tx_hash": "blocked", "amount": 0, "agent": agent_id,
                    "action": action, "detail": detail, "blocked": True,
                    "reason": guard_result["reason"]}

        # ── ERC-8004 validation ──────────────────────────────────────────────
        valid, reason = registry.validate(agent_id)

        # ── Gateway balance check ────────────────────────────────────────────
        gw_balance = get_gateway_balance(self.wallet["address"])

        # ── USYC redeem + nanopayment ─────────────────────────────────────────
        redeem_usyc_to_usdc(self.wallet["wallet_id"], amount)
        self.treasury.redeem_for_payment(amount)
        tx = fire_nanopayment(
            self.wallet["wallet_id"], agent_address, amount,
            f"{agent_id}:{action}:{detail[:40]}"
        )
        self.treasury.debit_usdc(amount)
        registry.record_payment("orchestrator", amount)

        receipt = {
            **tx, "agent": agent_id, "action": action,
            "detail": detail, "amount": amount,
            "erc8004_verified": valid,
            "flagged": guard_result.get("flagged", False),
            "gateway_balance": gw_balance.get("usdc_balance", 0),
        }
        self.tx_log.append(receipt)

        self.emit("transaction", {
            "tx_hash":          tx["tx_hash"],
            "agent":            agent_id,
            "action":           action,
            "amount":           amount,
            "total_tx":         len(self.tx_log),
            "chain":            "Arc",
            "erc8004_verified": valid,
            "flagged":          guard_result.get("flagged", False),
            "gateway_balance":  gw_balance.get("usdc_balance", 0),
        })
        return receipt

    def run(self, task: str, specialists: dict) -> dict:
        # Reset spending guard for new pipeline
        guard.reset_all_pipelines()

        self.emit("status", {"message": "Planning task...", "phase": "planning"})
        plan = self.plan_task(task)

        self.emit("status", {
            "message": f"Plan: {len(plan)} micro-actions across {len(set(p['agent'] for p in plan))} agents",
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
            if receipt.get("blocked"):
                results.append({"agent": agent_id, "action": action, "result": f"[Blocked: {receipt['reason']}]"})
                continue

            self.emit("agent_active", {"agent": agent_id, "action": action})
            result = specialist.execute(action, detail, task)
            results.append({"agent": agent_id, "action": action, "result": result})
            registry.record_success(agent_id, earned=receipt["amount"])

            self.emit("agent_done", {
                "agent":  agent_id,
                "action": action,
                "result": (result or "")[:120],
            })
            time.sleep(0.3)

        self.emit("status", {"message": "Compiling final report...", "phase": "compiling"})
        final = self._compile(task, results)

        # Gateway pool summary
        wallets = [self.wallet["address"]]
        gw_pool = gateway_pool_summary(wallets)

        return {
            "report":         final,
            "transactions":   self.tx_log,
            "tx_count":       len(self.tx_log),
            "total_cost":     round(sum(t["amount"] for t in self.tx_log), 6),
            "treasury":       self.treasury.snapshot(),
            "erc8004":        registry.all_agents(),
            "spending_guard": guard.snapshot(),
            "gateway_pool":   gw_pool,
        }

    def _compile(self, task: str, results: list) -> str:
        if DEMO_MODE or self._client is None:
            return "\n\n".join(r["result"] for r in results if r.get("result"))[:2000]
        content = "\n".join(
            f"[{r['agent'].upper()}/{r['action']}]: {r['result']}"
            for r in results if r.get("result")
        )
        system = "You are a professional report writer. Be clear and structured."
        prompt = f"Compile these agent outputs into a clean report for: '{task}'\n\n{content}"
        return chat(self._client, system, prompt, max_tokens=1500)
