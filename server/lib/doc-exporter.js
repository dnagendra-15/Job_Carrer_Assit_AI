import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
} from "docx";
import PdfPrinter from "pdfmake";

export async function textToDocx(text) {
  const lines = text.split("\n");
  const paragraphs = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) {
      paragraphs.push(new Paragraph({ text: "" }));
    } else if (stripped.startsWith("### ")) {
      paragraphs.push(
        new Paragraph({ text: stripped.slice(4), heading: HeadingLevel.HEADING_3 })
      );
    } else if (stripped.startsWith("## ")) {
      paragraphs.push(
        new Paragraph({ text: stripped.slice(3), heading: HeadingLevel.HEADING_2 })
      );
    } else if (stripped.startsWith("# ")) {
      paragraphs.push(
        new Paragraph({ text: stripped.slice(2), heading: HeadingLevel.HEADING_1 })
      );
    } else if (stripped.startsWith("- ") || stripped.startsWith("* ")) {
      paragraphs.push(
        new Paragraph({
          children: [new TextRun(stripped.slice(2))],
          bullet: { level: 0 },
        })
      );
    } else {
      const runs = parseInlineFormatting(stripped);
      paragraphs.push(new Paragraph({ children: runs }));
    }
  }

  const doc = new Document({
    sections: [
      {
        properties: {
          page: {
            margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
          },
        },
        children: paragraphs,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  return buffer;
}

function parseInlineFormatting(text) {
  const runs = [];
  const boldRegex = /\*\*(.*?)\*\*/g;
  let lastIndex = 0;
  let match;

  while ((match = boldRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      runs.push(new TextRun(text.slice(lastIndex, match.index)));
    }
    runs.push(new TextRun({ text: match[1], bold: true }));
    lastIndex = boldRegex.lastIndex;
  }
  if (lastIndex < text.length) {
    runs.push(new TextRun(text.slice(lastIndex)));
  }
  if (runs.length === 0) {
    runs.push(new TextRun(text));
  }
  return runs;
}

export async function textToPdf(text) {
  const fonts = {
    Helvetica: {
      normal: "Helvetica",
      bold: "Helvetica-Bold",
      italics: "Helvetica-Oblique",
      bolditalics: "Helvetica-BoldOblique",
    },
  };

  const printer = new PdfPrinter(fonts);

  const lines = text.split("\n");
  const content = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) {
      content.push({ text: " ", fontSize: 11 });
    } else if (stripped.startsWith("# ")) {
      content.push({ text: stripped.slice(2), fontSize: 18, bold: true, margin: [0, 10, 0, 4] });
    } else if (stripped.startsWith("## ")) {
      content.push({ text: stripped.slice(3), fontSize: 14, bold: true, margin: [0, 8, 0, 3] });
    } else if (stripped.startsWith("### ")) {
      content.push({ text: stripped.slice(4), fontSize: 12, bold: true, margin: [0, 6, 0, 2] });
    } else if (stripped.startsWith("- ") || stripped.startsWith("* ")) {
      content.push({ ul: [{ text: stripped.slice(2), fontSize: 11 }] });
    } else {
      content.push({ text: stripped.replace(/\*\*(.*?)\*\*/g, "$1"), fontSize: 11 });
    }
  }

  const docDefinition = {
    content,
    defaultStyle: { font: "Helvetica" },
    pageMargins: [72, 72, 72, 72],
  };

  return new Promise((resolve, reject) => {
    const pdfDoc = printer.createPdfKitDocument(docDefinition);
    const chunks = [];
    pdfDoc.on("data", (chunk) => chunks.push(chunk));
    pdfDoc.on("end", () => resolve(Buffer.concat(chunks)));
    pdfDoc.on("error", reject);
    pdfDoc.end();
  });
}
