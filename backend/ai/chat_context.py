"""Keep multi-turn chat efficient: only the latest user message may carry vision + long file text."""

from __future__ import annotations


def messages_for_llm_turn(messages: list[dict]) -> list[dict]:
    """
    Build the payload for one model call.

    Earlier user turns are reduced to their display ``content`` only (no ``attachments``,
    no ``model_content``), so homework scans and rubric dumps are not re-sent forever.
    Only the **last** message in the list may include vision images and full extracted text.
    """
    if not messages:
        return []

    n = len(messages)
    last_i = n - 1
    out: list[dict] = []

    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            c = m.get("content") or ""
            out.append(
                {"role": "assistant", "content": c if isinstance(c, str) else str(c)}
            )
            continue

        if role == "user":
            if i == last_i:
                text = m.get("model_content")
                if text is None:
                    text = m.get("content") or ""
                if not isinstance(text, str):
                    text = str(text)
                u: dict = {"role": "user", "content": text}
                att = m.get("attachments")
                if att:
                    u["attachments"] = att
                out.append(u)
            else:
                c = m.get("content") or ""
                out.append(
                    {"role": "user", "content": c if isinstance(c, str) else str(c)}
                )
            continue

        c = m.get("content") or ""
        out.append(
            {"role": role or "user", "content": c if isinstance(c, str) else str(c)}
        )

    return out
