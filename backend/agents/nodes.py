import json
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config.models_config import get_llm
from backend.agents.state import PipelineState
from backend.agents import prompts


def parse_jd_node(state: PipelineState) -> dict:
    llm = get_llm("jd_parser")
    messages = [
        SystemMessage(content=prompts.JD_PARSER_SYSTEM),
        HumanMessage(content=prompts.JD_PARSER_HUMAN.format(jd_text=state["jd_text"]))
    ]
    response = llm.invoke(messages)
    return {"jd_summary": response.content}


def analyze_gaps_node(state: PipelineState) -> dict:
    llm = get_llm("gap_analyzer")
    messages = [
        SystemMessage(content=prompts.GAP_ANALYZER_SYSTEM),
        HumanMessage(content=prompts.GAP_ANALYZER_HUMAN.format(
            jd_summary=state["jd_summary"],
            resume_text=state["resume_text"]
        ))
    ]
    response = llm.invoke(messages)
    try:
        gaps = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            gaps = json.loads(content[start:end])
        else:
            gaps = [{"requirement": "Could not parse gaps", "candidate_status": "Unknown", "severity": "MEDIUM", "category": "technical"}]
    return {"gaps": gaps}


def generate_questions_node(state: PipelineState) -> dict:
    llm = get_llm("question_generator")
    messages = [
        SystemMessage(content=prompts.QUESTION_GENERATOR_SYSTEM),
        HumanMessage(content=prompts.QUESTION_GENERATOR_HUMAN.format(
            gaps=json.dumps(state["gaps"], indent=2),
            resume_text=state["resume_text"]
        ))
    ]
    response = llm.invoke(messages)
    try:
        questions = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            questions = json.loads(content[start:end])
        else:
            questions = [{"id": "q1", "question": "Tell us more about your relevant experience.", "gap_reference": "general", "hint": "Describe any related projects or skills."}]

    user_answers = interrupt({"questions": questions})
    return {"questions": questions, "user_answers": user_answers}


def write_resume_node(state: PipelineState) -> dict:
    llm = get_llm("resume_writer")
    answers_text = state.get("user_answers", "")
    if isinstance(answers_text, dict): 
         answers_text = "\n".join([f"{k}: {v}" for k, v in answers_text.items()])

    messages = [
        SystemMessage(content=prompts.RESUME_WRITER_SYSTEM),
        HumanMessage(content=prompts.RESUME_WRITER_HUMAN.format(
            jd_summary=state["jd_summary"],
            resume_text=state["resume_text"],
            answers=answers_text or "No additional context provided."
        ))
    ]
    response = llm.invoke(messages)
    return {"tailored_resume": response.content}


def write_cover_letter_node(state: PipelineState) -> dict:
    llm = get_llm("cover_letter_writer")
    answers_text = state.get("user_answers", "")
    if isinstance(answers_text, dict): 
        answers_text = "\n".join([f"{k}: {v}" for k, v in answers_text.items()])

    messages = [
        SystemMessage(content=prompts.COVER_LETTER_SYSTEM),
        HumanMessage(content=prompts.COVER_LETTER_HUMAN.format(
            jd_summary=state["jd_summary"],
            resume_text=state["resume_text"],
            answers=answers_text or "No additional context provided."
        ))
    ]
    response = llm.invoke(messages)
    return {"cover_letter": response.content}


def score_fit_node(state: PipelineState) -> dict:
    llm = get_llm("fit_scorer")
    messages = [
        SystemMessage(content=prompts.FIT_SCORER_SYSTEM),
        HumanMessage(content=prompts.FIT_SCORER_HUMAN.format(
            jd_summary=state["jd_summary"],
            tailored_resume=state["tailored_resume"],
            resume_text=state["resume_text"]
        ))
    ]
    response = llm.invoke(messages)
    try:
        score = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            score = json.loads(content[start:end])
        else:
            score = {"overall_score": 0, "overall_rationale": "Could not parse score", "categories": []}
    return {"fit_score": score}
