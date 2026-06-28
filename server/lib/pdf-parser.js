import pdf from "pdf-parse/lib/pdf-parse.js";

export async function parsePdf(buffer) {
  const data = await pdf(buffer);
  return data.text || "";
}

export async function countPages(buffer) {
  const data = await pdf(buffer);
  return data.numpages || 0;
}
