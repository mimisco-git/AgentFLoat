"""
circle_client.py
Handles Circle Wallet creation, USDC balance queries, and nanopayments.
Falls back to simulated responses when DEMO_MODE is active.
"""

import uuid
import time
import random
import string
import requests
from config import (
    CIRCLE_API_KEY, CIRCLE_BASE_URL, CIRCLE_ENV, DEMO_MODE
)


def _headers():
    return {
        "Authorization": f"Bearer {CIRCLE_API_KEY}",
        "Content-Type": "application/json",
    }


# ── Wallet Management ─────────────────────────────────────────────────────────

def create_wallet(label: str) -> dict:
    """Create a Circle developer-controlled wallet for an agent."""
    if DEMO_MODE:
        return _mock_wallet(label)

    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "description":    label,
        "accountType":    "SCA",
        "blockchains":    ["ARC-TESTNET" if CIRCLE_ENV == "sandbox" else "ARC"],
    }
    r = requests.post(f"{CIRCLE_BASE_URL}/v1/developer/wallets", json=payload, headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    return {
        "wallet_id": data["walletId"],
        "address":   data["address"],
        "label":     label,
        "usdc_balance": 5.00,
        "usyc_balance": 5.00,
    }


def get_balance(wallet_id: str) -> dict:
    """Return USDC and USYC balances for a wallet."""
    if DEMO_MODE:
        return {"usdc": round(random.uniform(0.5, 5.0), 4), "usyc": round(random.uniform(0.5, 5.0), 4)}

    r = requests.get(f"{CIRCLE_BASE_URL}/v1/wallets/{wallet_id}/balances", headers=_headers(), timeout=10)
    r.raise_for_status()
    balances = r.json()["data"]["tokenBalances"]
    usdc = usyc = 0.0
    for b in balances:
        symbol = b.get("token", {}).get("symbol", "")
        if symbol == "USDC":
            usdc = float(b["amount"])
        elif symbol == "USYC":
            usyc = float(b["amount"])
    return {"usdc": usdc, "usyc": usyc}


# ── Nanopayments ──────────────────────────────────────────────────────────────

def fire_nanopayment(from_wallet_id: str, to_address: str, amount_usdc: float, memo: str) -> dict:
    """
    Fire a sub-cent nanopayment via Circle Nanopayments on Arc.
    Returns a transaction receipt.
    """
    if DEMO_MODE:
        return _mock_tx(from_wallet_id, to_address, amount_usdc, memo)

    payload = {
        "idempotencyKey":    str(uuid.uuid4()),
        "source":            {"type": "wallet", "id": from_wallet_id},
        "destination":       {"type": "blockchain", "address": to_address, "chain": "ARC"},
        "amount":            {"amount": f"{amount_usdc:.6f}", "currency": "USDC"},
        "memo":              memo,
    }
    r = requests.post(
        f"{CIRCLE_BASE_URL}/v1/transfers",
        json=payload,
        headers=_headers(),
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()["data"]
    return {
        "tx_hash":    data.get("transactionHash", _rand_hash()),
        "amount":     amount_usdc,
        "memo":       memo,
        "status":     data.get("status", "complete"),
        "timestamp":  time.time(),
        "chain":      "Arc",
    }


# ── USYC redemption ───────────────────────────────────────────────────────────

def redeem_usyc_to_usdc(wallet_id: str, amount_usdc: float) -> dict:
    """
    Instantly redeem USYC -> USDC (one block on Arc) before firing a payment.
    """
    if DEMO_MODE:
        return {
            "redeemed_usyc": round(amount_usdc * 1.0002, 6),
            "received_usdc": amount_usdc,
            "tx_hash":       _rand_hash(),
            "block_time_ms": random.randint(280, 480),
        }

    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "walletId":       wallet_id,
        "amount":         f"{amount_usdc:.6f}",
        "outputCurrency": "USDC",
    }
    r = requests.post(f"{CIRCLE_BASE_URL}/v1/usyc/redeem", json=payload, headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    return {
        "redeemed_usyc": float(data.get("usycAmount", amount_usdc)),
        "received_usdc": amount_usdc,
        "tx_hash":       data.get("transactionHash", _rand_hash()),
        "block_time_ms": data.get("blockTimeMs", 350),
    }


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _mock_wallet(label: str) -> dict:
    return {
        "wallet_id":    f"wallet_{uuid.uuid4().hex[:8]}",
        "address":      "0x" + uuid.uuid4().hex[:40],
        "label":        label,
        "usdc_balance": 5.00,
        "usyc_balance": 5.00,
    }


def _mock_tx(from_wallet_id, to_address, amount_usdc, memo) -> dict:
    return {
        "tx_hash":   _rand_hash(),
        "amount":    amount_usdc,
        "memo":      memo,
        "status":    "complete",
        "timestamp": time.time(),
        "chain":     "Arc",
    }


def _rand_hash() -> str:
    return "0x" + "".join(random.choices(string.hexdigits.lower(), k=64))
