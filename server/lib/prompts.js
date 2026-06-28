export function jdParserPrompt(rawText) {
  return `Extract from this job posting:
1. Job title (exact string from posting)
2. Company name
3. Clean job description (remove navigation, cookie notices, ads — keep only the actual job content)

Job posting text:
${rawText}

Respond in JSON only, no markdown:
{"title": "...", "company": "...", "description": "..."}`;
}

export function gapAnalyzerPrompt(resumeText, jdText, jdTitle, jdCompany) {
  return `You are a senior recruiter analyzing a job application.

RESUME:
${resumeText}

JOB DESCRIPTION for ${jdTitle} at ${jdCompany}:
${jdText}

Identify the 3-5 most important gaps — skills, experiences, or qualifications that:
- The JD explicitly requires or strongly prefers
- Are NOT clearly demonstrated in the resume (missing or only partially covered)

Focus on gaps that the candidate MIGHT actually have but hasn't documented (don't ask about impossible things like 10 years experience for a junior role).

For each gap, generate a natural, friendly conversational question to ask the candidate.

Respond in JSON only, no markdown:
{
  "gaps": [
    {
      "skill": "skill/experience name",
      "jd_requirement": "what the JD says",
      "resume_coverage": "none OR partial",
      "question": "conversational question for the candidate, referencing the specific JD need"
    }
  ]
}

If there are NO meaningful gaps (resume is a strong match), return: {"gaps": []}`;
}

export function resumeWriterPrompt(resumeText, jdText, jdTitle, jdCompany, extraContext) {
  return `You are an expert resume writer specialising in ATS optimisation. Never fabricate experience.

ORIGINAL RESUME:
${resumeText}

JOB DESCRIPTION for ${jdTitle} at ${jdCompany}:
${jdText}
${extraContext}

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
(list all significant rewrites)`;
}

export function coverLetterPrompt(resumeText, jdText, jdTitle, jdCompany, extraContext) {
  return `Write a compelling 1-page cover letter.

RESUME:
${resumeText}

JOB: ${jdTitle} at ${jdCompany}

JOB DESCRIPTION:
${jdText}
${extraContext}

Format:
[Date]

Hiring Manager
${jdCompany}

Dear Hiring Manager,

[Opening — 2-3 sentences: specific hook about this role/company]

[Body para 1 — top 2-3 matching strengths with specific examples from the resume]

[Body para 2 — address the most important gap: show self-awareness + growth plan]

[Closing — call to action]

Sincerely,
[Candidate Name from resume]

Tone: Confident, specific, human. No cliches like "I am writing to apply" or "I am a quick learner".`;
}

export function fitScorerPrompt(resumeText, jdText, extraContext) {
  return `Score this candidate's fit for the role 1-10 across three dimensions.

RESUME:
${resumeText.slice(0, 2000)}

JOB DESCRIPTION:
${jdText.slice(0, 2000)}
${extraContext}

Respond in JSON only:
{
  "overall_score": 7,
  "breakdown": {
    "technical_skills": 8,
    "experience_level": 6,
    "culture_and_values": 7
  },
  "recommendation": "Good Fit",
  "summary": "2-sentence honest summary of fit"
}

Recommendation must be one of: "Strong Fit" (8-10) / "Good Fit" (6-7) / "Possible Fit" (4-5) / "Poor Fit" (1-3)`;
}
