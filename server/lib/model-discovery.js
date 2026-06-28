const PROVIDER_CONFIGS = {
  google: {
    envKey: "GOOGLE_API_KEY",
    listUrl: (key) => `https://generativelanguage.googleapis.com/v1beta/models?key=${key}`,
    parseModels: (data) =>
      (data.models || [])
        .filter((m) => m.supportedGenerationMethods?.includes("generateContent"))
        .map((m) => ({
          id: m.name.replace("models/", ""),
          displayName: m.displayName || m.name,
          inputTokenLimit: m.inputTokenLimit || 0,
        })),
    preferences: {
      fast: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
      quality: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
    },
  },
  openai: {
    envKey: "OPENAI_API_KEY",
    listUrl: () => "https://api.openai.com/v1/models",
    headers: (key) => ({ Authorization: `Bearer ${key}` }),
    parseModels: (data) =>
      (data.data || []).map((m) => ({
        id: m.id,
        displayName: m.id,
        owned_by: m.owned_by,
      })),
    preferences: {
      fast: ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4.1-nano", "gpt-3.5-turbo"],
      quality: ["gpt-4.1", "gpt-4o", "gpt-4.1-mini", "gpt-4o-mini"],
    },
  },
  anthropic: {
    envKey: "ANTHROPIC_API_KEY",
    listUrl: () => "https://api.anthropic.com/v1/models",
    headers: (key) => ({ "x-api-key": key, "anthropic-version": "2023-06-01" }),
    parseModels: (data) =>
      (data.data || []).map((m) => ({
        id: m.id,
        displayName: m.display_name || m.id,
      })),
    preferences: {
      fast: ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
      quality: ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
    },
  },
  xai: {
    envKey: "XAI_API_KEY",
    listUrl: () => "https://api.x.ai/v1/models",
    headers: (key) => ({ Authorization: `Bearer ${key}` }),
    parseModels: (data) =>
      (data.data || data.models || []).map((m) => ({
        id: m.id,
        displayName: m.id,
      })),
    preferences: {
      fast: ["grok-3-mini-fast", "grok-3-mini", "grok-2"],
      quality: ["grok-3", "grok-3-mini", "grok-2"],
    },
  },
};

const TASK_TYPE_MAP = {
  jd_parser: "fast",
  gap_analyzer: "quality",
  resume_writer: "quality",
  cover_letter_writer: "quality",
  fit_scorer: "fast",
};

const PROVIDER_PRIORITY = ["google", "openai", "anthropic", "xai"];

let discoveredModels = {};
let selectedConfig = {};
let discoveryComplete = false;

export async function discoverModels() {
  console.log("[Model Discovery] Checking available providers...");
  discoveredModels = {};

  const checks = PROVIDER_PRIORITY.map(async (provider) => {
    const config = PROVIDER_CONFIGS[provider];
    const apiKey = process.env[config.envKey];
    if (!apiKey) {
      console.log(`  [${provider}] No API key found (${config.envKey})`);
      return;
    }

    try {
      const url = config.listUrl(apiKey);
      const headers = config.headers ? config.headers(apiKey) : {};
      const resp = await fetch(url, { headers, signal: AbortSignal.timeout(10000) });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        console.log(`  [${provider}] API returned ${resp.status}: ${errText.slice(0, 100)}`);
        return;
      }

      const data = await resp.json();
      const models = config.parseModels(data);
      discoveredModels[provider] = models;
      console.log(`  [${provider}] Found ${models.length} models`);
    } catch (err) {
      console.log(`  [${provider}] Discovery failed: ${err.message}`);
    }
  });

  await Promise.all(checks);
  selectBestModels();
  discoveryComplete = true;
  console.log("[Model Discovery] Complete. Selected models:");
  for (const [task, cfg] of Object.entries(selectedConfig)) {
    console.log(`  ${task}: ${cfg.provider}/${cfg.model}`);
  }
  return selectedConfig;
}

function selectBestModels() {
  selectedConfig = {};

  for (const [task, type] of Object.entries(TASK_TYPE_MAP)) {
    let found = false;
    for (const provider of PROVIDER_PRIORITY) {
      if (!discoveredModels[provider]) continue;

      const config = PROVIDER_CONFIGS[provider];
      const prefs = config.preferences[type];
      const availableIds = discoveredModels[provider].map((m) => m.id);

      for (const preferred of prefs) {
        const match = availableIds.find((id) => id.startsWith(preferred) || id === preferred);
        if (match) {
          selectedConfig[task] = { provider, model: match };
          found = true;
          break;
        }
      }
      if (found) break;
    }

    if (!found) {
      selectedConfig[task] = { provider: "google", model: "gemini-2.0-flash" };
    }
  }
}

export function getSelectedModel(taskName) {
  return selectedConfig[taskName] || { provider: "google", model: "gemini-2.0-flash" };
}

export function getDiscoveredModels() {
  return discoveredModels;
}

export function getSelectedConfig() {
  return selectedConfig;
}

export function isDiscoveryComplete() {
  return discoveryComplete;
}
