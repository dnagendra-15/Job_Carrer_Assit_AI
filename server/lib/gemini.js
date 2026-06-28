import { GoogleGenerativeAI } from "@google/generative-ai";

let genAI = null;

function getClient() {
  if (!genAI) {
    const apiKey = process.env.GOOGLE_API_KEY;
    if (!apiKey) {
      throw new Error("GOOGLE_API_KEY environment variable is not set");
    }
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

const MODEL_CONFIG = {
  jd_parser: { model: "gemini-2.0-flash", temperature: 0.1 },
  gap_analyzer: { model: "gemini-2.0-flash", temperature: 0.3 },
  resume_writer: { model: "gemini-2.0-flash", temperature: 0.4 },
  cover_letter_writer: { model: "gemini-2.0-flash", temperature: 0.5 },
  fit_scorer: { model: "gemini-2.0-flash", temperature: 0.2 },
};

export async function callGemini(prompt, taskName) {
  const config = MODEL_CONFIG[taskName] || MODEL_CONFIG.jd_parser;
  const client = getClient();
  const model = client.getGenerativeModel({
    model: config.model,
    generationConfig: { temperature: config.temperature, maxOutputTokens: 8192 },
  });

  const result = await model.generateContent(prompt);
  const response = result.response;
  return response.text();
}
