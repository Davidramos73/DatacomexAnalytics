from __future__ import annotations

import time

from chatkit import events
from chatkit.agents import llm
from chatkit.config import LLM_MODEL
from chatkit.domain import Domain, default_step_label
from chatkit.history import clean_history
from chatkit.widgets import build_tool_set


def run_chat(domain: Domain, user_message: str, sink, *, history=None) -> None:
    started = time.monotonic()
    con = domain.open_connection()
    try:
        prior = clean_history(history)
        sink(events.Thinking(label="Consultando datos"))

        extra = domain.extra_tools() or {"defs": [], "handlers": {}}
        wt = build_tool_set(domain.widgets(), con)
        defs = extra["defs"] + wt["defs"]
        handlers = {**extra["handlers"], **wt["handlers"]}

        def _label(name, ti):
            return domain.step_label(name, ti) or default_step_label(name, ti)

        agent = llm.run_agent(
            model=LLM_MODEL, system=domain.system_prompt,
            messages=prior + [{"role": "user", "content": user_message}],
            tools=defs, tool_impls=handlers, sink=sink, step_label=_label,
        )

        envelope = domain.finalize(agent, con)

        answer = ""
        closeout = [{"role": "user", "content": domain.prose_closeout_instruction}]
        for piece in llm.stream_text(
            model=LLM_MODEL, system=domain.system_prompt,
            messages=agent.messages + closeout,
        ):
            answer += piece
            sink(events.Delta(text=piece))
        answer = answer.strip() or agent.final_text or "Sin respuesta."

        if envelope is None:
            sink(events.Text(text=answer))
            sink(events.Done(seconds=round(time.monotonic() - started, 1)))
            return

        meta = envelope.setdefault("meta", {})
        notes = meta.setdefault("notes", [])
        if agent.hit_limit:
            notes.append("respuesta truncada: se alcanzó el límite de pasos")

        sink(events.Step(label="chart.render", detail="echarts v5"))
        sink(events.Text(text=answer))
        sink(events.Chart(
            title=envelope.get("title", "Informe"),
            meta=" · ".join(
                [f"{k['label']}: {k['value']}" for k in envelope.get("kpis", [])]
                + notes
            ),
            spec=envelope["echarts"],
            data=envelope.get("data") or {"columns": [], "rows": []},
        ))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
    finally:
        close = getattr(con, "close", None)
        if callable(close):
            close()
