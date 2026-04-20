"""
usyc_treasury.py
Tracks yield accrued on idle agent USYC balances.
Each agent holds USYC as its "savings account". When it needs to pay,
USYC redeems to USDC in one block on Arc, then the nanopayment fires.
"""

import time
from config import USYC_RATE_PER_SECOND


class AgentTreasury:
    def __init__(self, wallet_id: str, initial_usyc: float = 5.0):
        self.wallet_id      = wallet_id
        self.usyc_balance   = initial_usyc
        self.usdc_balance   = 0.0
        self.yield_earned   = 0.0
        self._last_tick     = time.time()
        self._start_time    = time.time()
        self.total_paid_out = 0.0

    def tick(self):
        """Accrue yield on USYC balance since last tick."""
        now   = time.time()
        delta = now - self._last_tick
        accrued = self.usyc_balance * USYC_RATE_PER_SECOND * delta
        self.yield_earned  += accrued
        self.usyc_balance  += accrued
        self._last_tick     = now
        return accrued

    def redeem_for_payment(self, amount_usdc: float) -> float:
        """
        Redeem USYC -> USDC to cover a payment.
        Returns actual USDC amount available.
        """
        self.tick()
        needed = min(amount_usdc, self.usyc_balance)
        self.usyc_balance  -= needed
        self.usdc_balance  += needed
        return needed

    def debit_usdc(self, amount: float):
        """Debit USDC after a nanopayment fires."""
        self.usdc_balance  -= amount
        self.total_paid_out += amount

    def snapshot(self) -> dict:
        self.tick()
        return {
            "wallet_id":     self.wallet_id,
            "usyc_balance":  round(self.usyc_balance, 6),
            "usdc_balance":  round(self.usdc_balance, 6),
            "yield_earned":  round(self.yield_earned, 8),
            "total_paid":    round(self.total_paid_out, 6),
            "uptime_seconds": round(time.time() - self._start_time, 1),
        }


class TreasuryPool:
    """Aggregate treasury across all agents in the pool."""

    def __init__(self):
        self._agents: dict[str, AgentTreasury] = {}

    def add(self, agent_id: str, treasury: AgentTreasury):
        self._agents[agent_id] = treasury

    def get(self, agent_id: str) -> AgentTreasury:
        return self._agents[agent_id]

    def total_yield(self) -> float:
        return sum(a.yield_earned for a in self._agents.values())

    def total_paid(self) -> float:
        return sum(a.total_paid_out for a in self._agents.values())

    def snapshot_all(self) -> dict:
        return {aid: t.snapshot() for aid, t in self._agents.items()}
