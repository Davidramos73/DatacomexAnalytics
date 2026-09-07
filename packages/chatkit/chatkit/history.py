MAX_HISTORY_TURNS = 6


def clean_history(turns) -> list[dict]:
    """Coerce client-supplied turns into a valid alternating message list:
    only user/assistant roles, non-empty, no consecutive same-role, starts
    with a user turn, capped to the most recent MAX_HISTORY_TURNS."""
    out: list[dict] = []
    for t in turns or []:
        role = t.get("role")
        content = (t.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if out and out[-1]["role"] == role:
            out[-1] = {"role": role, "content": content}
        else:
            out.append({"role": role, "content": content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out[-MAX_HISTORY_TURNS:]
