import os
import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.agents.state import PipelineState
from backend.agents.nodes import (
    parse_jd_node,
    analyze_gaps_node,
    generate_questions_node,
    write_resume_node,
    write_cover_letter_node,
    score_fit_node,
)

CHECKPOINT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "checkpoints.sqlite")
os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)

_conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
checkpointer = SqliteSaver(_conn)


def build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    builder.add_node("parse_jd", parse_jd_node)
    builder.add_node("analyze_gaps", analyze_gaps_node)
    builder.add_node("generate_questions", generate_questions_node)
    builder.add_node("write_resume", write_resume_node)
    builder.add_node("write_cover_letter", write_cover_letter_node)
    builder.add_node("score_fit", score_fit_node)

    builder.set_entry_point("parse_jd")
    builder.add_edge("parse_jd", "analyze_gaps")
    builder.add_edge("analyze_gaps", "generate_questions")
    builder.add_edge("generate_questions", "write_resume")
    builder.add_edge("write_resume", "write_cover_letter")
    builder.add_edge("write_cover_letter", "score_fit")
    builder.add_edge("score_fit", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
