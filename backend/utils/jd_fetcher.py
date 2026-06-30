import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_jd_from_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.Timeout:
        raise RuntimeError("URL timed out after 15 seconds")
    except requests.ConnectionError:
        raise RuntimeError("Could not connect to that URL")
    except requests.HTTPError as e:
        raise RuntimeError(f"URL returned HTTP {e.response.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    main = (
        soup.find("article") or
        soup.find("main") or
        soup.find(attrs={"class": lambda c: c and any(
            k in str(c).lower() for k in ["job-description", "job_description", "description", "content", "posting"]
        )}) or
        soup.find("body")
    )

    text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    return cleaned[:6000]
