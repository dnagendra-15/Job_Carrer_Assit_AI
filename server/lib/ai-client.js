import { GoogleGenerativeAI } from "@google/generative-ai";
import { getSelectedModel, getDiscoveredModels } from "./model-discovery.js";

let googleClient = null;

function getGoogleClient() {
  if (!googleClient) {
    const apiKey = process.env.GOOGLE_API_KEY;
    if (!apiKey) throw new Error("GOOGLE_API_KEY not set");
    googleClient = new GoogleGenerativeAI(apiKey);
  }
  return googleClient;
}

async function callGoogle(prompt, modelId, temperature) {
  const client = getGoogleClient();
  const model = client.getGenerativeModel({
    model: modelId,
    generationConfig: { temperature, maxOutputTokens: 8192 },
  });
  const result = await model.generateContent(prompt);
  return result.response.text();
}

async function callOpenAI(prompt, modelId, temperature) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY not set");

  const resp = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: modelId,
      messages: [{ role: "user", content: prompt }],
      temperature,
      max_tokens: 8192,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`OpenAI API error ${resp.status}: ${err.slice(0, 200)}`);
  }
  const data = await resp.json();
  return data.choices[0].message.content;
}

async function callAnthropic(prompt, modelId, temperature) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: modelId,
      max_tokens: 8192,
      temperature,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Anthropic API error ${resp.status}: ${err.slice(0, 200)}`);
  }
  const data = await resp.json();
  return data.content[0].text;
}

async function callXAI(prompt, modelId, temperature) {
  const apiKey = process.env.XAI_API_KEY;
  if (!apiKey) throw new Error("XAI_API_KEY not set");

  const resp = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: modelId,
      messages: [{ role: "user", content: prompt }],
      temperature,
      max_tokens: 8192,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`xAI API error ${resp.status}: ${err.slice(0, 200)}`);
  }
  const data = await resp.json();
  return data.choices[0].message.content;
}

const TEMPERATURE_MAP = {
  jd_parser: 0.1,
  gap_analyzer: 0.3,
  resume_writer: 0.4,
  cover_letter_writer: 0.5,
  fit_scorer: 0.2,
};

const PROVIDER_CALLERS = {
  google: callGoogle,
  openai: callOpenAI,
  anthropic: callAnthropic,
  xai: callXAI,
};

const GOOGLE_FALLBACK_CHAIN = [
  "gemini-2.0-flash",
  "gemini-2.5-flash",
  "gemini-1.5-flash",
  "gemini-1.5-pro",
];

function isRetryable(err) {
  const msg = err.message || "";
  return msg.includes("429") || msg.includes("503") || msg.includes("overloaded") || msg.includes("quota") || msg.includes("high demand");
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function callAI(prompt, taskName) {
  const { provider, model } = getSelectedModel(taskName);
  const temperature = TEMPERATURE_MAP[taskName] || 0.3;
  const caller = PROVIDER_CALLERS[provider];

  if (!caller) {
    throw new Error(`Unknown provider: ${provider}`);
  }

  // Try the selected model first with retry
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await caller(prompt, model, temperature);
    } catch (err) {
      console.error(`[AI] ${provider}/${model} attempt ${attempt + 1} failed: ${err.message.slice(0, 120)}`);
      if (!isRetryable(err)) throw err;
      if (attempt === 0) await sleep(2000);
    }
  }

  // If Google provider failed, try fallback models
  if (provider === "google") {
    const discovered = getDiscoveredModels().google || [];
    const availableIds = discovered.map((m) => m.id);
    const fallbacks = GOOGLE_FALLBACK_CHAIN.filter((f) => f !== model && availableIds.includes(f));

    for (const fallbackModel of fallbacks) {
      try {
        console.log(`[AI] Trying fallback: google/${fallbackModel}`);
        return await callGoogle(prompt, fallbackModel, temperature);
      } catch (err) {
        console.error(`[AI] Fallback google/${fallbackModel} failed: ${err.message.slice(0, 80)}`);
        if (!isRetryable(err)) throw err;
      }
    }
  }

  // Try other available providers as last resort
  const availableProviders = Object.keys(getDiscoveredModels()).filter((p) => p !== provider);
  for (const altProvider of availableProviders) {
    const altCaller = PROVIDER_CALLERS[altProvider];
    const altModels = getDiscoveredModels()[altProvider];
    if (!altCaller || !altModels || altModels.length === 0) continue;
    const altModel = altModels[0].id;
    try {
      console.log(`[AI] Cross-provider fallback: ${altProvider}/${altModel}`);
      return await altCaller(prompt, altModel, temperature);
    } catch (err) {
      console.error(`[AI] Cross-provider ${altProvider}/${altModel} failed: ${err.message.slice(0, 80)}`);
    }
  }

  throw new Error("All AI providers are unavailable. Please check your API keys and quotas.");
}
