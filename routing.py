# default provider pool
DEFAULT_POOL = {
    "name": "default",
    "models": [
        {"name": "small-fast", "max_context": 8000, "rps": 200, "cost": 0.0005},
        {"name": "gpt-4.1", "max_context": 128000, "rps": 20, "cost": 0.015}
    ],
    "routing": []
}


def choose_model(tokens_needed: int, step: str, pool: dict = None) -> dict:
    """choose model from pool based on context size and step"""
    if pool is None:
        pool = DEFAULT_POOL
    
    # use gpt-4.1 for high token needs or critical steps
    if tokens_needed > 60000 or step in ["aggregator", "react"]:
        model = "gpt-4.1"
        cost = 0.015
    else:
        model = "small-fast"
        cost = 0.0005
    
    return {
        "model": model,
        "tokens": tokens_needed,
        "cost_usd": cost,
        "step": step
    }

