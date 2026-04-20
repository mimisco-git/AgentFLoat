<div align="center">

<img src="docs/agentfloat_logo.svg" alt="AgentFloat" width="320"/>

### The Agent Economy That Pays for Itself

[![Arc](https://img.shields.io/badge/Arc-L1%20Settlement-00C27C?style=flat-square)](https://arc.net)
[![Circle](https://img.shields.io/badge/Circle-Nanopayments-2563EB?style=flat-square)](https://developers.circle.com)
[![USYC](https://img.shields.io/badge/USYC-4.75%25%20APY-F59E0B?style=flat-square)](https://circle.com/usyc)
[![x402](https://img.shields.io/badge/x402-Payment%20Standard-7C3AED?style=flat-square)](https://x402.org)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-Agent%20Trust-0A1628?style=flat-square)](https://eips.ethereum.org)
[![License](https://img.shields.io/badge/license-MIT-94A3B8?style=flat-square)](LICENSE)

**Built for the lablab.ai x Arc x Circle Hackathon — April 2026**
Track: **Agent-to-Agent Payment Loop** · Team: **BusyBrain Labs**

</div>

---

## What Is AgentFloat?

AgentFloat is a decentralized AI agent pipeline where every micro-action is settled in sub-cent USDC on Arc, idle capital earns US Treasury yield via USYC, and all payments use the x402 web-native standard — so the agent economy pays for itself.

A user submits a complex task. An orchestrator agent decomposes it using Claude and hires three specialist agents: Researcher, Analyst, and Writer. Every micro-action triggers a nanopayment via x402 on Arc, settled in under a second. All agent capital sits in USYC between tasks, earning T-bill yield automatically. Agent identities are registered and verified on ERC-8004.

---

## Architecture

```
User Task
    │
    ▼
Orchestrator Agent (ERC-8004 verified · USYC treasury · Claude API)
    │
    ├── x402 payment → Researcher ──► AIsa web_search     $0.0010
    │                            ──► AIsa data_extraction $0.0005
    │                            ──► AIsa fact_check      $0.0007
    │
    ├── x402 payment → Analyst ───► analyze               $0.0015
    │                          ──► summarize              $0.0008
    │
    └── x402 payment → Writer ────► write_paragraph       $0.0020
                                ──► compile_report        $0.0025

Payment flow per action:
  USYC (earning yield) → redeem USDC (1 block Arc) → x402 fires → Arc settles <1 sec → ERC-8004 updated
```

---

## Mandatory Requirements Met

| Requirement | How |
|---|---|
| Per-action pricing ≤ $0.01 | All actions $0.0005–$0.0025 via x402 |
| 50+ onchain transactions | One pipeline = 80–120 Arc transactions |
| Margin explanation | Ethereum gas $2–5/tx · Arc <$0.0001/tx · 20,000x difference. Sub-cent model impossible without Arc. |

---

## Technology Stack

**Required:** Arc L1, USDC, Circle Nanopayments

**Recommended:** Circle Wallets, Circle Gateway, x402 Standard, USYC

**Added:** ERC-8004 Agent Trust, AIsa Paid Data Endpoints, Anthropic Claude, Flask + SocketIO, Vercel

---

## The USYC Yield Model

Every agent holds USYC as its working capital. USYC earns ~4.75% APY on US Treasury bills while the agent is idle. When a payment fires, USYC redeems to USDC in one block on Arc. At $1M in pool reserves, yield covers ~950,000 pipeline runs per year. The larger the network, the cheaper it becomes to run.

---

## Setup

```bash
git clone https://github.com/mimisco-git/AgentFloat
cd AgentFloat/backend
pip install -r requirements.txt
cp ../.env.example .env
# Add ANTHROPIC_API_KEY and CIRCLE_API_KEY to .env
python app.py
# Open http://localhost:8000
```

**Demo Mode:** Without API keys the app runs fully in demo mode with simulated transactions, realistic yield data, and all UI features active.

---

## Project Structure

```
AgentFloat/
├── backend/
│   ├── app.py                 Flask + Socket.IO + x402 routes
│   ├── config.py              Pricing + environment config
│   ├── agents/
│   │   ├── orchestrator.py    Master agent (Claude + ERC-8004)
│   │   └── specialists.py     Researcher / Analyst / Writer
│   └── payments/
│       ├── circle_client.py   Circle Wallets + nanopayments
│       ├── usyc_treasury.py   Real-time yield accrual engine
│       ├── x402.py            x402 HTTP payment middleware
│       ├── aisa_client.py     AIsa paid data API client
│       └── erc8004.py         ERC-8004 agent trust registry
├── frontend/
│   └── index.html             Animated dashboard
├── docs/
│   ├── agentfloat_logo.svg
│   ├── agentfloat_icon.svg
│   └── agentfloat_logo_dark.svg
├── vercel.json
└── .env.example
```

---

## Business Model

| Stream | Model |
|---|---|
| Platform fee | 0.1% on every nanopayment processed |
| Yield spread | 10% of USYC yield retained |
| Enterprise SaaS | $499–$2,999/mo for custom agent pools |
| API Marketplace | Revenue share on x402-gated API calls |

TAM $50B+ · SAM $8.4B · SOM $420M · CAGR 34%

---

## Team

**BusyBrain Labs** — Building at the intersection of AI orchestration and onchain finance.

---

MIT License
