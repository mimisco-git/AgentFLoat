"""
app.py
AgentFloat: The Yield-Earning AI Workforce
Main Flask application with Socket.IO for real-time agent updates.
"""

import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from config import DEMO_MODE, PRICES
from payments.circle_client import create_wallet
from payments.usyc_treasury import AgentTreasury, TreasuryPool
from agents.orchestrator import Orchestrator
from agents.specialists import build_specialist

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["SECRET_KEY"] = "agentfloat-secret-2026"
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Global agent pool (initialised once on startup) ───────────────────────────
AGENTS = {}
TREASURY_POOL = TreasuryPool()


def init_agent_pool():
    global AGENTS
    agent_ids = ["orchestrator", "researcher", "analyst", "writer"]
    labels    = {
        "orchestrator": "AgentFloat Orchestrator",
        "researcher":   "AgentFloat Researcher",
        "analyst":      "AgentFloat Analyst",
        "writer":       "AgentFloat Writer",
    }
    for aid in agent_ids:
        wallet   = create_wallet(labels[aid])
        treasury = AgentTreasury(wallet_id=wallet["wallet_id"], initial_usyc=5.0)
        TREASURY_POOL.add(aid, treasury)
        AGENTS[aid] = {"wallet": wallet, "treasury": treasury}

    print(f"[AgentFloat] Pool ready. DEMO_MODE={DEMO_MODE}")
    for aid, a in AGENTS.items():
        print(f"  {aid}: wallet={a['wallet']['wallet_id']}  addr={a['wallet']['address']}")


# ── Background yield ticker ───────────────────────────────────────────────────
def yield_ticker():
    """Push yield updates to all connected clients every 2 seconds."""
    while True:
        time.sleep(2)
        try:
            socketio.emit("yield_update", {
                "total_yield":  round(TREASURY_POOL.total_yield(), 8),
                "total_paid":   round(TREASURY_POOL.total_paid(), 6),
                "agents":       TREASURY_POOL.snapshot_all(),
            })
        except Exception:
            pass


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("../frontend", "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "mode":    "demo" if DEMO_MODE else "live",
        "agents":  [
            {
                "id":      aid,
                "wallet":  a["wallet"]["wallet_id"],
                "address": a["wallet"]["address"],
                "treasury": a["treasury"].snapshot(),
            }
            for aid, a in AGENTS.items()
        ],
        "prices":  PRICES,
        "yield": {
            "total_earned": round(TREASURY_POOL.total_yield(), 8),
            "total_paid":   round(TREASURY_POOL.total_paid(), 6),
        },
    })


@app.route("/api/run", methods=["POST"])
def run_task():
    """
    Kick off an agent pipeline for a user task.
    Emits real-time Socket.IO events throughout execution.
    """
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

            specialists = {
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

    thread = threading.Thread(target=pipeline, daemon=True)
    thread.start()

    return jsonify({"message": "Pipeline started", "mode": "demo" if DEMO_MODE else "live"})


@app.route("/api/prices")
def prices():
    return jsonify(PRICES)


# ── Socket.IO events ──────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    print(f"[Socket] Client connected: {request.sid}")
    emit("connected", {"sid": request.sid, "mode": "demo" if DEMO_MODE else "live"})


@socketio.on("disconnect")
def on_disconnect():
    print(f"[Socket] Client disconnected: {request.sid}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_agent_pool()
    ticker = threading.Thread(target=yield_ticker, daemon=True)
    ticker.start()
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)
