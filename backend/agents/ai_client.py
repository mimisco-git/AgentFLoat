"""
ai_client.py
Unified AI client — uses Groq if GROQ_API_KEY is set, otherwise Anthropic.
Groq is free, Anthropic requires a paid key.
"""

from config import ANTHROPIC_API_KEY, GROQ_API_KEY, USE_GROQ, DEMO_MODE


def get_client():
    """Return the appropriate AI client."""
    if DEMO_MODE:
        return None
    if USE_GROQ:
        from groq import Groq
        return Groq(api_key=GROQ_API_KEY)
    else:
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def chat(client, system: str, user: str, max_tokens: int = 800) -> str:
    """Unified chat call — works with both Groq and Anthropic."""
    if client is None:
        return ""

    if USE_GROQ:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content

    else:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
