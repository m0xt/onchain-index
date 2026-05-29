# Anthropic pricing (USD per million tokens). Match the public pricing page.
MODEL_PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}

# One row per Claude call site. Tokens are estimates, refreshed by hand
# when prompts or cadence change materially.
COST_ESTIMATES: list[dict[str, object]] = [
    {
        "site": "onchain_index.brief.generate_brief",
        "model": "claude-sonnet-4-6",
        "calls_per_week": 1,
        "tokens_in": 2_000,
        "tokens_out": 600,
    }
]
