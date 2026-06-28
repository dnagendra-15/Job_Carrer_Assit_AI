import "dotenv/config";
import express from "express";
import cors from "cors";
import multer from "multer";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { parsePdf, countPages } from "./lib/pdf-parser.js";
import { fetchJdFromUrl } from "./lib/jd-fetcher.js";
import { callGemini } from "./lib/gemini.js";
import { textToDocx, textToPdf } from "./lib/doc-exporter.js";
import * as prompts from "./lib/prompts.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 10 * 1024 * 1024 } });

app.use(cors());
app.use(express.json());

// ── In-memory session store ──────────────────────────────────────────────────
const sessions = new Map();

function getSession(sessionId) {
  return sessions.get(sessionId) || null;
}

function createSession(sessionId, data) {
  sessions.set(sessionId, { ...data, createdAt: Date.now() });
  return sessions.get(sessionId);
}

function updateSession(sessionId, updates) {
  const session = sessions.get(sessionId);
  if (!session) return null;
  Object.assign(session, updates);
  return session;
}

// Clean up sessions older than 2 hours
setInterval(() => {
  const cutoff = Date.now() - 2 * 60 * 60 * 1000;
  for (const [id, s] of sessions) {
    if (s.createdAt < cutoff) sessions.delete(id);
  }
}, 10 * 60 * 1000);

// ── Health ───────────────────────────────────────────────────────────────────
app.get("/health", (req, res) => res.json({ status: "ok" }));

// ── POST /api/analyze ────────────────────────────────────────────────────────
app.post("/api/analyze", upload.single("resume"), async (req, res) => {
  try {
    const sessionId = req.headers["x-session-id"];
    if (!sessionId || sessionId.length < 10) {
      return res.status(400).json({ detail: "Missing X-Session-ID header" });
    }

    const jdUrl = req.body.jd_url;
    if (!jdUrl || !jdUrl.startsWith("http")) {
      return res.status(400).json({ detail: "Please provide a valid URL starting with http:// or https://" });
    }

    if (!req.file) {
      return res.status(400).json({ detail: "Please upload a PDF file" });
    }

    if (!req.file.originalname.toLowerCase().endsWith(".pdf")) {
      return res.status(400).json({ detail: "Please upload a PDF file" });
    }

    const pdfBuffer = req.file.buffer;
    const resumeText = await parsePdf(pdfBuffer);
    if (resumeText.trim().length < 100) {
      return res.status(400).json({ detail: "Could not extract text from PDF. Is it a scanned image?" });
    }
    const pages = await countPages(pdfBuffer);

    // Fetch JD
    let rawJdText;
    try {
      rawJdText = await fetchJdFromUrl(jdUrl);
    } catch (err) {
      return res.status(400).json({ detail: `Could not fetch job listing: ${err.message}` });
    }

    // Parse JD with Gemini
    const jdParseResult = await callGemini(prompts.jdParserPrompt(rawJdText), "jd_parser");
    let jdText = rawJdText, jdTitle = "Role", jdCompany = "Company";
    try {
      const parsed = JSON.parse(jdParseResult);
      jdText = parsed.description || rawJdText;
      jdTitle = parsed.title || "Role";
      jdCompany = parsed.company || "Company";
    } catch {}

    // Analyze gaps
    const gapResult = await callGemini(prompts.gapAnalyzerPrompt(resumeText, jdText, jdTitle, jdCompany), "gap_analyzer");
    let gaps = [];
    try {
      let text = gapResult.trim();
      if (text.startsWith("```")) {
        text = text.split("```")[1];
        if (text.startsWith("json")) text = text.slice(4);
      }
      const data = JSON.parse(text.trim());
      gaps = (data.gaps || []).map((g) => ({
        skill: g.skill,
        jdRequirement: g.jd_requirement,
        resumeCoverage: g.resume_coverage || "none",
        question: g.question,
        userAnswer: null,
        addressed: false,
      }));
    } catch {}

    const initialMsg = {
      role: "assistant",
      content: `I've reviewed your resume against the **${jdTitle}** role at **${jdCompany}**. ` +
        (gaps.length > 0
          ? `I found ${gaps.length} area${gaps.length !== 1 ? "s" : ""} where I'd like to learn more to tailor your application. Let's go through them — your answers will help me write a much stronger resume and cover letter.`
          : "Great news — your resume is already a strong match! I'll go ahead and generate your tailored resume and cover letter."),
    };

    const phase = gaps.length > 0 ? "chatting" : "generating";
    const session = createSession(sessionId, {
      resumeText,
      jdUrl,
      jdText,
      jdTitle,
      jdCompany,
      gaps,
      chatHistory: [initialMsg],
      userInfoGathered: "",
      resumeOutput: "",
      coverLetterOutput: "",
      fitScore: 0,
      fitBreakdown: {},
      fitRecommendation: "",
      phase,
      currentGapIndex: 0,
    });

    if (phase === "generating") {
      await runGeneration(sessionId);
      const s = getSession(sessionId);
      return res.json({
        status: "done",
        session_id: sessionId,
        jd_title: jdTitle,
        jd_company: jdCompany,
        resume_pages: pages,
        chat_history: s.chatHistory,
        fit_score: s.fitScore,
        fit_breakdown: s.fitBreakdown,
        fit_recommendation: s.fitRecommendation,
        resume_output: s.resumeOutput,
        cover_letter_output: s.coverLetterOutput,
      });
    }

    const nextQuestion = gaps[0]?.question || "Tell me more about your relevant experience.";
    return res.json({
      status: "chatting",
      session_id: sessionId,
      jd_title: jdTitle,
      jd_company: jdCompany,
      resume_pages: pages,
      chat_history: session.chatHistory,
      next_question: nextQuestion,
    });
  } catch (err) {
    console.error("Analyze error:", err);
    return res.status(500).json({ detail: "Internal server error. Please try again." });
  }
});

// ── POST /api/chat ───────────────────────────────────────────────────────────
app.post("/api/chat", async (req, res) => {
  try {
    const sessionId = req.headers["x-session-id"];
    if (!sessionId || sessionId.length < 10) {
      return res.status(400).json({ detail: "Missing X-Session-ID header" });
    }

    const session = getSession(sessionId);
    if (!session) {
      return res.status(400).json({ detail: "No active session. Please start a new analysis." });
    }

    const { message } = req.body;
    if (!message) {
      return res.status(400).json({ detail: "Message is required." });
    }

    const { gaps, currentGapIndex } = session;

    // Check if we're in confirmation phase (all gaps answered)
    const unanswered = gaps.filter((g) => !g.addressed);
    if (unanswered.length === 0 && session.phase === "confirming") {
      session.chatHistory.push({ role: "user", content: message });
      session.phase = "generating";
      updateSession(sessionId, session);

      await runGeneration(sessionId);
      const s = getSession(sessionId);
      return res.json({
        status: "done",
        chat_history: s.chatHistory,
        fit_score: s.fitScore,
        fit_breakdown: s.fitBreakdown,
        fit_recommendation: s.fitRecommendation,
        resume_output: s.resumeOutput,
        cover_letter_output: s.coverLetterOutput,
      });
    }

    // Record answer for current gap
    const currentGap = gaps[currentGapIndex];
    if (currentGap && !currentGap.addressed) {
      currentGap.userAnswer = message;
      currentGap.addressed = true;
      session.userInfoGathered += `\n${currentGap.skill}: ${message}`;
      session.chatHistory.push(
        { role: "assistant", content: currentGap.question },
        { role: "user", content: message },
        { role: "assistant", content: "Got it, thanks for sharing that." }
      );
      session.currentGapIndex = currentGapIndex + 1;
    }

    // Check if there are more gaps
    const nextUnanswered = gaps.filter((g) => !g.addressed);
    if (nextUnanswered.length > 0) {
      const nextQuestion = nextUnanswered[0].question;
      updateSession(sessionId, session);
      return res.json({
        status: "chatting",
        chat_history: session.chatHistory,
        next_question: nextQuestion,
      });
    }

    // All gaps answered - show confirmation
    const gathered = gaps
      .filter((g) => g.userAnswer)
      .map((g) => `- ${g.skill}: ${g.userAnswer}`)
      .join("\n");
    const confirmMsg =
      "Here's what I'll include in your tailored resume and cover letter:\n\n" +
      gathered +
      "\n\nType **yes** to generate your updated resume and cover letter, or share anything else you'd like me to add.";

    session.chatHistory.push({ role: "assistant", content: confirmMsg });
    session.phase = "confirming";
    updateSession(sessionId, session);

    return res.json({
      status: "chatting",
      chat_history: session.chatHistory,
      next_question: confirmMsg,
    });
  } catch (err) {
    console.error("Chat error:", err);
    return res.status(500).json({ detail: "Internal server error." });
  }
});

// ── GET /api/results/:sessionId ──────────────────────────────────────────────
app.get("/api/results/:sessionId", (req, res) => {
  const session = getSession(req.params.sessionId);
  if (!session) return res.status(404).json({ detail: "Session not found" });
  if (session.phase !== "done") return res.status(400).json({ detail: "Analysis not complete yet" });
  return res.json({
    resume_output: session.resumeOutput,
    cover_letter_output: session.coverLetterOutput,
    fit_score: session.fitScore,
    fit_breakdown: session.fitBreakdown,
    fit_recommendation: session.fitRecommendation,
    jd_title: session.jdTitle,
    jd_company: session.jdCompany,
  });
});

// ── GET /api/export/:sessionId/:docType ──────────────────────────────────────
app.get("/api/export/:sessionId/:docType", async (req, res) => {
  const { sessionId, docType } = req.params;
  const format = req.query.format || "docx";

  if (!["resume", "cover-letter"].includes(docType)) {
    return res.status(400).json({ detail: "docType must be 'resume' or 'cover-letter'" });
  }

  const session = getSession(sessionId);
  if (!session) return res.status(404).json({ detail: "Session not found" });

  const text = docType === "resume" ? session.resumeOutput : session.coverLetterOutput;
  if (!text) return res.status(404).json({ detail: "Document not generated yet" });

  const company = (session.jdCompany || "company").replace(/\s+/g, "_");
  const baseName = `${docType}_${company}`;

  try {
    if (format === "pdf") {
      const pdfBytes = await textToPdf(text);
      res.setHeader("Content-Type", "application/pdf");
      res.setHeader("Content-Disposition", `attachment; filename=${baseName}.pdf`);
      return res.send(Buffer.from(pdfBytes));
    } else {
      const docxBytes = await textToDocx(text);
      res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
      res.setHeader("Content-Disposition", `attachment; filename=${baseName}.docx`);
      return res.send(Buffer.from(docxBytes));
    }
  } catch (err) {
    console.error("Export error:", err);
    return res.status(500).json({ detail: "Failed to generate document." });
  }
});

// ── Generation helper ────────────────────────────────────────────────────────
async function runGeneration(sessionId) {
  const session = getSession(sessionId);
  const { resumeText, jdText, jdTitle, jdCompany, userInfoGathered } = session;

  const extraContext = userInfoGathered
    ? `\n\nADDITIONAL CONTEXT PROVIDED BY CANDIDATE:\n${userInfoGathered}`
    : "";

  // Resume writer
  const resumeOutput = await callGemini(
    prompts.resumeWriterPrompt(resumeText, jdText, jdTitle, jdCompany, extraContext),
    "resume_writer"
  );

  // Cover letter writer
  const coverOutput = await callGemini(
    prompts.coverLetterPrompt(resumeText, jdText, jdTitle, jdCompany, extraContext),
    "cover_letter_writer"
  );

  // Fit scorer
  const scoreRaw = await callGemini(
    prompts.fitScorerPrompt(resumeText, jdText, extraContext),
    "fit_scorer"
  );
  let scoreData = {
    overall_score: 7,
    breakdown: { technical_skills: 7, experience_level: 7, culture_and_values: 7 },
    recommendation: "Good Fit",
    summary: "Fit analysis could not be computed.",
  };
  try {
    let text = scoreRaw.trim();
    if (text.startsWith("```")) {
      text = text.split("```")[1];
      if (text.startsWith("json")) text = text.slice(4);
    }
    scoreData = JSON.parse(text.trim());
  } catch {}

  const doneMsg = {
    role: "assistant",
    content: `Your application kit is ready! Overall fit score: **${scoreData.overall_score}/10 — ${scoreData.recommendation}**. Your updated resume and cover letter are below. You can download either as a Word or PDF document.`,
  };

  updateSession(sessionId, {
    resumeOutput,
    coverLetterOutput: coverOutput,
    fitScore: scoreData.overall_score || 7,
    fitBreakdown: scoreData.breakdown || {},
    fitRecommendation: scoreData.recommendation || "Good Fit",
    chatHistory: [...session.chatHistory, doneMsg],
    phase: "done",
  });
}

// ── Start server ─────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 8001;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
