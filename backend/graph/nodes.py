import json
from langchain_core.messages import HumanMessage, SystemMessage
from .state import AppState, Gap, ChatMessage
from backend.config.models_config import get_llm
from backend.utils.jd_fetcher import fetch_jd_from_url


# ── NODE 1: fetch_jd_node ──────────────────────────────────────────────────
def fetch_jd_node(state: AppState) -> dict:
    """Fetch job description from URL and extract structured info."""
    try:
        raw_text = fetch_jd_from_url(state["jd_url"])
    except Exception as e:
        return {"error": str(e), "phase": "done"}

    llm = get_llm("jd_parser")
    prompt = f"""Extract from this job posting:
1. Job title (exact string from posting)
2. Company name
3. Clean job description (remove navigation, cookie notices, ads — keep only the actual job content)

Job posting text:
{raw_text}

Respond in JSON only, no markdown:
{{"title": "...", "company": "...", "description": "..."}}"""

    response = llm.invoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(response.content)
        return {
            "jd_text": data.get("description", raw_text),
            "jd_title": data.get("title", "Unknown Role"),
            "jd_company": data.get("company", "Unknown Company"),
            "phase": "analyzing"
        }
    except json.JSONDecodeError:
        return {
            "jd_text": raw_text,
            "jd_title": "Role",
            "jd_company": "Company",
            "phase": "analyzing"
        }


# ── NODE 2: analyze_node ──────────────────────────────────────────────────
def analyze_node(state: AppState) -> dict:
    """Identify the most important gaps between resume and JD."""
    llm = get_llm("gap_analyzer")

    prompt = f"""You are a senior recruiter analyzing a job application.

RESUME:
{state["resume_text"]}

JOB DESCRIPTION for {state["jd_title"]} at {state["jd_company"]}:
{state["jd_text"]}

Identify the 3-5 most important gaps — skills, experiences, or qualifications that:
- The JD explicitly requires or strongly prefers
- Are NOT clearly demonstrated in the resume (missing or only partially covered)

Focus on gaps that the candidate MIGHT actually have but hasn't documented (don't ask about impossible things like 10 years experience for a junior role).

For each gap, generate a natural, friendly conversational question to ask the candidate.

Respond in JSON only, no markdown:
{{
  "gaps": [
    {{
      "skill": "skill/experience name",
      "jd_requirement": "what the JD says",
      "resume_coverage": "none OR partial",
      "question": "conversational question for the candidate, referencing the specific JD need"
    }}
  ]
}}

If there are NO meaningful gaps (resume is a strong match), return: {{"gaps": []}}"""

    response = llm.invoke([HumanMessage(content=prompt)])
    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        gaps_raw = data.get("gaps", [])
        gaps = [
            Gap(
                skill=g["skill"],
                jd_requirement=g["jd_requirement"],
                resume_coverage=g.get("resume_coverage", "none"),
                question=g["question"],
                user_answer=None,
                addressed=False
            )
            for g in gaps_raw
        ]
    except (json.JSONDecodeError, KeyError):
        gaps = []

    initial_msg: ChatMessage = {
        "role": "assistant",
        "content": (
            f"I've reviewed your resume against the **{state['jd_title']}** role at **{state['jd_company']}**. "
            + (
                f"I found {len(gaps)} area{'s' if len(gaps) != 1 else ''} where I'd like to learn more to tailor your application. "
                "Let's go through them — your answers will help me write a much stronger resume and cover letter."
                if gaps else
                "Great news — your resume is already a strong match! I'll go ahead and generate your tailored resume and cover letter."
            )
        )
    }

    return {
        "gaps": gaps,
        "chat_history": [initial_msg],
        "phase": "chatting" if gaps else "generating"
    }


# ── NODE 3: chat_questioner ──────────────────────────────────────────────────
def chat_questioner(state: AppState) -> dict:
    """
    Core conversation node. Uses LangGraph interrupt() to pause and wait for user.
    Loops until all gaps addressed, then moves to confirm phase.
    """
    from langgraph.types import interrupt

    gaps = state["gaps"]
    unanswered = [g for g in gaps if not g["addressed"]]

    if not unanswered:
        gathered_summary = "\n".join([
            f"\u2022 {g['skill']}: {g['user_answer']}"
            for g in gaps if g["user_answer"]
        ])
        confirm_msg = (
            "Here's what I'll include in your tailored resume and cover letter:\n\n"
            + gathered_summary
            + "\n\nType **yes** to generate your updated resume and cover letter, or share anything else you'd like me to add."
        )

        user_input: str = interrupt(confirm_msg)

        return {
            "is_generation_confirmed": True,
            "chat_history": [
                {"role": "assistant", "content": confirm_msg},
                {"role": "user", "content": user_input}
            ],
            "phase": "generating"
        }
    else:
        current_gap = unanswered[0]
        question = current_gap["question"]

        user_input: str = interrupt(question)

        gap_idx = next(i for i, g in enumerate(gaps) if g["skill"] == current_gap["skill"])
        gaps[gap_idx]["user_answer"] = user_input
        gaps[gap_idx]["addressed"] = True

        ack = "Got it, thanks for sharing that."

        return {
            "gaps": gaps,
            "user_info_gathered": state.get("user_info_gathered", "") + f"\n{current_gap['skill']}: {user_input}",
            "chat_history": [
                {"role": "assistant", "content": question},
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": ack}
            ],
            "phase": "chatting"
        }


# ── NODE 4: generate_node ──────────────────────────────────────────────────
def generate_node(state: AppState) -> dict:
    """Generate resume, cover letter, and fit score in sequence."""

    extra_context = ""
    if state.get("user_info_gathered"):
        extra_context = f"\n\nADDITIONAL CONTEXT PROVIDED BY CANDIDATE (use this in the resume):\n{state['user_info_gathered']}"

    resume_text = state["resume_text"]
    jd_text = state["jd_text"]
    jd_title = state["jd_title"]
    jd_company = state["jd_company"]

    # ── Resume writer ──
    resume_llm = get_llm("resume_writer")
    resume_prompt = f"""You are an expert resume writer specialising in ATS optimisation.

ORIGINAL RESUME:
{resume_text}

JOB DESCRIPTION for {jd_title} at {jd_company}:
{jd_text}
{extra_context}

INSTRUCTIONS:
1. Write a tailored professional summary (3-4 sentences) using the JD's language
2. Strengthen all experience bullet points: action verbs + quantifiable impact where implied + JD keywords woven in naturally
3. Include the additional context from the candidate chat — weave it into the experience/skills sections naturally
4. NEVER invent experience, dates, or job titles not in the original resume
5. Reorder skills to match JD priorities

Output the FULL rewritten resume in clean markdown.
Then add a section:
## WHAT I CHANGED
- [bullet: specific change and why]
(list all significant rewrites)"""

    resume_response = resume_llm.invoke([
        SystemMessage(content="You are an expert ATS-optimised resume writer. Never fabricate experience."),
        HumanMessage(content=resume_prompt)
    ])
    resume_output = resume_response.content

    # ── Cover letter writer ──
    cover_llm = get_llm("cover_letter_writer")
    cover_prompt = f"""Write a compelling 1-page cover letter.

RESUME:
{resume_text}

JOB: {jd_title} at {jd_company}

JOB DESCRIPTION:
{jd_text}
{extra_context}

Format:
[Date]

Hiring Manager
{jd_company}

Dear Hiring Manager,

[Opening — 2-3 sentences: specific hook about this role/company]

[Body para 1 — top 2-3 matching strengths with specific examples from the resume]

[Body para 2 — address the most important gap: show self-awareness + growth plan]

[Closing — call to action]

Sincerely,
[Candidate Name from resume]

Tone: Confident, specific, human. No clichés like "I am writing to apply" or "I am a quick learner"."""

    cover_response = cover_llm.invoke([HumanMessage(content=cover_prompt)])
    cover_output = cover_response.content

    # ── Fit scorer ──
    score_llm = get_llm("fit_scorer")
    score_prompt = f"""Score this candidate's fit for the role 1-10 across three dimensions.

RESUME:
{resume_text[:2000]}

JOB DESCRIPTION:
{jd_text[:2000]}
{extra_context}

Respond in JSON only:
{{
  "overall_score": 7,
  "breakdown": {{
    "technical_skills": 8,
    "experience_level": 6,
    "culture_and_values": 7
  }},
  "recommendation": "Good Fit",
  "summary": "2-sentence honest summary of fit"
}}

Recommendation must be one of: "Strong Fit" (8-10) / "Good Fit" (6-7) / "Possible Fit" (4-5) / "Poor Fit" (1-3)"""

    score_response = score_llm.invoke([HumanMessage(content=score_prompt)])
    try:
        score_text = score_response.content.strip()
        if score_text.startswith("```"):
            score_text = score_text.split("```")[1]
            if score_text.startswith("json"):
                score_text = score_text[4:]
        score_data = json.loads(score_text.strip())
    except Exception:
        score_data = {
            "overall_score": 7,
            "breakdown": {"technical_skills": 7, "experience_level": 7, "culture_and_values": 7},
            "recommendation": "Good Fit",
            "summary": "Fit analysis could not be computed."
        }

    done_msg: ChatMessage = {
        "role": "assistant",
        "content": (
            f"Your application kit is ready! "
            f"Overall fit score: **{score_data['overall_score']}/10 — {score_data['recommendation']}**. "
            "Your updated resume and cover letter are below. You can download either as a Word document."
        )
    }

    return {
        "resume_output": resume_output,
        "cover_letter_output": cover_output,
        "fit_score": score_data.get("overall_score", 7),
        "fit_breakdown": score_data.get("breakdown", {}),
        "fit_recommendation": score_data.get("recommendation", "Good Fit"),
        "chat_history": [done_msg],
        "phase": "done"
    }
