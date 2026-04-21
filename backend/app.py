"""
app.py — AgentFloat
Arc + Circle Nanopayments + Gateway + x402 + ERC-8004 + USYC + SpendingGuard + AIsa
"""

import os
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from config import DEMO_MODE, PRICES
from payments.circle_client import create_wallet
from payments.usyc_treasury import AgentTreasury, TreasuryPool
from payments.x402 import x402_required
from payments.erc8004 import registry
from payments.spending_guard import guard, default_policy
from payments.gateway_client import get_gateway_balance, gateway_pool_summary
from payments.cctp_client import initiate_transfer, get_attestation, CCTP_DOMAINS, rebalance_to_arc
from payments.bridge_kit import bridge_usdc, fund_agent_on_arc, multichain_balance, estimate_route
from agents.orchestrator import Orchestrator
from agents.specialists import build_specialist

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["SECRET_KEY"] = "agentfloat-arc-2026"
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(
    app, cors_allowed_origins="*",
    async_mode="threading",
    logger=False, engineio_logger=False,
)

AGENTS        = {}
TREASURY_POOL = TreasuryPool()


def init_agent_pool():
    global AGENTS
    configs = [
        ("orchestrator", "AgentFloat Orchestrator"),
        ("researcher",   "AgentFloat Researcher"),
        ("analyst",      "AgentFloat Analyst"),
        ("writer",       "AgentFloat Writer"),
    ]
    for aid, label in configs:
        wallet   = create_wallet(label)
        treasury = AgentTreasury(wallet_id=wallet["wallet_id"], initial_usyc=5.0)
        TREASURY_POOL.add(aid, treasury)
        AGENTS[aid] = {"wallet": wallet, "treasury": treasury}

        # Register ERC-8004 identity
        registry.register(
            agent_id=aid, display_name=label,
            role=aid, wallet_address=wallet["address"],
        )
        # Register spending policy
        guard.set_policy(default_policy(aid))

    print(f"[AgentFloat] Pool ready. DEMO_MODE={DEMO_MODE}")
    for aid, a in AGENTS.items():
        print(f"  {aid}: {a['wallet']['wallet_id']}")


def yield_ticker():
    while True:
        time.sleep(2)
        try:
            socketio.emit("yield_update", {
                "total_yield": round(TREASURY_POOL.total_yield(), 8),
                "total_paid":  round(TREASURY_POOL.total_paid(), 6),
                "agents":      TREASURY_POOL.snapshot_all(),
            })
        except Exception:
            pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("../frontend", "index.html")


@app.route("/api/status")
def status():
    addresses = [a["wallet"]["address"] for a in AGENTS.values()]
    gw_pool   = gateway_pool_summary(addresses)
    return jsonify({
        "mode":    "demo" if DEMO_MODE else "live",
        "agents":  [
            {
                "id":            aid,
                "wallet":        a["wallet"]["wallet_id"],
                "address":       a["wallet"]["address"],
                "treasury":      a["treasury"].snapshot(),
                "erc8004":       registry.get(aid).to_dict() if registry.get(aid) else {},
                "spending":      guard.snapshot().get(aid, {}),
                "gateway_bal":   get_gateway_balance(a["wallet"]["address"]),
            }
            for aid, a in AGENTS.items()
        ],
        "prices":      PRICES,
        "gateway_pool": gw_pool,
        "yield": {
            "total_earned": round(TREASURY_POOL.total_yield(), 8),
            "total_paid":   round(TREASURY_POOL.total_paid(), 6),
        },
    })


@app.route("/api/trust")
def trust():
    return jsonify({
        "leaderboard": registry.leaderboard(),
        "standard":    "ERC-8004",
        "chain":       "Arc Testnet",
    })


@app.route("/api/spending")
def spending():
    return jsonify({
        "guard_snapshot": guard.snapshot(),
        "policies": {
            aid: {
                "max_per_action":   p.max_per_action,
                "max_per_day":      p.max_per_day,
                "max_per_pipeline": p.max_per_pipeline,
                "allowed_actions":  p.allowed_actions,
                "enabled":          p.enabled,
            }
            for aid, p in guard._policies.items()
        },
    })


@app.route("/api/gateway")
def gateway():
    addresses = [a["wallet"]["address"] for a in AGENTS.values()]
    return jsonify(gateway_pool_summary(addresses))


@app.route("/api/cctp/estimate", methods=["POST"])
def cctp_estimate():
    """Estimate cross-chain transfer route and fees."""
    body = request.get_json(silent=True) or {}
    return jsonify(estimate_route(
        from_chain=body.get("from_chain", "ethereum"),
        to_chain=body.get("to_chain", "arc"),
        amount_usdc=float(body.get("amount", 1.0)),
    ))


@app.route("/api/cctp/transfer", methods=["POST"])
def cctp_transfer():
    """Initiate a CCTP cross-chain USDC transfer."""
    body = request.get_json(silent=True) or {}
    result = initiate_transfer(
        from_chain=body.get("from_chain", "ethereum"),
        to_chain=body.get("to_chain", "arc"),
        amount_usdc=float(body.get("amount", 1.0)),
        recipient=body.get("recipient", ""),
        wallet_id=body.get("wallet_id", ""),
    )
    return jsonify(result)


@app.route("/api/cctp/chains")
def cctp_chains():
    """List all CCTP-supported chains."""
    return jsonify({
        "chains":   list(CCTP_DOMAINS.keys()),
        "domains":  CCTP_DOMAINS,
        "protocol": "Circle CCTP v2",
        "note":     "Native USDC burn+mint. No wrapped tokens.",
    })


@app.route("/api/bridge/estimate", methods=["POST"])
def bridge_estimate():
    """Estimate Bridge Kit route (CCTP vs Gateway)."""
    body = request.get_json(silent=True) or {}
    return jsonify(estimate_route(
        from_chain=body.get("from_chain", "ethereum"),
        to_chain=body.get("to_chain", "arc"),
        amount_usdc=float(body.get("amount", 1.0)),
    ))


@app.route("/api/bridge/transfer", methods=["POST"])
def bridge_transfer():
    """Bridge USDC via optimal route (Bridge Kit)."""
    body = request.get_json(silent=True) or {}
    result = bridge_usdc(
        from_chain=body.get("from_chain", "ethereum"),
        to_chain=body.get("to_chain", "arc"),
        amount_usdc=float(body.get("amount", 1.0)),
        recipient=body.get("recipient", ""),
        wallet_id=body.get("wallet_id", ""),
    )
    return jsonify(result)


@app.route("/api/bridge/multichain/<address>")
def bridge_multichain(address):
    """Get multichain USDC balance for an address."""
    return jsonify(multichain_balance(address))


@app.route("/api/prices")
def prices():
    return jsonify(PRICES)


# x402-protected endpoints
@app.route("/api/agent/web_search", methods=["GET", "POST"])
@x402_required("web_search", "0xAgentFloatTreasury")
def agent_web_search():
    query = request.args.get("q", "")
    return jsonify({"endpoint": "web_search", "query": query, "chain": "Arc", "standard": "x402"})


@app.route("/api/agent/analyze", methods=["GET", "POST"])
@x402_required("analyze", "0xAgentFloatTreasury")
def agent_analyze():
    return jsonify({"endpoint": "analyze", "chain": "Arc", "standard": "x402"})


@app.route("/api/agent/write", methods=["GET", "POST"])
@x402_required("write_paragraph", "0xAgentFloatTreasury")
def agent_write():
    return jsonify({"endpoint": "write_paragraph", "chain": "Arc", "standard": "x402"})


# Pipeline
@app.route("/api/run", methods=["POST"])
def run_task():
    body = request.get_json(silent=True) or {}
    task = body.get("task", "").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    sid = body.get("sid", "")

    def emit_fn(event, data):
        if sid:
            socketio.emit(event, data, room=sid)
        else:
            socketio.emit(event, data)

    def pipeline():
        try:
            orch_wallet   = AGENTS["orchestrator"]["wallet"]
            orch_treasury = AGENTS["orchestrator"]["treasury"]
            specialists   = {
                aid: build_specialist(aid, AGENTS[aid]["wallet"])
                for aid in ("researcher", "analyst", "writer")
            }
            orchestrator = Orchestrator(
                wallet=orch_wallet,
                treasury=orch_treasury,
                emit_fn=emit_fn,
            )
            result = orchestrator.run(task, specialists)
            emit_fn("task_complete", result)
        except Exception as exc:
            emit_fn("task_error", {"error": str(exc)})

    threading.Thread(target=pipeline, daemon=True).start()
    return jsonify({"message": "Pipeline started", "mode": "demo" if DEMO_MODE else "live"})


@socketio.on("connect")
def on_connect():
    emit("connected", {"sid": request.sid, "mode": "demo" if DEMO_MODE else "live"})


if __name__ == "__main__":
    init_agent_pool()
    threading.Thread(target=yield_ticker, daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
