import * as cheerio from "cheerio";

const HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
};

export async function fetchJdFromUrl(url) {
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    throw new Error("URL must start with http:// or https://");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  let resp;
  try {
    resp = await fetch(url, { headers: HEADERS, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") throw new Error("URL timed out after 15 seconds");
    throw new Error("Could not connect to that URL");
  } finally {
    clearTimeout(timeout);
  }

  if (!resp.ok) {
    throw new Error(`URL returned HTTP ${resp.status}`);
  }

  const html = await resp.text();
  const $ = cheerio.load(html);

  $("script, style, nav, footer, header").remove();

  const main =
    $("article").first() ||
    $("main").first() ||
    $('[class*="job-description"], [class*="job_description"], [class*="description"], [class*="content"], [class*="posting"]').first() ||
    $("body").first();

  let text = (main.length ? main.text() : $.root().text()) || "";
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l);
  const cleaned = lines.join("\n");
  return cleaned.slice(0, 6000);
}
