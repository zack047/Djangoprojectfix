import os
import re
from typing import Optional

os.environ["TOKENIZERS_PARALLELISM"] = "false"

try:
    from transformers import pipeline
except Exception:
    pipeline = None

_summarizer: Optional[object] = None


def get_summarizer():
    """Lazy-load summarizer; return None if transformers/torch unavailable."""
    global _summarizer
    if _summarizer is not None:
        return _summarizer
    if pipeline is None:
        return None
    try:
        _summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            tokenizer="facebook/bart-large-cnn",
            device=-1,
        )
    except Exception:
        _summarizer = None
    return _summarizer


# ---------- URL PROTECTION HELPERS ----------
URL_RE = re.compile(r"(https?://[^\s]+)")


def protect_urls(text: str):
    urls = URL_RE.findall(text)
    mapping = {}
    safe_text = text
    for idx, url in enumerate(urls):
        token = f"URLTOKEN{idx}"
        mapping[token] = url
        safe_text = safe_text.replace(url, token)
    return safe_text, mapping


def restore_urls(text: str, mapping: dict):
    for token, url in mapping.items():
        text = text.replace(token, url)
    return text


def chunk_by_words(text: str, max_chars: int = 900):
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    for w in words:
        add_len = len(w) + (1 if current else 0)
        if current and current_len + add_len > max_chars:
            chunks.append(" ".join(current))
            current = [w]
            current_len = len(w)
        else:
            current.append(w)
            current_len += add_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def generate_ai_summary(text: str):
    if not text:
        return ""
    raw = text.strip()
    if len(raw) < 50:
        return raw

    summarizer_model = get_summarizer()
    if summarizer_model is None:
        return raw[:600]

    safe_text, url_map = protect_urls(raw)
    chunks = chunk_by_words(safe_text, max_chars=900)

    summaries = []
    for chunk in chunks:
        result = summarizer_model(
            chunk,
            max_length=200,
            min_length=60,
            do_sample=False,
            truncation=False,
        )
        summaries.append(result[0]["summary_text"].strip())

    combined = " ".join(summaries)
    final_summary = restore_urls(combined, url_map)
    return final_summary
