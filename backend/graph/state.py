from typing import TypedDict, List, Optional, Annotated
import operator


class Gap(TypedDict):
    skill: str                    # e.g. "Kubernetes"
    jd_requirement: str           # what the JD says
    resume_coverage: str          # "none", "partial"
    question: str                 # conversational question to ask user
    user_answer: Optional[str]    # filled in after user responds
    addressed: bool               # True once user has answered


class ChatMessage(TypedDict):
    role: str       # "assistant" or "user"
    content: str


class AppState(TypedDict):
    session_id: str
    resume_text: str
    jd_url: str
    jd_text: str
    jd_title: str
    jd_company: str
    gaps: List[Gap]
    chat_history: Annotated[List[ChatMessage], operator.add]  # append-only
    user_info_gathered: str       # accumulated extra context from chat
    is_generation_confirmed: bool
    resume_output: str
    cover_letter_output: str
    fit_score: int                # 1-10
    fit_breakdown: dict           # {"technical": 7, "experience": 8, "culture": 6}
    fit_recommendation: str       # "Strong Fit", "Good Fit", etc.
    phase: str                    # "fetching" | "analyzing" | "chatting" | "confirming" | "generating" | "done"
    error: Optional[str]
