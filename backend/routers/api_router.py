import asyncio
from fastapi import APIRouter, File, UploadFile, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from langgraph.types import Command

from backend.graph.pipeline import pipeline
from backend.graph.state import AppState
from backend.utils.pdf_parser import parse_pdf, count_pages
from backend.utils.doc_exporter import text_to_docx

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def get_session_id(x_session_id: Optional[str] = Header(default=None)) -> str:
    if not x_session_id or len(x_session_id) < 10:
        raise HTTPException(status_code=400, detail="Missing X-Session-ID header")
    return x_session_id


def get_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def run_graph_step(input_val, config: dict) -> dict:
    """
    Run the graph until it hits an interrupt or completes.
    Returns {"type": "interrupt", "message": str} or {"type": "done", "state": dict}
    """
    last_state = None
    for event in pipeline.stream(input_val, config=config, stream_mode="values"):
        last_state = event

    snapshot = pipeline.get_state(config)

    if snapshot.next:
        interrupt_msg = None
        for task in snapshot.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupt_msg = task.interrupts[0].value
                break
        return {"type": "interrupt", "message": interrupt_msg or "Please respond to continue."}
    else:
        return {"type": "done", "state": last_state}


@router.post("/analyze")
async def analyze(
    resume: UploadFile = File(...),
    jd_url: str = Form(...),
    x_session_id: Optional[str] = Header(default=None)
):
    """Start analysis: upload resume PDF + JD URL. Runs until first chat question."""
    session_id = get_session_id(x_session_id)
    config = get_config(session_id)

    if not resume.filename.endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file")

    file_bytes = await resume.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 10MB.")

    resume_text = parse_pdf(file_bytes)
    if len(resume_text.strip()) < 100:
        raise HTTPException(400, "Could not extract text from PDF. Is it a scanned image?")

    pages = count_pages(file_bytes)

    if not jd_url.strip().startswith(("http://", "https://")):
        raise HTTPException(400, "Please provide a valid URL starting with http:// or https://")

    initial_state = AppState(
        session_id=session_id,
        resume_text=resume_text,
        jd_url=jd_url.strip(),
        jd_text="",
        jd_title="",
        jd_company="",
        gaps=[],
        chat_history=[],
        user_info_gathered="",
        is_generation_confirmed=False,
        resume_output="",
        cover_letter_output="",
        fit_score=0,
        fit_breakdown={},
        fit_recommendation="",
        phase="fetching",
        error=None
    )

    result = await asyncio.to_thread(run_graph_step, initial_state, config)

    if result["type"] == "done":
        state = result["state"]
        if state.get("error"):
            raise HTTPException(503, state["error"])
        return {
            "status": "done",
            "session_id": session_id,
            "jd_title": state["jd_title"],
            "jd_company": state["jd_company"],
            "resume_pages": pages,
            "chat_history": state.get("chat_history", []),
        }
    else:
        snapshot = pipeline.get_state(config)
        state = snapshot.values
        return {
            "status": "chatting",
            "session_id": session_id,
            "jd_title": state.get("jd_title", ""),
            "jd_company": state.get("jd_company", ""),
            "resume_pages": pages,
            "chat_history": state.get("chat_history", []),
            "next_question": result["message"]
        }


@router.post("/chat")
async def chat(
    body: ChatRequest,
    x_session_id: Optional[str] = Header(default=None)
):
    """Resume the graph with user's chat message."""
    session_id = get_session_id(x_session_id)
    config = get_config(session_id)

    snapshot = pipeline.get_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(400, "No active session. Please start a new analysis.")

    result = await asyncio.to_thread(
        run_graph_step,
        Command(resume=body.message),
        config
    )

    if result["type"] == "interrupt":
        snapshot2 = pipeline.get_state(config)
        state = snapshot2.values
        return {
            "status": "chatting",
            "chat_history": state.get("chat_history", []),
            "next_question": result["message"]
        }
    else:
        state = result["state"]
        return {
            "status": "done",
            "chat_history": state.get("chat_history", []),
            "fit_score": state.get("fit_score", 0),
            "fit_breakdown": state.get("fit_breakdown", {}),
            "fit_recommendation": state.get("fit_recommendation", ""),
            "resume_output": state.get("resume_output", ""),
            "cover_letter_output": state.get("cover_letter_output", "")
        }


@router.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get the final outputs for a completed session."""
    config = get_config(session_id)
    snapshot = pipeline.get_state(config)
    if not snapshot:
        raise HTTPException(404, "Session not found")
    state = snapshot.values
    if state.get("phase") != "done":
        raise HTTPException(400, "Analysis not complete yet")
    return {
        "resume_output": state.get("resume_output", ""),
        "cover_letter_output": state.get("cover_letter_output", ""),
        "fit_score": state.get("fit_score", 0),
        "fit_breakdown": state.get("fit_breakdown", {}),
        "fit_recommendation": state.get("fit_recommendation", ""),
        "jd_title": state.get("jd_title", ""),
        "jd_company": state.get("jd_company", "")
    }


@router.get("/export/{session_id}/{doc_type}")
async def export_doc(session_id: str, doc_type: str):
    """Download resume or cover letter as a .docx file."""
    if doc_type not in ("resume", "cover-letter"):
        raise HTTPException(400, "doc_type must be 'resume' or 'cover-letter'")

    config = get_config(session_id)
    snapshot = pipeline.get_state(config)
    if not snapshot:
        raise HTTPException(404, "Session not found")

    state = snapshot.values
    if doc_type == "resume":
        text = state.get("resume_output", "")
        filename = f"resume_{state.get('jd_company', 'company').replace(' ', '_')}.docx"
    else:
        text = state.get("cover_letter_output", "")
        filename = f"cover_letter_{state.get('jd_company', 'company').replace(' ', '_')}.docx"

    if not text:
        raise HTTPException(404, "Document not generated yet")

    docx_bytes = await asyncio.to_thread(text_to_docx, text)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
