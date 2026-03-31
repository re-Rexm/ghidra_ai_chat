from __future__ import print_function

import json


SYSTEM_PROMPT = """You are a reverse engineering assistant embedded in Ghidra.

Rules:
- Use ONLY the provided context. If something is missing, say exactly what additional context you need.
- Be concrete: refer to function names, addresses, strings, and call patterns when possible.
- If evidence is insufficient, provide hypotheses with confidence levels and tell the user how to verify in Ghidra.
- Prefer short, actionable steps over long essays.
"""


def _truncate(s, max_chars):
    if s is None:
        return ""
    if max_chars is None or max_chars <= 0:
        return str(s)
    s = str(s)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 200] + "\n\n[...truncated...]\n"


def format_context_block(context, settings):
    """
    Produce a readable context string for LLM + for preview.
    """
    if not context:
        return "No context."
    if context.get("error"):
        return "ContextError: %s" % context.get("error")

    parts = []
    parts.append("ProgramSummary:")
    parts.append(json.dumps(context.get("program", {}), indent=2, sort_keys=True))
    parts.append("")

    parts.append("Location:")
    parts.append(json.dumps(context.get("location", {}), indent=2, sort_keys=True))
    parts.append("")

    parts.append("CurrentFunction:")
    parts.append(json.dumps(context.get("function", {}), indent=2, sort_keys=True))
    parts.append("")

    if getattr(settings, "include_decompile", True):
        parts.append("Decompile:")
        parts.append(_truncate(context.get("decompile", ""), int(getattr(settings, "max_context_chars", 18000) * 0.75)))
        parts.append("")

    other = []
    if getattr(settings, "include_strings", False):
        other.append({"strings": context.get("strings", [])})
    if getattr(settings, "include_imports", False):
        other.append({"imports": context.get("imports", [])})
    if getattr(settings, "include_xrefs", False):
        other.append({"xrefs": context.get("xrefs", [])})

    if other:
        parts.append("OtherArtifacts:")
        for item in other:
            parts.append(json.dumps(item, indent=2, sort_keys=True))
        parts.append("")

    joined = "\n".join(parts).strip() + "\n"
    return _truncate(joined, getattr(settings, "max_context_chars", 18000))


def build_messages(question, context_str, history, settings):
    """
    history: list of {role, content} entries.
    Returns messages list suitable for OpenAI-style chat completion.
    """
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

    # rolling history window, budgeted by chars
    hist_budget = int(getattr(settings, "max_history_chars", 6000))
    if history:
        acc = 0
        kept = []
        for m in reversed(history):
            c = str(m.get("content", ""))
            acc += len(c)
            if acc > hist_budget:
                break
            kept.append({"role": m.get("role", "user"), "content": c})
        msgs.extend(reversed(kept))

    user_payload = "Question:\n%s\n\n%s" % (question, context_str)
    msgs.append({"role": "user", "content": user_payload})
    return msgs

