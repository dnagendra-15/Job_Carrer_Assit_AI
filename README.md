# Job Application Co-Pilot

IIT Roorkee SE Capstone - Module 6 - Project 02

## What it does

Upload your resume PDF + paste a job listing URL. The AI fetches the JD,
identifies skill gaps, then has a conversation with you to gather context.
After you confirm, it generates a tailored resume, cover letter, and fit score.
No login required -- sessions are tracked by a browser UUID.

## Live Demo

- App: [your-app.onrender.com -- fill in after deploy]
- API docs: [your-app.onrender.com/docs -- Swagger UI]

## Tech Stack

| Layer | Tool |
|---|---|
| Frontend | Vanilla HTML/CSS/JS |
| Backend | FastAPI + Uvicorn |
| Pipeline | LangGraph (StateGraph + SqliteSaver + interrupt()) |
| Models | Groq llama-3.3-70b / llama-3.1-8b (configurable) |
| PDF parse | pypdf |
| Export | python-docx |
| Session | UUID in browser localStorage |

## How to switch LLM models

Edit `backend/config/models_config.py`. Change any node's `provider` and `model`.
No other code changes needed.

## Local setup

```bash
git clone your-repo
cd job-copilot
cp .env.example .env
# Add your GROQ_API_KEY in .env
pip install -r requirements.txt
uvicorn backend.main:app --reload
# Open http://localhost:8000
```

## LangGraph pipeline phases

1. `fetch_jd` -- scrapes URL, extracts JD text/title/company
2. `analyze` -- gaps analysis (resume vs JD)
3. `chat_questioner` -- interrupt loop, one question per gap
4. `generate` -- resume + cover letter + fit score

## Deploy to Render

1. Push to GitHub
2. render.com -> New Web Service -> connect repo
3. Render auto-reads render.yaml
4. Add GROQ_API_KEY in Render env vars panel
5. Deploy -> get public URL

## Submission checklist

- [ ] Video walkthrough: upload PDF -> paste URL -> chat -> confirm -> show results
- [ ] Slides: problem, LangGraph flow diagram, what works, what's next
- [ ] Live URL on Render
- [ ] GitHub repo with this README
- [ ] /docs Swagger link in README
