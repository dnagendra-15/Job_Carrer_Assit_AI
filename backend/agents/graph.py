import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.state import PipelineState
from backend.agents.nodes import (
    fetch_jd_node,
    route_after_fetch,
    parse_jd_node,
    analyze_and_question_node,
    write_documents_node,
    score_fit_node,
)

CHECKPOINT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "checkpoints.sqlite")
os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)

checkpointer = MemorySaver()


def build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    builder.add_node("fetch_jd", fetch_jd_node)
    builder.add_node("parse_jd", parse_jd_node)
    builder.add_node("analyze_and_question", analyze_and_question_node)
    builder.add_node("write_documents", write_documents_node)
    builder.add_node("score_fit", score_fit_node)

    builder.set_entry_point("fetch_jd")
    # If the JD URL fails to fetch (timeout, 404, blocked, etc.), skip
    # straight to END with state["error"] set rather than crashing the
    # whole graph -- the router surfaces state["error"] as a clean 503.
    builder.add_conditional_edges(
        "fetch_jd",
        route_after_fetch,
        {"parse_jd": "parse_jd", "error_end": END},
    )
    builder.add_edge("parse_jd", "analyze_and_question")
    builder.add_edge("analyze_and_question", "write_documents")
    builder.add_edge("write_documents", "score_fit")
    builder.add_edge("score_fit", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
