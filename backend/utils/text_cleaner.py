import re


def clean_resume_text(raw: str) -> str:
    """
    Normalize raw pypdf-extracted resume text into a compact, low-noise
    representation. Run this ONCE right after PDF parsing, then reuse the
    result everywhere downstream. This is the version that gets sent to
    every LLM node, so trimming noise here saves tokens on every single
    call in the pipeline, not just one.
    """
    if not raw:
        return raw

    lines = raw.splitlines()
    cleaned_lines = []

    page_artifact_re = re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if page_artifact_re.match(line):
            continue
        # collapse internal runs of whitespace pypdf sometimes leaves behind
        line = re.sub(r"[ \t]{2,}", " ", line)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # collapse 3+ blank-line-equivalents (shouldn't exist after the loop
    # above, but defensive against odd PDF extraction patterns)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
