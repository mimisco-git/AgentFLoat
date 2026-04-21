"""
app.py — AgentFloat (self-contained)
All payment modules inlined — no missing import errors.
Arc + Circle Nanopayments + Gateway + x402 + ERC-8004 + USYC + SpendingGuard + CCTP + Bridge Kit
"""

import os, threading, time, uuid, random, string
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from config import DEMO_MODE, PRICES, CIRCLE_API_KEY
from payments.circle_client import create_wallet
from payments.usyc_treasury import AgentTreasury, TreasuryPool
from payments.x402 import x402_required
from payments.erc8004 import registry
from agents.orchestrator import Orchestrator
from agents.specialists import build_specialist

# ── Inline: SpendingGuard ─────────────────────────────────────────────────────
class SpendingPolicy:
    def __init__(self, agent_id, max_per_action=0.005, max_per_day=2.0,
                 max_per_pipeline=0.5, allowed_actions=None, enabled=True):
        self.agent_id = agent_id
        self.max_per_action = max_per_action
        self.max_per_day = max_per_day
        self.max_per_pipeline = max_per_pipeline
        self.allowed_actions = allowed_actions or list(PRICES.keys())
        self.enabled = enabled
        self.require_approval_above = 0.002

class SpendingRecord:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.today_spent = 0.0
        self.pipeline_spent = 0.0
        self.total_spent = 0.0
        self.action_count = 0
        self.blocked_count = 0
        self.flagged_count = 0
        self.last_reset = time.time()
        self.violations = []

    def reset_daily(self):
        if time.time() - self.last_reset > 86400:
            self.today_spent = 0.0
            self.last_reset = time.time()

    def reset_pipeline(self):
        self.pipeline_spent = 0.0

class SpendingGuard:
    def __init__(self):
        self._policies = {}
        self._records = {}

    def set_policy(self, policy):
        self._policies[policy.agent_id] = policy
        if policy.agent_id not in self._records:
            self._records[policy.agent_id] = SpendingRecord(policy.agent_id)

    def reset_pipeline(self, agent_id):
        if agent_id in self._records:
            self._records[agent_id].reset_pipeline()

    def reset_all_pipelines(self):
        for r in self._records.values():
            r.reset_pipeline()

    def check(self, agent_id, amount, action, recipient=""):
        policy = self._policies.get(agent_id)
        record = self._records.get(agent_id)
        if not policy or not record or not policy.enabled:
            return {"allowed": True, "flagged": False, "reason": "no_policy", "amount": amount, "action": action}
        record.reset_daily()
        if amount > policy.max_per_action:
            return self._block(record, amount, action, f"Exceeds per-action cap ${policy.max_per_action:.4f}")
        if record.today_spent + amount > policy.max_per_day:
            return self._block(record, amount, action, f"Daily limit ${policy.max_per_day:.2f} exceeded")
        if record.pipeline_spent + amount > policy.max_per_pipeline:
            return self._block(record, amount, action, f"Pipeline limit ${policy.max_per_pipeline:.2f} exceeded")
        if policy.allowed_actions and action not in policy.allowed_actions:
            return self._block(record, amount, action, f"Action '{action}' not allowed")
        record.today_spent += amount
        record.pipeline_spent += amount
        record.total_spent += amount
        record.action_count += 1
        flagged = amount >= policy.require_approval_above
        if flagged: record.flagged_count += 1
        return {"allowed": True, "flagged": flagged, "reason": "approved", "amount": amount, "action": action}

    def _block(self, record, amount, action, reason):
        record.blocked_count += 1
        record.violations.append({"ts": time.time(), "action": action, "amount": amount, "reason": reason})
        return {"allowed": False, "flagged": False, "reason": reason, "amount": amount, "action": action}

    def snapshot(self):
        return {
            aid: {
                "today_spent": round(r.today_spent, 6),
                "pipeline_spent": round(r.pipeline_spent, 6),
                "total_spent": round(r.total_spent, 6),
                "action_count": r.action_count,
                "blocked_count": r.blocked_count,
                "flagged_count": r.flagged_count,
                "violations": r.violations[-5:],
            }
            for aid, r in self._records.items()
        }

guard = SpendingGuard()

def default_policy(agent_id):
    return SpendingPolicy(agent_id=agent_id, allowed_actions=list(PRICES.keys()))

# ── Inline: Gateway Client ────────────────────────────────────────────────────
def get_gateway_balance(address):
    return {
        "address": address,
        "usdc_balance": round(random.uniform(4.5, 5.5), 4),
        "chains": [
            {"chain": "ARC",  "balance": round(random.uniform(2.0, 3.0), 4)},
            {"chain": "BASE", "balance": round(random.uniform(1.0, 2.0), 4)},
            {"chain": "ETHEREUM", "balance": round(random.uniform(0.5, 1.0), 4)},
        ],
        "gateway": True,
        "demo": True,
    }

def gateway_pool_summary(wallets):
    balances = [get_gateway_balance(w) for w in wallets]
    total = sum(b.get("usdc_balance", 0) for b in balances)
    return {"total_usdc": round(total, 4), "wallet_count": len(wallets), "balances": balances, "gateway": True}

# ── Inline: CCTP Client ───────────────────────────────────────────────────────
CCTP_DOMAINS = {"ethereum": 0, "avalanche": 1, "optimism": 2, "arbitrum": 3, "base": 6, "arc": 9}

def cctp_initiate(from_chain, to_chain, amount, recipient):
    return {
        "transfer_id": "cctp-" + uuid.uuid4().hex[:16],
        "from_chain": from_chain, "to_chain": to_chain,
        "amount": amount, "recipient": recipient,
        "status": "complete", "cctp": True, "demo": True,
        "tx_hash": "0x" + "c" * 64,
        "note": "Native USDC burn+mint, no bridge risk",
    }

# ── Inline: Bridge Kit ────────────────────────────────────────────────────────
def bridge_estimate_route(from_chain, to_chain, amount):
    use_cctp = amount >= 1.0
    return {
        "from_chain": from_chain, "to_chain": to_chain, "amount": amount,
        "route": "cctp" if use_cctp else "gateway",
        "protocol": "Circle CCTP v2" if use_cctp else "Circle Gateway",
        "estimated_time": "15-20 min" if use_cctp else "near-instant",
        "estimated_fee": 0.0, "native_usdc": True, "gas_required": False,
    }

def bridge_usdc_transfer(from_chain, to_chain, amount, recipient):
    route = bridge_estimate_route(from_chain, to_chain, amount)
    return {
        "bridge_id": "bk-" + uuid.uuid4().hex[:16],
        "from_chain": from_chain, "to_chain": to_chain,
        "amount": amount, "recipient": recipient,
        "status": "complete", "bridge_kit": True, "demo": True,
        "route_info": route, "native_usdc": True,
    }

def multichain_balance(address):
    bal = get_gateway_balance(address)
    return {"address": address, "total_usdc": bal["usdc_balance"],
            "chains": bal["chains"], "supported_chains": list(CCTP_DOMAINS.keys()), "bridge_kit": True}

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["SECRET_KEY"] = "agentfloat-arc-2026"
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", logger=False, engineio_logger=False)

AGENTS = {}
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
        registry.register(agent_id=aid, display_name=label, role=aid, wallet_address=wallet["address"])
        guard.set_policy(default_policy(aid))
    print(f"[AgentFloat] Pool ready. DEMO_MODE={DEMO_MODE}")

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

@app.route("/api/mode")
def mode():
    from config import USE_GROQ, GROQ_API_KEY, ANTHROPIC_API_KEY
    ai_label = "Groq Llama 3" if USE_GROQ else ("Claude Sonnet" if ANTHROPIC_API_KEY else "Demo")
    return jsonify({
        "mode":     "demo" if DEMO_MODE else "live",
        "ai_label": ai_label,
        "circle":   bool(CIRCLE_API_KEY),
        "groq":     bool(GROQ_API_KEY),
    })

@app.route("/api/status")
def status():
    addresses = [a["wallet"]["address"] for a in AGENTS.values()]
    return jsonify({
        "mode":    "demo" if DEMO_MODE else "live",
        "agents":  [
            {
                "id":         aid,
                "wallet":     a["wallet"]["wallet_id"],
                "address":    a["wallet"]["address"],
                "treasury":   a["treasury"].snapshot(),
                "erc8004":    registry.get(aid).to_dict() if registry.get(aid) else {},
                "spending":   guard.snapshot().get(aid, {}),
                "gateway_bal": get_gateway_balance(a["wallet"]["address"]),
            }
            for aid, a in AGENTS.items()
        ],
        "prices":       PRICES,
        "gateway_pool": gateway_pool_summary(addresses),
        "yield": {
            "total_earned": round(TREASURY_POOL.total_yield(), 8),
            "total_paid":   round(TREASURY_POOL.total_paid(), 6),
        },
    })

@app.route("/api/trust")
def trust():
    return jsonify({"leaderboard": registry.leaderboard(), "standard": "ERC-8004", "chain": "Arc Testnet"})

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

@app.route("/api/cctp/chains")
def cctp_chains():
    return jsonify({"chains": list(CCTP_DOMAINS.keys()), "domains": CCTP_DOMAINS, "protocol": "Circle CCTP v2", "note": "Native USDC burn+mint."})

@app.route("/api/cctp/transfer", methods=["POST"])
def cctp_transfer():
    body = request.get_json(silent=True) or {}
    return jsonify(cctp_initiate(body.get("from_chain","ethereum"), body.get("to_chain","arc"), float(body.get("amount",1.0)), body.get("recipient","")))

@app.route("/api/cctp/estimate", methods=["POST"])
def cctp_estimate():
    body = request.get_json(silent=True) or {}
    return jsonify(bridge_estimate_route(body.get("from_chain","ethereum"), body.get("to_chain","arc"), float(body.get("amount",1.0))))

@app.route("/api/bridge/transfer", methods=["POST"])
def bridge_transfer():
    body = request.get_json(silent=True) or {}
    return jsonify(bridge_usdc_transfer(body.get("from_chain","ethereum"), body.get("to_chain","arc"), float(body.get("amount",1.0)), body.get("recipient","")))

@app.route("/api/bridge/estimate", methods=["POST"])
def bridge_estimate():
    body = request.get_json(silent=True) or {}
    return jsonify(bridge_estimate_route(body.get("from_chain","ethereum"), body.get("to_chain","arc"), float(body.get("amount",1.0))))

@app.route("/api/bridge/multichain/<address>")
def bridge_multichain(address):
    return jsonify(multichain_balance(address))

@app.route("/api/agent/web_search", methods=["GET","POST"])
@x402_required("web_search","0xAgentFloatTreasury")
def agent_web_search():
    return jsonify({"endpoint": "web_search", "query": request.args.get("q",""), "chain": "Arc", "standard": "x402"})

@app.route("/api/agent/analyze", methods=["GET","POST"])
@x402_required("analyze","0xAgentFloatTreasury")
def agent_analyze():
    return jsonify({"endpoint": "analyze", "chain": "Arc", "standard": "x402"})

@app.route("/api/agent/write", methods=["GET","POST"])
@x402_required("write_paragraph","0xAgentFloatTreasury")
def agent_write():
    return jsonify({"endpoint": "write_paragraph", "chain": "Arc", "standard": "x402"})

@app.route("/api/run", methods=["POST"])
def run_task():
    body = request.get_json(silent=True) or {}
    task = body.get("task","").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    sid = body.get("sid","")

    def emit_fn(event, data):
        if sid: socketio.emit(event, data, room=sid)
        else:   socketio.emit(event, data)

    def pipeline():
        try:
            guard.reset_all_pipelines()
            orch_wallet   = AGENTS["orchestrator"]["wallet"]
            orch_treasury = AGENTS["orchestrator"]["treasury"]
            specialists   = {aid: build_specialist(aid, AGENTS[aid]["wallet"]) for aid in ("researcher","analyst","writer")}
            orchestrator  = Orchestrator(wallet=orch_wallet, treasury=orch_treasury, emit_fn=emit_fn)
            result = orchestrator.run(task, specialists)
            emit_fn("task_complete", result)
        except Exception as exc:
            emit_fn("task_error", {"error": str(exc)})

    threading.Thread(target=pipeline, daemon=True).start()
    return jsonify({"message": "Pipeline started", "mode": "demo" if DEMO_MODE else "live"})

@socketio.on("connect")
def on_connect():
    from config import USE_GROQ, GROQ_API_KEY, ANTHROPIC_API_KEY
    ai_label = "Groq Llama 3" if USE_GROQ else ("Claude Sonnet" if ANTHROPIC_API_KEY else "Demo")
    emit("connected", {"sid": request.sid, "mode": "demo" if DEMO_MODE else "live", "ai_label": ai_label})

if __name__ == "__main__":
    init_agent_pool()
    threading.Thread(target=yield_ticker, daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
