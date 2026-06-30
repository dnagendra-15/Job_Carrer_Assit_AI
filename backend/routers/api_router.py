import asyncio
from fastapi import APIRouter, File, UploadFile, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from langgraph.types import Command

from backend.agents.graph import graph as pipeline
from backend.agents.state import PipelineState as AppState
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


def _append_chat(config: dict, role: str, content: str):
    """Append a turn to the UI-facing chat transcript. This is bookkeeping
    only (never sent back to an LLM), so it's done as a direct state patch
    rather than threading it through node return values."""
    snapshot = pipeline.get_state(config)
    history = list((snapshot.values or {}).get("chat_history", []))
    history.append({"role": role, "content": content})
    pipeline.update_state(config, {"chat_history": history})
    return history


def run_graph_step(input_val, config: dict) -> dict:
    """
    Run the graph until it hits an interrupt or completes.
    Returns {"type": "interrupt", "message": str} or {"type": "done", "state": dict}
    """
    for _ in pipeline.stream(input_val, config=config, stream_mode="values"):
        pass

    snapshot = pipeline.get_state(config)

    if snapshot.next:
        interrupt_msg = "Please respond to continue."
        for task in snapshot.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                raw_val = task.interrupts[0].value
                if isinstance(raw_val, dict) and "questions" in raw_val:
                    q_list = raw_val["questions"]
                    formatted_msg = "I found a few gaps between your resume and the job description. To tailor your application perfectly, please clarify:\n\n"
                    for q in q_list:
                        formatted_msg += f"- {q.get('question', '')}\n"
                    interrupt_msg = formatted_msg
                else:
                    interrupt_msg = str(raw_val)
                break
        return {"type": "interrupt", "message": interrupt_msg}

    final_snapshot = pipeline.get_state(config)
    return {"type": "done", "state": final_snapshot.values}


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
        chat_history=[],
        phase="fetching",
    )

    result = await asyncio.to_thread(run_graph_step, initial_state, config)

    if result["type"] == "done":
        state = result["state"]
        if state.get("error"):
            raise HTTPException(503, state["error"])
        # Pipeline finished without ever hitting the Q&A interrupt
        # (e.g. the gap analyzer found nothing worth asking about).
        return {
            "status": "done",
            "session_id": session_id,
            "jd_title": state.get("jd_title", ""),
            "jd_company": state.get("jd_company", ""),
            "resume_pages": pages,
            "chat_history": state.get("chat_history", []),
            "fit_score": state.get("fit_score", 0),
            "fit_breakdown": state.get("fit_breakdown", {}),
            "fit_recommendation": state.get("fit_recommendation", ""),
            "resume_output": state.get("tailored_resume", ""),
            "cover_letter_output": state.get("cover_letter", ""),
        }

    snapshot = pipeline.get_state(config)
    state = snapshot.values
    if state.get("error"):
        raise HTTPException(503, state["error"])

    chat_history = _append_chat(config, "assistant", result["message"])

    return {
        "status": "chatting",
        "session_id": session_id,
        "jd_title": state.get("jd_title", ""),
        "jd_company": state.get("jd_company", ""),
        "resume_pages": pages,
        "chat_history": chat_history,
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

    _append_chat(config, "user", body.message)

    result = await asyncio.to_thread(
        run_graph_step,
        Command(resume=body.message),
        config
    )

    if result["type"] == "interrupt":
        chat_history = _append_chat(config, "assistant", result["message"])
        return {
            "status": "chatting",
            "chat_history": chat_history,
            "next_question": result["message"]
        }

    state = result["state"]
    if state.get("error"):
        raise HTTPException(503, state["error"])

    return {
        "status": "done",
        "chat_history": state.get("chat_history", []),
        "fit_score": state.get("fit_score", 0),
        "fit_breakdown": state.get("fit_breakdown", {}),
        "fit_recommendation": state.get("fit_recommendation", ""),
        "resume_output": state.get("tailored_resume", ""),
        "cover_letter_output": state.get("cover_letter", "")
    }


@router.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get the final outputs for a completed session."""
    config = get_config(session_id)
    snapshot = pipeline.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Session not found")
    state = snapshot.values
    if state.get("phase") != "done":
        raise HTTPException(400, "Analysis not complete yet")
    return {
        "resume_output": state.get("tailored_resume", ""),
        "cover_letter_output": state.get("cover_letter", ""),
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
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Session not found")

    state = snapshot.values
    company = (state.get("jd_company") or "company").replace(" ", "_")

    if doc_type == "resume":
        text = state.get("tailored_resume", "")
        filename = f"resume_{company}.docx"
    else:
        text = state.get("cover_letter", "")
        filename = f"cover_letter_{company}.docx"

    if not text:
        raise HTTPException(404, "Document not generated yet")

    docx_bytes = await asyncio.to_thread(text_to_docx, text, doc_type)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
