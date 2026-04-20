"""
erc8004.py
ERC-8004 Trust Layer for Autonomous Agents.

ERC-8004 defines a standard for agent identity, reputation, and validation
on EVM-compatible chains. It allows:
  - Agents to have verifiable onchain identities
  - Reputation scores updated based on task outcomes
  - Validation of agent credentials before payment
  - Trust-based routing (higher-trust agents get higher-value tasks)

Reference: ERC-8004-vyper implementation from Circle hackathon resources.
On Arc testnet we implement a lightweight version of this standard.
"""

import uuid
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from config import DEMO_MODE, ARC_RPC_URL


@dataclass
class AgentIdentity:
    """ERC-8004 compliant agent identity."""
    agent_id:        str
    display_name:    str
    role:            str            # orchestrator | researcher | analyst | writer
    wallet_address:  str
    created_at:      float = field(default_factory=time.time)
    reputation:      float = 100.0  # 0-1000 scale
    tasks_completed: int   = 0
    tasks_failed:    int   = 0
    total_earned:    float = 0.0
    total_paid:      float = 0.0
    is_verified:     bool  = False
    trust_level:     str   = "standard"  # standard | trusted | elite
    erc8004_token:   str   = ""

    def __post_init__(self):
        if not self.erc8004_token:
            # Deterministic identity token based on agent attributes
            raw = f"{self.agent_id}:{self.wallet_address}:{self.created_at}"
            self.erc8004_token = "0x" + hashlib.sha256(raw.encode()).hexdigest()

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 1.0

    @property
    def trust_score(self) -> float:
        """Composite trust score 0-1000."""
        base    = self.reputation
        sr_mod  = self.success_rate * 100
        exp_mod = min(self.tasks_completed * 2, 100)
        return min(base + sr_mod * 0.3 + exp_mod * 0.2, 1000)

    def to_dict(self) -> dict:
        return {
            "agent_id":        self.agent_id,
            "display_name":    self.display_name,
            "role":            self.role,
            "wallet_address":  self.wallet_address,
            "erc8004_token":   self.erc8004_token,
            "reputation":      round(self.reputation, 2),
            "trust_score":     round(self.trust_score, 2),
            "trust_level":     self.trust_level,
            "tasks_completed": self.tasks_completed,
            "tasks_failed":    self.tasks_failed,
            "success_rate":    round(self.success_rate, 4),
            "total_earned":    round(self.total_earned, 6),
            "total_paid":      round(self.total_paid, 6),
            "is_verified":     self.is_verified,
        }


class ERC8004Registry:
    """
    Onchain agent identity registry (ERC-8004).
    In production this is a smart contract on Arc.
    In demo/testnet we use an in-memory store with the same interface.
    """

    def __init__(self):
        self._agents: dict[str, AgentIdentity] = {}
        self._chain  = ARC_RPC_URL

    def register(self, agent_id: str, display_name: str, role: str, wallet_address: str) -> AgentIdentity:
        """Register a new agent identity on Arc."""
        identity = AgentIdentity(
            agent_id=agent_id,
            display_name=display_name,
            role=role,
            wallet_address=wallet_address,
            is_verified=True,     # Auto-verified on testnet
            trust_level="standard",
        )
        self._agents[agent_id] = identity

        if not DEMO_MODE:
            self._register_onchain(identity)

        return identity

    def get(self, agent_id: str) -> Optional[AgentIdentity]:
        return self._agents.get(agent_id)

    def validate(self, agent_id: str, min_trust: float = 0) -> tuple[bool, str]:
        """Validate an agent before allowing it to receive payment."""
        identity = self._agents.get(agent_id)
        if not identity:
            return False, "Agent not registered in ERC-8004 registry"
        if not identity.is_verified:
            return False, "Agent identity not verified"
        if identity.trust_score < min_trust:
            return False, f"Trust score {identity.trust_score:.0f} below minimum {min_trust}"
        return True, "Valid"

    def record_success(self, agent_id: str, earned: float = 0.0):
        """Update reputation after successful task completion."""
        identity = self._agents.get(agent_id)
        if not identity:
            return
        identity.tasks_completed += 1
        identity.total_earned    += earned
        # Reputation increases with successful completions, capped at 1000
        identity.reputation = min(identity.reputation + 2.5, 1000)
        self._update_trust_level(identity)

    def record_failure(self, agent_id: str):
        """Update reputation after failed task."""
        identity = self._agents.get(agent_id)
        if not identity:
            return
        identity.tasks_failed += 1
        identity.reputation   = max(identity.reputation - 10, 0)
        self._update_trust_level(identity)

    def record_payment(self, agent_id: str, paid: float):
        """Record outgoing payment from agent treasury."""
        identity = self._agents.get(agent_id)
        if identity:
            identity.total_paid += paid

    def _update_trust_level(self, identity: AgentIdentity):
        score = identity.trust_score
        if score >= 800:
            identity.trust_level = "elite"
        elif score >= 500:
            identity.trust_level = "trusted"
        else:
            identity.trust_level = "standard"

    def _register_onchain(self, identity: AgentIdentity):
        """Register agent identity on Arc via smart contract call."""
        try:
            import requests
            # ERC-8004 registration transaction on Arc
            payload = {
                "jsonrpc": "2.0",
                "method":  "eth_sendTransaction",
                "params":  [{
                    "from":  identity.wallet_address,
                    "to":    "0xERC8004RegistryContract",
                    "data":  self._encode_register(identity),
                }],
                "id": 1,
            }
            requests.post(self._chain, json=payload, timeout=5)
        except Exception:
            pass  # Fail silently on testnet — in-memory store is source of truth

    def _encode_register(self, identity: AgentIdentity) -> str:
        """Encode ERC-8004 register call ABI."""
        # register(bytes32 agentId, string role, address wallet)
        return "0x" + identity.erc8004_token[2:34]

    def all_agents(self) -> list[dict]:
        return [a.to_dict() for a in self._agents.values()]

    def leaderboard(self) -> list[dict]:
        agents = sorted(self._agents.values(), key=lambda a: a.trust_score, reverse=True)
        return [a.to_dict() for a in agents]


# ── Global registry (singleton) ───────────────────────────────────────────────
registry = ERC8004Registry()
