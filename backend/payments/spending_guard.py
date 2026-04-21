"""
spending_guard.py
Programmable spending limits and guardrails for autonomous agents.

Implements budget caps, rate limits, recipient whitelists, and
daily/per-action spending controls — critical for trustless AI agents.

This is what separates a trustworthy autonomous agent from an
unconstrained one that could drain its treasury.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from config import PRICES


@dataclass
class SpendingPolicy:
    """
    Defines the spending rules for a single agent.
    All limits are in USDC.
    """
    agent_id:           str
    max_per_action:     float = 0.01        # Hard cap per single payment
    max_per_day:        float = 1.00        # Daily spending limit
    max_per_pipeline:   float = 0.50        # Single pipeline run limit
    allowed_recipients: list  = field(default_factory=list)  # Whitelist (empty = allow all)
    allowed_actions:    list  = field(default_factory=list)  # Action whitelist (empty = allow all)
    require_approval_above: float = 0.005  # Flag payments above this for review
    enabled:            bool  = True


@dataclass
class SpendingRecord:
    """Tracks actual spending for enforcement."""
    agent_id:         str
    today_spent:      float = 0.0
    pipeline_spent:   float = 0.0
    total_spent:      float = 0.0
    action_count:     int   = 0
    blocked_count:    int   = 0
    flagged_count:    int   = 0
    last_reset:       float = field(default_factory=time.time)
    violations:       list  = field(default_factory=list)

    def reset_daily(self):
        """Reset daily counter at midnight."""
        now = time.time()
        if now - self.last_reset > 86400:
            self.today_spent = 0.0
            self.last_reset  = now

    def reset_pipeline(self):
        """Reset pipeline counter at start of each run."""
        self.pipeline_spent = 0.0


class SpendingGuard:
    """
    Enforces spending policies on agent payments.

    Every payment must pass through check() before firing.
    Blocked payments are logged with reason.
    Flagged payments are allowed but noted for review.
    """

    def __init__(self):
        self._policies: dict[str, SpendingPolicy] = {}
        self._records:  dict[str, SpendingRecord]  = {}

    def set_policy(self, policy: SpendingPolicy):
        """Register or update a spending policy for an agent."""
        self._policies[policy.agent_id] = policy
        if policy.agent_id not in self._records:
            self._records[policy.agent_id] = SpendingRecord(agent_id=policy.agent_id)

    def get_record(self, agent_id: str) -> Optional[SpendingRecord]:
        return self._records.get(agent_id)

    def reset_pipeline(self, agent_id: str):
        """Call at the start of each pipeline run."""
        if agent_id in self._records:
            self._records[agent_id].reset_pipeline()

    def reset_all_pipelines(self):
        """Reset pipeline counters for all agents."""
        for record in self._records.values():
            record.reset_pipeline()

    def check(self, agent_id: str, amount: float, action: str, recipient: str = "") -> dict:
        """
        Check whether a payment is allowed.

        Returns:
            {
                "allowed":  bool,
                "flagged":  bool,
                "reason":   str,
                "amount":   float,
                "action":   str,
            }
        """
        policy = self._policies.get(agent_id)
        record = self._records.get(agent_id)

        # No policy registered — allow by default
        if not policy or not record:
            return {"allowed": True, "flagged": False, "reason": "no_policy", "amount": amount, "action": action}

        if not policy.enabled:
            return {"allowed": True, "flagged": False, "reason": "policy_disabled", "amount": amount, "action": action}

        # Reset daily counter if needed
        record.reset_daily()

        # ── Checks ───────────────────────────────────────────────────────────

        # 1. Per-action cap
        if amount > policy.max_per_action:
            return self._block(record, amount, action,
                f"Amount ${amount:.4f} exceeds per-action cap ${policy.max_per_action:.4f}")

        # 2. Daily limit
        if record.today_spent + amount > policy.max_per_day:
            return self._block(record, amount, action,
                f"Daily limit ${policy.max_per_day:.2f} would be exceeded (spent ${record.today_spent:.4f})")

        # 3. Pipeline limit
        if record.pipeline_spent + amount > policy.max_per_pipeline:
            return self._block(record, amount, action,
                f"Pipeline limit ${policy.max_per_pipeline:.2f} would be exceeded")

        # 4. Action whitelist
        if policy.allowed_actions and action not in policy.allowed_actions:
            return self._block(record, amount, action,
                f"Action '{action}' not in allowed list: {policy.allowed_actions}")

        # 5. Recipient whitelist
        if policy.allowed_recipients and recipient and recipient not in policy.allowed_recipients:
            return self._block(record, amount, action,
                f"Recipient {recipient[:12]}... not whitelisted")

        # ── Payment approved ─────────────────────────────────────────────────
        record.today_spent    += amount
        record.pipeline_spent += amount
        record.total_spent    += amount
        record.action_count   += 1

        # Flag if above threshold
        flagged = amount >= policy.require_approval_above
        if flagged:
            record.flagged_count += 1

        return {
            "allowed": True,
            "flagged": flagged,
            "reason":  "approved" + (" (flagged for review)" if flagged else ""),
            "amount":  amount,
            "action":  action,
        }

    def _block(self, record: SpendingRecord, amount: float, action: str, reason: str) -> dict:
        record.blocked_count += 1
        record.violations.append({
            "ts":     time.time(),
            "action": action,
            "amount": amount,
            "reason": reason,
        })
        return {"allowed": False, "flagged": False, "reason": reason, "amount": amount, "action": action}

    def snapshot(self) -> dict:
        """Return spending summary for all agents."""
        return {
            aid: {
                "today_spent":    round(r.today_spent, 6),
                "pipeline_spent": round(r.pipeline_spent, 6),
                "total_spent":    round(r.total_spent, 6),
                "action_count":   r.action_count,
                "blocked_count":  r.blocked_count,
                "flagged_count":  r.flagged_count,
                "violations":     r.violations[-5:],  # Last 5 only
            }
            for aid, r in self._records.items()
        }


# ── Default policy builder ────────────────────────────────────────────────────

def default_policy(agent_id: str) -> SpendingPolicy:
    """
    Standard policy for AgentFloat agents.
    Limits are set conservatively for testnet safety.
    """
    return SpendingPolicy(
        agent_id           = agent_id,
        max_per_action     = 0.005,    # Max $0.005 per single action
        max_per_day        = 2.00,     # Max $2.00 per day
        max_per_pipeline   = 0.50,     # Max $0.50 per pipeline run
        allowed_recipients = [],       # Open — any Circle wallet
        allowed_actions    = list(PRICES.keys()),  # Only known action types
        require_approval_above = 0.002,  # Flag actions over $0.002
        enabled            = True,
    )


# ── Global guard instance ─────────────────────────────────────────────────────
guard = SpendingGuard()
