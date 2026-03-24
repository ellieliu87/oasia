"""
Agent Panel UI — company SDK version.

Changes from original:
  - respond() is now async (Gradio handles async event handlers natively)
  - orchestrator.chat() called with await
  - All other logic unchanged
"""
from __future__ import annotations

import gradio as gr


def create_agent_panel():
    """
    Returns chatbot, msg_input, send_btn, clear_btn.
    Layout: chatbot (flex-fill) → compact input bar with send + clear inline.
    Unchanged from original.
    """
    chatbot = gr.Chatbot(
        label="",
        height=None,
        show_label=False,
        layout="bubble",
        avatar_images=(None, None),
        elem_id="nexus-chatbot",
        elem_classes=["nexus-chatbot-inner"],
    )

    with gr.Row(elem_id="nexus-input-bar", elem_classes=["nexus-input-bar"]):
        msg_input = gr.Textbox(
            label="",
            placeholder="Ask Oasia anything…",
            show_label=False,
            scale=10,
            lines=1,
            max_lines=1,
            elem_id="nexus-msg-input",
        )
        send_btn = gr.Button(
            "➤", variant="primary", scale=0, min_width=36,
            elem_id="nexus-send-btn",
        )
        clear_btn = gr.Button(
            "✕", variant="secondary", scale=0, min_width=28,
            elem_id="nexus-clear-btn",
            size="sm",
        )

    return chatbot, msg_input, send_btn, clear_btn


def wire_agent_panel(
    chatbot: gr.Chatbot,
    msg_input: gr.Textbox,
    send_btn: gr.Button,
    clear_btn: gr.Button,
    orchestrator_state: gr.State,
    dashboard_state=None,
):
    """Wire event handlers for the agent panel."""

    def _get_or_create_orchestrator(state):
        if state is None or "orchestrator" not in state:
            from agent.orchestrator import AgentOrchestrator
            orch = AgentOrchestrator()
            if state is None:
                state = {}
            state["orchestrator"] = orch
        return state["orchestrator"], state

    def _parse_dashboard_cmd(message: str, dash_state: dict) -> dict:
        ds  = dict(dash_state or {})
        msg = message.lower()
        if any(w in msg for w in ["cc30", "conventional 30"]):
            ds["filter_product"] = "CC30"
        elif any(w in msg for w in ["cc15", "conventional 15"]):
            ds["filter_product"] = "CC15"
        elif any(w in msg for w in ["gn30", "gnma 30", "ginnie 30"]):
            ds["filter_product"] = "GN30"
        elif any(w in msg for w in ["gn15", "gnma 15", "ginnie 15"]):
            ds["filter_product"] = "GN15"
        elif any(w in msg for w in ["all positions", "entire portfolio", "show all", "clear filter", "reset"]):
            ds["filter_product"] = None
        ds["refresh_count"] = ds.get("refresh_count", 0) + 1
        return ds

    # ── async: Gradio handles async event handlers natively ──────────────────
    async def respond(message: str, history: list, state: dict, dash_state: dict = None):
        if not message or not message.strip():
            if dashboard_state is not None:
                return "", history, state, dash_state
            return "", history, state

        orchestrator, state = _get_or_create_orchestrator(state)
        history = history or []
        history.append({"role": "user", "content": message})

        try:
            response = await orchestrator.chat(message)   # await async chat()
        except Exception as e:
            response = f"Error: {str(e)}"

        history.append({"role": "assistant", "content": response})
        new_dash = _parse_dashboard_cmd(message, dash_state) if dashboard_state is not None else dash_state
        if dashboard_state is not None:
            return "", history, state, new_dash
        return "", history, state

    def clear_chat(state, dash_state=None):
        if state and "orchestrator" in state:
            state["orchestrator"].clear_history()
        if dashboard_state is not None:
            return [], state, dash_state
        return [], state

    if dashboard_state is not None:
        inputs_r  = [msg_input, chatbot, orchestrator_state, dashboard_state]
        outputs_r = [msg_input, chatbot, orchestrator_state, dashboard_state]
        inputs_c  = [orchestrator_state, dashboard_state]
        outputs_c = [chatbot, orchestrator_state, dashboard_state]
    else:
        inputs_r  = [msg_input, chatbot, orchestrator_state]
        outputs_r = [msg_input, chatbot, orchestrator_state]
        inputs_c  = [orchestrator_state]
        outputs_c = [chatbot, orchestrator_state]

    send_btn.click(fn=respond, inputs=inputs_r, outputs=outputs_r)
    msg_input.submit(fn=respond, inputs=inputs_r, outputs=outputs_r)
    clear_btn.click(fn=clear_chat, inputs=inputs_c, outputs=outputs_c)
