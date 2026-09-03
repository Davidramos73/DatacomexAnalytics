from __future__ import annotations

import dataclasses
import json
from typing import Callable

from backend import events
from backend.config import MAX_AGENT_ITERS, MAX_TOKENS

_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


Sink = Callable[[events.Event], None]


@dataclasses.dataclass
class ToolCall:
    name: str
    input: dict
    result: str
    is_error: bool


@dataclasses.dataclass
class AgentResult:
    final_text: str
    messages: list
    tool_calls: list
    iterations: int
    hit_limit: bool


def _text_of(content) -> str:
    parts = [b.text for b in content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def run_agent(
    *,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_impls: dict[str, Callable[..., str]],
    sink: Sink,
    step_label: Callable[[str, dict], events.Step] | None = None,
    max_iters: int | None = None,
) -> AgentResult:
    max_iters = MAX_AGENT_ITERS if max_iters is None else max_iters
    client = get_client()
    messages = list(messages)
    tool_calls: list[ToolCall] = []
    iterations = 0
    final_text = ""

    while True:
        iterations += 1
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = _text_of(response.content)
            return AgentResult(final_text, messages, tool_calls, iterations, False)

        if response.stop_reason == "pause_turn":
            if iterations >= max_iters:
                break
            continue

        if response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            results = []
            for tu in tool_uses:
                label_event = (
                    step_label(tu.name, dict(tu.input))
                    if step_label
                    else events.Step(label=tu.name)
                )
                sink(label_event)
                try:
                    out = tool_impls[tu.name](**tu.input)
                    is_error = False
                except Exception as exc:  # noqa: BLE001 - surfaced to the model
                    out = f"Error: {exc}"
                    is_error = True
                text_out = out if isinstance(out, str) else json.dumps(out)
                tool_calls.append(ToolCall(tu.name, dict(tu.input), text_out, is_error))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": text_out,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
            if iterations >= max_iters:
                break
            continue

        # unknown stop reason: treat as terminal
        final_text = _text_of(response.content)
        return AgentResult(final_text, messages, tool_calls, iterations, False)

    sink(events.ErrorEvent(message=f"agent exceeded {max_iters} iterations"))
    return AgentResult(final_text, messages, tool_calls, iterations, True)
