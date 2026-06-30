import json
import re

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config.models_config import get_llm
from backend.agents.state import PipelineState
from backend.agents import prompts
from backend.utils.jd_fetcher import fetch_jd_from_url


def _extract_json(content: str, open_char: str, close_char: str):
    """Best-effort JSON extraction if the model wraps output in prose/fences."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find(open_char)
        end = content.rfind(close_char) + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        raise


def fetch_jd_node(state: PipelineState) -> dict:
    """
    Scrapes the JD URL into state["jd_text"]. This node was previously
    missing entirely -- the graph used to start at parse_jd expecting
    jd_text to already be populated, which it never was.
    """
    try:
        jd_text = fetch_jd_from_url(state["jd_url"])
        return {"jd_text": jd_text, "phase": "parsing"}
    except (ValueError, RuntimeError) as e:
        return {"error": str(e), "phase": "error"}


def route_after_fetch(state: PipelineState) -> str:
    return "error_end" if state.get("error") else "parse_jd"


_ROLE_RE = re.compile(r"^ROLE:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_COMPANY_RE = re.compile(r"^COMPANY:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def parse_jd_node(state: PipelineState) -> dict:
    llm = get_llm("jd_parser")
    messages = [
        SystemMessage(content=prompts.JD_PARSER_SYSTEM),
        HumanMessage(content=prompts.JD_PARSER_HUMAN.format(jd_text=state["jd_text"]))
    ]
    response = llm.invoke(messages)
    summary = response.content

    # Pull title/company out of the summary's own ROLE:/COMPANY: lines
    # instead of paying for a second LLM call to extract the same info.
    role_match = _ROLE_RE.search(summary)
    company_match = _COMPANY_RE.search(summary)
    jd_title = role_match.group(1).strip() if role_match else "Role"
    jd_company = company_match.group(1).strip() if company_match else "Company"
    if jd_company.lower().startswith("not specified"):
        jd_company = "Company"

    return {"jd_summary": summary, "jd_title": jd_title, "jd_company": jd_company, "phase": "analyzing"}


def analyze_and_question_node(state: PipelineState) -> dict:
    """
    Combines gap analysis + question generation into a single LLM call.
    Previously these were two separate nodes that each sent the full
    resume_text + jd_summary -- merging them halves that redundant payload.
    """
    llm = get_llm("gap_analyzer")
    messages = [
        SystemMessage(content=prompts.GAP_AND_QUESTIONS_SYSTEM),
        HumanMessage(content=prompts.GAP_AND_QUESTIONS_HUMAN.format(
            jd_summary=state["jd_summary"],
            resume_text=state["resume_text"]
        ))
    ]
    response = llm.invoke(messages)
    try:
        parsed = _extract_json(response.content, "{", "}")
        gaps = parsed.get("gaps", [])
        questions = parsed.get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        gaps = [{"requirement": "Could not parse gaps", "candidate_status": "Unknown", "severity": "MEDIUM", "category": "technical"}]
        questions = [{"id": "q1", "question": "Tell us more about your relevant experience.", "gap_reference": "general", "hint": "Describe any related projects or skills."}]

    if not questions:
        questions = [{"id": "q1", "question": "Tell us more about your relevant experience.", "gap_reference": "general", "hint": "Describe any related projects or skills."}]

    user_answers = interrupt({"questions": questions})
    return {"gaps": gaps, "questions": questions, "user_answers": user_answers, "phase": "generating"}


def write_documents_node(state: PipelineState) -> dict:
    """
    Combines resume + cover letter writing into a single LLM call.
    Previously these were two separate nodes that each sent the full
    resume_text + jd_summary + answers -- merging them halves that
    redundant payload.
    """
    llm = get_llm("resume_writer")
    answers_text = state.get("user_answers", "")
    if isinstance(answers_text, dict):
        answers_text = "\n".join([f"{k}: {v}" for k, v in answers_text.items()])

    messages = [
        SystemMessage(content=prompts.DOCUMENT_WRITER_SYSTEM),
        HumanMessage(content=prompts.DOCUMENT_WRITER_HUMAN.format(
            jd_summary=state["jd_summary"],
            resume_text=state["resume_text"],
            answers=answers_text or "No additional context provided."
        ))
    ]
    response = llm.invoke(messages)
    content = response.content

    if "===COVER-LETTER===" in content:
        resume_part, cover_part = content.split("===COVER-LETTER===", 1)
    else:
        # Fallback if the model drops the delimiter -- keep the pipeline
        # from crashing rather than losing both documents.
        resume_part, cover_part = content, ""

    tailored_resume = resume_part.replace("## RESUME", "", 1).strip()
    cover_letter = cover_part.replace("## COVER LETTER", "", 1).strip()

    return {"tailored_resume": tailored_resume, "cover_letter": cover_letter, "phase": "scoring"}


def score_fit_node(state: PipelineState) -> dict:
    llm = get_llm("fit_scorer")
    messages = [
        SystemMessage(content=prompts.FIT_SCORER_SYSTEM),
        HumanMessage(content=prompts.FIT_SCORER_HUMAN.format(
            jd_summary=state["jd_summary"],
            tailored_resume=state["tailored_resume"]
        ))
    ]
    response = llm.invoke(messages)
    try:
        parsed = _extract_json(response.content, "{", "}")
        fit_score = int(parsed.get("overall_score", 0))
        fit_recommendation = parsed.get("recommendation", "")
        fit_breakdown = parsed.get("categories", {})
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        fit_score, fit_recommendation, fit_breakdown = 0, "Could not score", {}

    return {
        "fit_score": fit_score,
        "fit_recommendation": fit_recommendation,
        "fit_breakdown": fit_breakdown,
        "phase": "done",
    }
