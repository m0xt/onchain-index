# Phase A has no Claude calls; Phase C composite-design will populate this.

# Anthropic pricing (USD per million tokens). Match the public pricing page.
MODEL_PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}

# One row per Claude call site. Tokens are estimates, refreshed by hand
# when prompts or cadence change materially.
COST_ESTIMATES: list[dict[str, object]] = []
