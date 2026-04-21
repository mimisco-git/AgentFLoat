"""
bridge_kit.py
Circle Bridge Kit integration.

The Bridge Kit wraps CCTP and Gateway to give a single unified interface
for moving USDC across chains. It handles:
  - Route selection (CCTP for native burns, Gateway for batched transfers)
  - Fee estimation before committing
  - Transfer status tracking end-to-end
  - Automatic retry on attestation delays

For AgentFloat: used to pre-fund agent wallets on Arc from any supported
chain, and to sweep profits back to the operator's treasury chain.
"""

import time
import uuid
import requests
from config import CIRCLE_API_KEY, CIRCLE_BASE_URL, DEMO_MODE
from payments.cctp_client import initiate_transfer, get_attestation, CCTP_DOMAINS
from payments.gateway_client import get_gateway_balance

BRIDGE_BASE = f"{CIRCLE_BASE_URL}/v1/bridge"


def _headers():
    return {
        "Authorization": f"Bearer {CIRCLE_API_KEY}",
        "Content-Type":  "application/json",
    }


# ── Route estimation ──────────────────────────────────────────────────────────

def estimate_route(
    from_chain: str,
    to_chain:   str,
    amount_usdc: float,
) -> dict:
    """
    Estimate the best route for a cross-chain USDC transfer.
    Chooses between CCTP (native burn/mint) and Gateway (batched).

    CCTP is preferred for larger amounts (>$1 USDC).
    Gateway is preferred for nanopayment-scale amounts (<$1 USDC).
    """
    use_cctp    = amount_usdc >= 1.0
    route       = "cctp" if use_cctp else "gateway"
    est_time    = "15-20 minutes" if use_cctp else "near-instant"
    est_fee     = 0.0 if use_cctp else 0.0   # Both are fee-free at testnet

    return {
        "from_chain":    from_chain,
        "to_chain":      to_chain,
        "amount":        amount_usdc,
        "route":         route,
        "protocol":      "Circle CCTP v2" if use_cctp else "Circle Gateway",
        "estimated_time": est_time,
        "estimated_fee": est_fee,
        "native_usdc":   True,   # Always native, never wrapped
        "gas_required":  False,  # Arc uses USDC as gas natively
    }


# ── Bridge execution ──────────────────────────────────────────────────────────

def bridge_usdc(
    from_chain:   str,
    to_chain:     str,
    amount_usdc:  float,
    recipient:    str,
    wallet_id:    str = "",
) -> dict:
    """
    Bridge USDC from one chain to another using the optimal route.
    Returns a transfer receipt with status and tracking info.
    """
    if DEMO_MODE:
        return _mock_bridge(from_chain, to_chain, amount_usdc, recipient)

    route_info = estimate_route(from_chain, to_chain, amount_usdc)

    if route_info["route"] == "cctp":
        result = initiate_transfer(
            from_chain=from_chain,
            to_chain=to_chain,
            amount_usdc=amount_usdc,
            recipient=recipient,
            wallet_id=wallet_id,
        )
    else:
        # Use Gateway for small amounts
        from payments.gateway_client import submit_nanopayment_gateway
        result = submit_nanopayment_gateway(
            from_address=recipient,
            to_address=recipient,
            amount_usdc=amount_usdc,
            memo=f"bridge:{from_chain}->{to_chain}",
        )

    return {
        **result,
        "route_info": route_info,
        "bridge_kit": True,
    }


def fund_agent_on_arc(
    agent_address:  str,
    amount_usdc:    float,
    source_chain:   str = "ethereum",
    wallet_id:      str = "",
) -> dict:
    """
    Fund an agent wallet on Arc from any supported chain.
    Used during agent pool initialization to top up Arc treasuries.
    """
    result = bridge_usdc(
        from_chain=source_chain,
        to_chain="arc",
        amount_usdc=amount_usdc,
        recipient=agent_address,
        wallet_id=wallet_id,
    )
    result["purpose"]     = "agent_funding"
    result["agent_addr"]  = agent_address
    return result


def sweep_profits(
    agent_address:    str,
    amount_usdc:      float,
    destination_chain: str = "base",
    wallet_id:        str  = "",
) -> dict:
    """
    Sweep accumulated agent profits from Arc to a treasury chain.
    Called by operator to collect earnings.
    """
    result = bridge_usdc(
        from_chain="arc",
        to_chain=destination_chain,
        amount_usdc=amount_usdc,
        recipient=agent_address,
        wallet_id=wallet_id,
    )
    result["purpose"] = "profit_sweep"
    return result


def _mock_bridge(from_chain, to_chain, amount, recipient):
    route = estimate_route(from_chain, to_chain, amount)
    return {
        "bridge_id":    "bk-" + uuid.uuid4().hex[:16],
        "from_chain":   from_chain,
        "to_chain":     to_chain,
        "amount":       amount,
        "recipient":    recipient,
        "status":       "complete",
        "route_info":   route,
        "tx_hash":      "0x" + "d" * 64,
        "bridge_kit":   True,
        "demo":         True,
        "native_usdc":  True,
        "completed_at": time.time(),
    }


# ── Multi-chain balance view ──────────────────────────────────────────────────

def multichain_balance(address: str) -> dict:
    """
    Get USDC balance for an address across all supported chains.
    Uses Circle Gateway for unified crosschain view.
    """
    gw = get_gateway_balance(address)
    return {
        "address":       address,
        "total_usdc":    gw.get("usdc_balance", 0),
        "chains":        gw.get("chains", []),
        "supported_chains": list(CCTP_DOMAINS.keys()),
        "bridge_kit":    True,
    }
