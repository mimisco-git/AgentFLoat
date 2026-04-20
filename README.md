# AgentFloat
### *The Agent Economy That Pays for Itself*

> Built for the **Agentic Economy on Arc** hackathon — lablab.ai × Arc × Circle  
> Track: **Agent-to-Agent Payment Loop**

---

## What It Does

AgentFloat is a decentralized AI agent pipeline where every micro-action is settled in sub-cent USDC on Arc, and all idle agent capital earns US Treasury yield via USYC.

A user submits a complex task. An orchestrator agent decomposes it and hires three specialist agents: Researcher, Analyst, and Writer. Every micro-action between agents triggers a nanopayment on Arc, settled in under a second. All agent capital sits in USYC between tasks, earning T-bill yield automatically. When a payment fires, USYC redeems to USDC in one block.

**The result:** an agent economy that partially pays for itself through yield on idle capital.

---

## Mandatory Requirements Met

| Requirement | How |
|---|---|
| Per-action pricing under $0.01 | Actions priced $0.0005–$0.0025 USDC |
| 50+ onchain transactions in demo | One research task generates 80–120 payments |
| Margin explanation | Ethereum gas: $2–5 per tx. Arc: <$0.0001. Sub-cent model is mathematically impossible on conventional chains. Arc's USDC-native gas is the only infrastructure where this works. |

---

## Architecture

```
User Task
    │
    ▼
Orchestrator Agent (Circle Wallet + USYC Treasury)
    │   Plans task via Claude API
    │   Pays specialist per action via Arc Nanopayments
    ├──► Researcher Agent  ──► web_search / data_extraction / fact_check
    ├──► Analyst Agent     ──► analyze / summarize
    └──► Writer Agent      ──► write_paragraph / compile_report

All payments:
  USYC (earning yield) ──► redeem to USDC ──► nanopayment on Arc ──► tx hash
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Settlement | Arc (EVM-compatible L1) |
| Payment currency | USDC (native Arc gas token) |
| Micropayments | Circle Nanopayments |
| Wallets | Circle Developer-Controlled Wallets |
| Yield layer | USYC (Circle tokenized T-bill fund) |
| Agent intelligence | Anthropic Claude API (claude-sonnet-4) |
| Backend | Python + Flask + Flask-SocketIO |
| Frontend | Vanilla HTML/CSS/JS, deployed on Vercel |
| Payment standard | x402 (agent HTTP payment wrapping) |

---

## USYC Yield Model

Every agent holds USYC as its working capital reserve:
- USYC earns ~4.75% APY on US Treasury bills automatically
- When a nanopayment is triggered: USYC redeems to USDC in one block on Arc
- At scale: if the agent pool holds $100,000 USDC in reserve, yield covers ~$4,750/year of operational cost
- This is the first agent network with a built-in financial subsidy from idle capital

---

## Setup

### Prerequisites
- Python 3.11+
- Circle Developer Account (developers.circle.com)
- Anthropic API Key (console.anthropic.com)
- Arc Testnet access + funded USDC wallet

### Install

```bash
git clone https://github.com/busybrain-labs/agentfloat
cd agentfloat/backend
pip install -r requirements.txt
```

### Configure

```bash
cp ../.env.example .env
# Edit .env with your API keys
```

### Run

```bash
python app.py
# Open http://localhost:8000
```

### Demo Mode
If no API keys are provided, AgentFloat runs in **DEMO MODE** automatically.
All agent actions and transactions are simulated with realistic data.
The full UI is functional. Switch to LIVE MODE by adding your API keys.

---

## Judging Criteria Alignment

**Presentation:** Live dashboard with real-time transaction feed, agent status indicators, cost counter, and yield counter. One glance tells the whole story.

**Business value:** Yield on idle capital subsidises operational costs. At $10M in agent pool reserves, yield covers $475,000/year in pipeline costs. The larger the agent economy grows, the more it subsidises itself.

**Application of technology:** Arc for settlement, Circle Nanopayments for per-action pricing, Circle Wallets for agent identity, USYC for treasury yield, Claude for intelligence, x402 for payment-gated HTTP.

**Originality:** No one has built yield-bearing agent treasuries before. USYC as an agent savings account is a genuinely new primitive.

---

## Team

**BusyBrain Labs**  
Builders at the intersection of AI orchestration and onchain finance.

---

## License
MIT
