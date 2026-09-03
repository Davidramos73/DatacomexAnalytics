from __future__ import annotations

import dataclasses
import json
from typing import Callable

import backend.config as config
from backend import events
from backend.config import MAX_AGENT_ITERS, MAX_TOKENS

_client = None


def get_client():
    global _client
    if _client is None:
        if config.LLM_PROVIDER == "openrouter":
            from openai import OpenAI

            _client = OpenAI(
                base_url=config.OPENROUTER_BASE_URL,
                api_key=config.OPENROUTER_API_KEY or None,
                default_headers={"X-Title": "Lumen Analyst"},
            )
        else:
            import anthropic

            _client = anthropic.Anthropic()
    return _client


def reset_client() -> None:
    """Drop the memoised client (used by tests that switch providers)."""
    global _client
    _client = None


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


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert our Anthropic-style tool defs to OpenAI function-tool defs."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
            },
        }
        for t in tools
    ]


def _dispatch_tool(name, args, tool_impls, tool_calls, sink, step_label):
    sink(
        step_label(name, dict(args))
        if step_label
        else events.Step(label=name)
    )
    try:
        out = tool_impls[name](**args)
        is_error = False
    except Exception as exc:  # noqa: BLE001 - surfaced to the model
        out = f"Error: {exc}"
        is_error = True
    text_out = out if isinstance(out, str) else json.dumps(out)
    tool_calls.append(ToolCall(name, dict(args), text_out, is_error))
    return text_out, is_error


# --------------------------------------------------------------------------- #
# Anthropic path
# --------------------------------------------------------------------------- #
def _text_of(content) -> str:
    parts = [b.text for b in content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def _run_agent_anthropic(
    *, model, system, messages, tools, tool_impls, sink, step_label, max_iters
) -> AgentResult:
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
                text_out, is_error = _dispatch_tool(
                    tu.name, dict(tu.input), tool_impls, tool_calls, sink, step_label
                )
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

        final_text = _text_of(response.content)
        return AgentResult(final_text, messages, tool_calls, iterations, False)

    sink(events.ErrorEvent(message=f"agent exceeded {max_iters} iterations"))
    return AgentResult(final_text, messages, tool_calls, iterations, True)


# --------------------------------------------------------------------------- #
# OpenAI-compatible path (OpenRouter)
# --------------------------------------------------------------------------- #
def _assistant_entry(msg) -> dict:
    entry: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        entry["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return entry


def _run_agent_openai(
    *, model, system, messages, tools, tool_impls, sink, step_label, max_iters
) -> AgentResult:
    client = get_client()
    msgs: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        msgs.append({"role": m["role"], "content": m["content"]})
    oai_tools = to_openai_tools(tools)
    tool_calls: list[ToolCall] = []
    iterations = 0
    final_text = ""

    while True:
        iterations += 1
        response = client.chat.completions.create(
            model=model,
            messages=msgs,
            tools=oai_tools,
            max_tokens=MAX_TOKENS,
        )
        msg = response.choices[0].message
        msgs.append(_assistant_entry(msg))

        if not msg.tool_calls:
            final_text = (msg.content or "").strip()
            return AgentResult(final_text, msgs, tool_calls, iterations, False)

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            text_out, _ = _dispatch_tool(
                tc.function.name, args, tool_impls, tool_calls, sink, step_label
            )
            msgs.append(
                {"role": "tool", "tool_call_id": tc.id, "content": text_out}
            )

        if iterations >= max_iters:
            break

    sink(events.ErrorEvent(message=f"agent exceeded {max_iters} iterations"))
    return AgentResult(final_text, msgs, tool_calls, iterations, True)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
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
    impl = (
        _run_agent_openai
        if config.LLM_PROVIDER == "openrouter"
        else _run_agent_anthropic
    )
    return impl(
        model=model,
        system=system,
        messages=messages,
        tools=tools,
        tool_impls=tool_impls,
        sink=sink,
        step_label=step_label,
        max_iters=max_iters,
    )


def structured_json(
    *,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    schema: dict,
    schema_name: str = "response",
) -> dict:
    """One completion constrained to `schema`, returned as a parsed dict.

    For the OpenAI path `messages` is the agent transcript (already carrying a
    system message); for the Anthropic path `system` is passed separately.
    """
    client = get_client()

    if config.LLM_PROVIDER == "openrouter":
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=to_openai_tools(tools),
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        return json.loads(response.choices[0].message.content)

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
        tools=tools,
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
