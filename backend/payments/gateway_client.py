"""
gateway_client.py
Circle Gateway integration — unified USDC balance accessible crosschain.

Gateway bundles thousands of nanopayments into a single onchain settlement,
making individual payments gas-free. It is the financial rail that makes
Circle Nanopayments economically viable at scale.

Key capabilities used:
  - Unified USDC balance across all supported chains
  - Gas-free nanopayment submission via Gateway
  - Batch settlement status tracking
  - Crosschain balance visibility
"""

import uuid
import time
import requests
from config import CIRCLE_API_KEY, CIRCLE_BASE_URL, DEMO_MODE


# Gateway API endpoints
GATEWAY_BASE   = "https://api-sandbox.circle.com/v1/gateway"
NANOPAY_SUBMIT = f"{GATEWAY_BASE}/nanopayments"
NANOPAY_STATUS = f"{GATEWAY_BASE}/nanopayments/{{payment_id}}/status"
BALANCE_URL    = f"{GATEWAY_BASE}/balances"


def _headers():
    return {
        "Authorization": f"Bearer {CIRCLE_API_KEY}",
        "Content-Type":  "application/json",
    }


# ── Gateway Balance ───────────────────────────────────────────────────────────

def get_gateway_balance(wallet_address: str) -> dict:
    """
    Get unified USDC balance via Circle Gateway.
    Gateway aggregates balance across all supported chains.
    Returns balance visible crosschain without multiple RPC calls.
    """
    if DEMO_MODE:
        return _mock_gateway_balance(wallet_address)

    try:
        r = requests.get(
            BALANCE_URL,
            params={"address": wallet_address},
            headers=_headers(),
            timeout=8,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        return {
            "address":       wallet_address,
            "usdc_balance":  float(data.get("usdcBalance", 0)),
            "chains":        data.get("chains", []),
            "last_updated":  data.get("updatedAt", ""),
            "gateway":       True,
        }
    except Exception as exc:
        return {**_mock_gateway_balance(wallet_address), "error": str(exc)}


def _mock_gateway_balance(address: str) -> dict:
    import random
    return {
        "address":      address,
        "usdc_balance": round(random.uniform(4.5, 5.5), 4),
        "chains":       [
            {"chain": "ARC",      "balance": round(random.uniform(2.0, 3.0), 4)},
            {"chain": "BASE",     "balance": round(random.uniform(1.0, 2.0), 4)},
            {"chain": "ETHEREUM", "balance": round(random.uniform(0.5, 1.0), 4)},
        ],
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gateway":      True,
        "demo":         True,
    }


# ── Gateway Nanopayment Submission ────────────────────────────────────────────

def submit_nanopayment_gateway(
    from_address: str,
    to_address:   str,
    amount_usdc:  float,
    memo:         str = "",
) -> dict:
    """
    Submit a nanopayment via Circle Gateway.
    Gateway batches payments for gas-free onchain settlement.
    Individual payments settle near-instantly off-chain,
    with batch onchain settlement handled by Circle.
    """
    if DEMO_MODE:
        return _mock_nanopay(from_address, to_address, amount_usdc, memo)

    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "source":    {"type": "address", "address": from_address},
        "destination": {"type": "address", "address": to_address},
        "amount":    {"amount": f"{amount_usdc:.6f}", "currency": "USDC"},
        "memo":      memo,
    }
    try:
        r = requests.post(NANOPAY_SUBMIT, json=payload, headers=_headers(), timeout=8)
        r.raise_for_status()
        data = r.json().get("data", {})
        return {
            "payment_id":  data.get("id", str(uuid.uuid4())),
            "status":      data.get("status", "pending"),
            "amount":      amount_usdc,
            "memo":        memo,
            "gateway":     True,
            "gas_free":    True,
            "settled_at":  data.get("settledAt", ""),
        }
    except Exception as exc:
        return {**_mock_nanopay(from_address, to_address, amount_usdc, memo), "error": str(exc)}


def _mock_nanopay(from_addr, to_addr, amount, memo):
    import random, string
    return {
        "payment_id":  "gw-" + "".join(random.choices(string.hexdigits.lower(), k=16)),
        "status":      "settled",
        "amount":      amount,
        "memo":        memo,
        "gateway":     True,
        "gas_free":    True,
        "batch_id":    "batch-" + str(int(time.time())),
        "demo":        True,
    }


# ── Batch Settlement Status ───────────────────────────────────────────────────

def get_settlement_status(payment_id: str) -> dict:
    """Check the settlement status of a Gateway nanopayment."""
    if DEMO_MODE:
        return {
            "payment_id": payment_id,
            "status":     "settled",
            "onchain_tx": "0x" + "a" * 64,
            "settled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "demo":       True,
        }
    try:
        r = requests.get(
            NANOPAY_STATUS.format(payment_id=payment_id),
            headers=_headers(),
            timeout=8,
        )
        r.raise_for_status()
        return r.json().get("data", {})
    except Exception as exc:
        return {"payment_id": payment_id, "error": str(exc)}


# ── Gateway Pool Summary ──────────────────────────────────────────────────────

def gateway_pool_summary(wallets: list[str]) -> dict:
    """
    Get aggregate Gateway balance across all agent wallets.
    Shows total USDC available across the entire agent pool.
    """
    balances = [get_gateway_balance(w) for w in wallets]
    total    = sum(b.get("usdc_balance", 0) for b in balances)
    return {
        "total_usdc":    round(total, 4),
        "wallet_count":  len(wallets),
        "balances":      balances,
        "gateway":       True,
        "timestamp":     time.time(),
    }
