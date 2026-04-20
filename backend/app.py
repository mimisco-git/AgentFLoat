"""
app.py — AgentFloat main server
Arc + Circle Nanopayments + x402 + ERC-8004 + USYC + AIsa
"""

import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from config import DEMO_MODE, PRICES
from payments.circle_client import create_wallet
from payments.usyc_treasury import AgentTreasury, TreasuryPool
from payments.x402 import x402_required, build_payment_requirement
from payments.erc8004 import registry
from agents.orchestrator import Orchestrator
from agents.specialists import build_specialist

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["SECRET_KEY"] = "agentfloat-arc-2026"
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

AGENTS       = {}
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
        # Register ERC-8004 identity on Arc
        registry.register(
            agent_id=aid,
            display_name=label,
            role=aid,
            wallet_address=wallet["address"],
        )
    print(f"[AgentFloat] Pool ready. DEMO_MODE={DEMO_MODE}")
    for aid, a in AGENTS.items():
        identity = registry.get(aid)
        print(f"  {aid}: {a['wallet']['wallet_id']}  erc8004={identity.erc8004_token[:18]}...")


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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("../frontend", "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "mode":    "demo" if DEMO_MODE else "live",
        "agents":  [
            {
                "id":       aid,
                "wallet":   a["wallet"]["wallet_id"],
                "address":  a["wallet"]["address"],
                "treasury": a["treasury"].snapshot(),
                "erc8004":  registry.get(aid).to_dict() if registry.get(aid) else {},
            }
            for aid, a in AGENTS.items()
        ],
        "prices":  PRICES,
        "yield": {
            "total_earned": round(TREASURY_POOL.total_yield(), 8),
            "total_paid":   round(TREASURY_POOL.total_paid(), 6),
        },
    })


@app.route("/api/trust")
def trust_leaderboard():
    """ERC-8004 agent trust leaderboard."""
    return jsonify({
        "leaderboard": registry.leaderboard(),
        "standard":    "ERC-8004",
        "chain":       "Arc Testnet",
    })


@app.route("/api/prices")
def prices():
    return jsonify(PRICES)


# ── x402-protected agent endpoints ───────────────────────────────────────────

@app.route("/api/agent/web_search", methods=["GET", "POST"])
@x402_required("web_search", "0xAgentFloatTreasury")
def agent_web_search():
    """x402-gated web search endpoint. Agents pay $0.001 USDC per call."""
    query = request.args.get("q", request.json.get("q", "") if request.is_json else "")
    return jsonify({"endpoint": "web_search", "query": query, "result": "Data returned", "chain": "Arc", "standard": "x402"})


@app.route("/api/agent/analyze", methods=["GET", "POST"])
@x402_required("analyze", "0xAgentFloatTreasury")
def agent_analyze():
    """x402-gated analysis endpoint. Agents pay $0.0015 USDC per call."""
    return jsonify({"endpoint": "analyze", "result": "Analysis complete", "chain": "Arc", "standard": "x402"})


@app.route("/api/agent/write", methods=["GET", "POST"])
@x402_required("write_paragraph", "0xAgentFloatTreasury")
def agent_write():
    """x402-gated writing endpoint. Agents pay $0.002 USDC per call."""
    return jsonify({"endpoint": "write_paragraph", "result": "Content generated", "chain": "Arc", "standard": "x402"})


# ── Pipeline run ──────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def run_task():
    body = request.get_json(silent=True) or {}
    task = body.get("task", "").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    sid = body.get("sid", "")

    def emit_fn(event, data):
        socketio.emit(event, data, room=sid) if sid else socketio.emit(event, data)

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


# ── Sockets ───────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("connected", {"sid": request.sid, "mode": "demo" if DEMO_MODE else "live"})


if __name__ == "__main__":
    init_agent_pool()
    threading.Thread(target=yield_ticker, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)
