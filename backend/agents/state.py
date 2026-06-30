from typing import Optional
from typing_extensions import TypedDict


class ChatMessage(TypedDict):
    role: str  # "assistant" | "user"
    content: str


class PipelineState(TypedDict, total=False):
    # session / input
    session_id: str
    resume_text: str
    jd_url: str

    # JD pipeline
    jd_text: str
    jd_summary: str
    jd_title: str
    jd_company: str

    # gap analysis + Q&A
    gaps: list
    questions: list
    user_answers: dict
    chat_history: list  # list[ChatMessage], UI-facing transcript

    # generated documents
    tailored_resume: str
    cover_letter: str

    # fit score (matches frontend contract: 0-10 scale)
    fit_score: int
    fit_breakdown: dict
    fit_recommendation: str

    # bookkeeping
    phase: str
    error: Optional[str]
