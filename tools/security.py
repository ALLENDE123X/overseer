def scan_text(text: str, block_patterns: list[str]) -> dict:
    """scan text for blocked patterns"""
    for pattern in block_patterns:
        if pattern in text:
            return {"error": f"blocked pattern found: {pattern}"}
    return {"ok": True}


def scan_repo() -> dict:
    """scan entire repo for security issues (stub)"""
    # always ok for demo
    return {"ok": True, "issues": []}

