import os
import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .state import AppState
from .nodes import fetch_jd_node, analyze_node, chat_questioner, generate_node


def route_after_analyze(state: AppState) -> str:
    if state.get("error"):
        return END
    if state["phase"] == "generating":
        return "generate"
    return "chat"


def route_after_chat(state: AppState) -> str:
    if state["phase"] == "generating":
        return "generate"
    return "chat"


def build_graph():
    """Build and compile the LangGraph pipeline with SQLite checkpointer."""
    graph = StateGraph(AppState)

    graph.add_node("fetch_jd", fetch_jd_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("chat", chat_questioner)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("fetch_jd")
    graph.add_edge("fetch_jd", "analyze")

    graph.add_conditional_edges("analyze", route_after_analyze, {
        "chat": "chat",
        "generate": "generate",
        END: END
    })

    graph.add_conditional_edges("chat", route_after_chat, {
        "chat": "chat",
        "generate": "generate"
    })

    graph.add_edge("generate", END)

    db_path = os.path.join(os.path.dirname(__file__), "..", "checkpoints.sqlite")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    return graph.compile(checkpointer=checkpointer, interrupt_before=["chat"])


pipeline = build_graph()
