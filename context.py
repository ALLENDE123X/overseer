from tools import files


def compile_context(run, step: str, profile_name: str, events: list, context_profiles: dict) -> dict:
    """compile context bundle with manifest and budget enforcement"""
    
    profile = context_profiles.get(profile_name, {"budget_tokens": 120000})
    budget = profile.get("budget_tokens", 120000)
    
    # gather scratchpad (last 5 events' data)
    recent_events = events[-5:] if len(events) > 5 else events
    scratchpad = [{"step": e.get("step", ""), "type": e.get("type", ""), "data": e.get("data", {})} 
                  for e in recent_events]
    
    # gather repo snippets (read key files)
    repo_snippets = {}
    try:
        app_content = files.read("app.py")
        if "content" in app_content:
            repo_snippets["app.py"] = app_content["content"]
    except:
        pass
    
    try:
        test_content = files.read("tests/test_app.py")
        if "content" in test_content:
            repo_snippets["tests/test_app.py"] = test_content["content"]
    except:
        pass
    
    # policy docs stub
    policy_docs = {"note": "policy enforcement active", "patterns_blocked": ["eval("]}
    
    # build sections and estimate tokens (len/4 heuristic)
    sections = {
        "scratchpad": {"content": scratchpad, "token_estimate": len(str(scratchpad)) // 4},
        "repo_snippets": {"content": repo_snippets, "token_estimate": len(str(repo_snippets)) // 4},
        "policy_docs": {"content": policy_docs, "token_estimate": len(str(policy_docs)) // 4}
    }
    
    total_tokens = sum(s["token_estimate"] for s in sections.values())
    drops = []
    
    # enforce budget by trimming repo snippets first
    if total_tokens > budget:
        trim_amount = total_tokens - budget
        if sections["repo_snippets"]["token_estimate"] > trim_amount:
            sections["repo_snippets"]["token_estimate"] -= trim_amount
            # truncate repo snippets
            max_chars = sections["repo_snippets"]["token_estimate"] * 4
            repo_str = str(repo_snippets)
            if len(repo_str) > max_chars:
                drops.append(f"repo_snippets trimmed by {len(repo_str) - max_chars} chars")
                sections["repo_snippets"]["content"] = repo_str[:max_chars]
            total_tokens = budget
        else:
            drops.append("repo_snippets dropped entirely")
            sections["repo_snippets"]["content"] = {}
            sections["repo_snippets"]["token_estimate"] = 0
            total_tokens = (sections["scratchpad"]["token_estimate"] + 
                          sections["policy_docs"]["token_estimate"])
    
    bundle = {
        "scratchpad": sections["scratchpad"]["content"],
        "repo_snippets": sections["repo_snippets"]["content"],
        "policy_docs": sections["policy_docs"]["content"]
    }
    
    manifest = {
        "sections": {k: {"token_estimate": v["token_estimate"]} for k, v in sections.items()},
        "total_tokens": total_tokens,
        "drops": drops
    }
    
    return {"bundle": bundle, "manifest": manifest}

