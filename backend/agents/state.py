from typing import Optional
from typing_extensions import TypedDict


class PipelineState(TypedDict, total=False):
    resume_text: str
    jd_text: str
    jd_summary: str
    gaps: list
    questions: list
    user_answers: dict
    tailored_resume: str
    cover_letter: str
    fit_score: dict
