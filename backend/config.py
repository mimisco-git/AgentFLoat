import os
from dotenv import load_dotenv

load_dotenv()

# ── AI Provider (Anthropic or Groq) ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

# Use Groq if no Anthropic key
USE_GROQ = bool(GROQ_API_KEY) and not bool(ANTHROPIC_API_KEY)
AI_KEY   = GROQ_API_KEY if USE_GROQ else ANTHROPIC_API_KEY

# ── Circle ────────────────────────────────────────────────────────────────────
CIRCLE_API_KEY        = os.getenv("CIRCLE_API_KEY", "")
CIRCLE_ENV            = os.getenv("CIRCLE_ENV", "sandbox")
CIRCLE_BASE_URL       = "https://api-sandbox.circle.com" if CIRCLE_ENV == "sandbox" else "https://api.circle.com"
NANOPAYMENTS_BASE_URL = os.getenv("NANOPAYMENTS_BASE_URL", "https://nanopayments-sandbox.circle.com")

# ── Arc ───────────────────────────────────────────────────────────────────────
ARC_RPC_URL  = os.getenv("ARC_RPC_URL", "https://rpc-testnet.arc.net")
ARC_CHAIN_ID = int(os.getenv("ARC_CHAIN_ID", "1214"))
USDC_CONTRACT = os.getenv("USDC_CONTRACT", "0xUSDC_CONTRACT_ADDRESS")

# ── Agent pricing (in USDC) ───────────────────────────────────────────────────
PRICES = {
    "web_search":      0.0010,
    "data_extraction": 0.0005,
    "summarize":       0.0008,
    "analyze":         0.0015,
    "write_paragraph": 0.0020,
    "compile_report":  0.0025,
    "fact_check":      0.0007,
}

# ── USYC yield ────────────────────────────────────────────────────────────────
USYC_APY             = 0.0475
USYC_RATE_PER_SECOND = USYC_APY / (365 * 24 * 3600)

# ── Demo mode ─────────────────────────────────────────────────────────────────
DEMO_MODE = not bool(AI_KEY and CIRCLE_API_KEY)

print(f"[Config] USE_GROQ={USE_GROQ} | DEMO_MODE={DEMO_MODE} | CIRCLE={'yes' if CIRCLE_API_KEY else 'no'}")
