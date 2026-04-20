"""
x402.py
Web-native payment middleware implementing the x402 payment standard.

x402 is an HTTP-level payment protocol where:
  - A server returns HTTP 402 Payment Required with payment details
  - The client pays (via USDC nanopayment on Arc)
  - The client retries with a payment receipt header
  - The server verifies and serves the resource

This makes agents pay per HTTP request automatically at the transport layer,
no manual payment logic required in business code.

References:
  - x402 facilitator: verifies and submits x402 payments
  - Circle Nanopayments: the settlement rail
  - Arc: the settlement chain
"""

import uuid
import time
import hashlib
import json
import requests
from functools import wraps
from flask import request, jsonify
from config import CIRCLE_API_KEY, DEMO_MODE, PRICES
from payments.circle_client import fire_nanopayment, redeem_usyc_to_usdc


# ── x402 Constants ────────────────────────────────────────────────────────────
X402_VERSION      = "1.0"
X402_CHAIN        = "arc-testnet"
X402_CURRENCY     = "USDC"
X402_FACILITATOR  = "https://x402.circle.com/verify"   # Circle x402 facilitator
PAYMENT_HEADER    = "X-Payment"
RECEIPT_HEADER    = "X-Payment-Receipt"


# ── Payment receipt store (in-memory; use Redis in production) ────────────────
_used_receipts: set[str] = set()


def build_payment_requirement(price_usdc: float, resource: str, wallet_address: str) -> dict:
    """
    Build the 402 Payment Required response body.
    Tells the client exactly how much to pay and where.
    """
    nonce = uuid.uuid4().hex
    return {
        "x402Version": X402_VERSION,
        "accepts": [
            {
                "scheme":    "exact",
                "network":   X402_CHAIN,
                "maxAmount": str(int(price_usdc * 1_000_000)),   # USDC has 6 decimals
                "resource":  resource,
                "address":   wallet_address,
                "currency":  X402_CURRENCY,
                "nonce":     nonce,
                "expiresAt": int(time.time()) + 300,             # 5-minute window
            }
        ],
        "error": "Payment required to access this resource",
    }


def verify_payment_header(payment_header: str, expected_amount: float, wallet_address: str) -> dict:
    """
    Verify an x402 payment header.
    In live mode: calls the Circle x402 facilitator.
    In demo mode: simulates verification.
    Returns {"valid": bool, "tx_hash": str, "amount": float}
    """
    if DEMO_MODE:
        return _mock_verify(payment_header, expected_amount)

    try:
        r = requests.post(
            X402_FACILITATOR,
            json={
                "paymentHeader": payment_header,
                "expectedAmount": str(int(expected_amount * 1_000_000)),
                "recipientAddress": wallet_address,
                "network": X402_CHAIN,
            },
            headers={"Authorization": f"Bearer {CIRCLE_API_KEY}"},
            timeout=5,
        )
        data = r.json()
        return {
            "valid":   data.get("valid", False),
            "tx_hash": data.get("transactionHash", ""),
            "amount":  float(data.get("amount", 0)) / 1_000_000,
        }
    except Exception as exc:
        return {"valid": False, "tx_hash": "", "error": str(exc)}


def _mock_verify(payment_header: str, expected_amount: float) -> dict:
    """Demo mode verification — always passes if header looks valid."""
    if not payment_header or len(payment_header) < 10:
        return {"valid": False, "tx_hash": "", "error": "Missing payment header"}

    # Prevent replay attacks even in demo mode
    receipt_id = hashlib.sha256(payment_header.encode()).hexdigest()
    if receipt_id in _used_receipts:
        return {"valid": False, "tx_hash": "", "error": "Payment receipt already used"}

    _used_receipts.add(receipt_id)
    return {
        "valid":   True,
        "tx_hash": "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:28],
        "amount":  expected_amount,
    }


def build_payment_header(tx_hash: str, amount: float, nonce: str) -> str:
    """
    Build the X-Payment header an agent sends after paying.
    Format: base64-encoded JSON with tx proof.
    """
    import base64
    payload = json.dumps({
        "txHash":  tx_hash,
        "amount":  str(int(amount * 1_000_000)),
        "nonce":   nonce,
        "chain":   X402_CHAIN,
        "version": X402_VERSION,
    })
    return base64.b64encode(payload.encode()).decode()


# ── Flask decorator ───────────────────────────────────────────────────────────

def x402_required(action: str, wallet_address: str = "0xAgentFloatTreasury"):
    """
    Decorator that enforces x402 payment on a Flask route.

    Usage:
        @app.route("/api/agent/research")
        @x402_required("web_search")
        def research_endpoint():
            ...

    Flow:
        1. Request arrives without X-Payment header
           -> Return 402 with payment instructions
        2. Agent pays via nanopayment, retries with X-Payment header
           -> Verify payment, serve response + receipt header
    """
    price = PRICES.get(action, 0.001)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            payment_header = request.headers.get(PAYMENT_HEADER)

            if not payment_header:
                # Step 1: return 402 with payment requirement
                requirement = build_payment_requirement(price, f"/api/agent/{action}", wallet_address)
                resp = jsonify(requirement)
                resp.status_code = 402
                resp.headers["X-402-Version"]  = X402_VERSION
                resp.headers["Content-Type"]   = "application/json"
                return resp

            # Step 2: verify payment and serve
            verification = verify_payment_header(payment_header, price, wallet_address)

            if not verification["valid"]:
                return jsonify({
                    "error":  "Invalid or expired payment",
                    "detail": verification.get("error", "Verification failed"),
                }), 402

            # Payment verified — execute the route and attach receipt
            response = fn(*args, **kwargs)
            if hasattr(response, "headers"):
                response.headers[RECEIPT_HEADER] = json.dumps({
                    "txHash":  verification["tx_hash"],
                    "amount":  price,
                    "action":  action,
                    "chain":   X402_CHAIN,
                    "settled": True,
                })
            return response

        return wrapper
    return decorator


# ── Agent-side x402 client ────────────────────────────────────────────────────

class X402Client:
    """
    HTTP client that handles x402 payment flows automatically.
    An agent uses this to call any x402-protected endpoint.
    It pays, retries, and returns the resource transparently.
    """

    def __init__(self, wallet_id: str, wallet_address: str, treasury):
        self.wallet_id      = wallet_id
        self.wallet_address = wallet_address
        self.treasury       = treasury
        self.total_spent    = 0.0
        self.tx_log         = []

    def get(self, url: str, **kwargs) -> dict:
        """GET request with automatic x402 payment handling."""
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> dict:
        """POST request with automatic x402 payment handling."""
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        if DEMO_MODE:
            return self._demo_request(url, kwargs.get("action", "web_search"))

        try:
            # First attempt — no payment header
            r = requests.request(method, url, timeout=10, **kwargs)

            if r.status_code != 402:
                return {"status": r.status_code, "body": r.json(), "paid": False}

            # Got 402 — extract payment requirement
            req_body = r.json()
            accepts  = req_body.get("accepts", [{}])[0]
            amount   = int(accepts.get("maxAmount", 1000)) / 1_000_000
            nonce    = accepts.get("nonce", uuid.uuid4().hex)
            address  = accepts.get("address", "0xTreasury")

            # Pay via USYC -> USDC -> nanopayment
            self.treasury.redeem_for_payment(amount)
            tx = fire_nanopayment(self.wallet_id, address, amount, f"x402:{url}")
            self.treasury.debit_usdc(amount)
            self.total_spent += amount
            self.tx_log.append(tx)

            # Retry with payment header
            payment_hdr = build_payment_header(tx["tx_hash"], amount, nonce)
            headers = kwargs.pop("headers", {})
            headers[PAYMENT_HEADER] = payment_hdr

            r2 = requests.request(method, url, headers=headers, timeout=10, **kwargs)
            return {
                "status":  r2.status_code,
                "body":    r2.json() if r2.headers.get("content-type", "").startswith("application/json") else r2.text,
                "paid":    True,
                "tx_hash": tx["tx_hash"],
                "amount":  amount,
                "receipt": r2.headers.get(RECEIPT_HEADER, ""),
            }

        except Exception as exc:
            return {"status": 0, "error": str(exc), "paid": False}

    def _demo_request(self, url: str, action: str = "web_search") -> dict:
        """Simulate a full x402 request/pay/retry cycle."""
        amount = PRICES.get(action, 0.001)
        nonce  = uuid.uuid4().hex

        # Simulate payment
        self.treasury.redeem_for_payment(amount)
        tx = fire_nanopayment(self.wallet_id, "0xX402Endpoint", amount, f"x402:{action}")
        self.treasury.debit_usdc(amount)
        self.total_spent += amount
        self.tx_log.append(tx)

        payment_hdr = build_payment_header(tx["tx_hash"], amount, nonce)

        return {
            "status":  200,
            "paid":    True,
            "tx_hash": tx["tx_hash"],
            "amount":  amount,
            "receipt": f"settled:{tx['tx_hash'][:16]}",
            "body":    {"resource": url, "action": action, "result": "x402 payment verified"},
        }
