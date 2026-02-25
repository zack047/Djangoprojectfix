import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import re
from transformers import pipeline

summarizer = pipeline(
    "summarization",
    model="facebook/bart-large-cnn",
    tokenizer="facebook/bart-large-cnn",
    device=-1,  # CPU
)

# ---------- URL PROTECTION HELPERS ----------

URL_RE = re.compile(r"(https?://[^\s]+)")

def protect_urls(text: str):
    """
    Replace every URL with a placeholder like URLTOKEN0, URLTOKEN1...
    This prevents the summarizer from breaking the URL.
    """
    urls = URL_RE.findall(text)
    mapping = {}
    safe_text = text

    for idx, url in enumerate(urls):
        token = f"URLTOKEN{idx}"
        mapping[token] = url
        safe_text = safe_text.replace(url, token)

    return safe_text, mapping

def restore_urls(text: str, mapping: dict):
    """
    Replace URLTOKENx back with the original URLs.
    """
    for token, url in mapping.items():
        text = text.replace(token, url)
    return text

def chunk_by_words(text: str, max_chars: int = 900):
    """
    Split text into chunks by words, so we never cut in the middle
    of a URLTOKEN or word.
    """
    words = text.split()
    chunks = []
    current = []

    current_len = 0
    for w in words:
        # +1 for space
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
    """
    Generate an AI summary that:
    - keeps URLs intact (no breaking https://...),
    - keeps length reasonable (~550–600 chars with our settings),
    - works for long agendas via chunking.
    """
    if not text:
        return ""

    raw = text.strip()
    if len(raw) < 50:
        # Too short to summarize meaningfully
        return raw

    # ✅ 1. Protect URLs before giving to the model
    safe_text, url_map = protect_urls(raw)

    # ✅ 2. Split into word-based chunks (preserves URLTOKENs)
    chunks = chunk_by_words(safe_text, max_chars=900)

    summaries = []

    for chunk in chunks:
        # You can tune max_length/min_length for overall size.
        # BART token length, not characters, but this usually lands
        # you in the ~100–150 word / 500–600 char range.
        result = summarizer(
            chunk,
            max_length=200,  # target-ish upper bound
            min_length=60,
            do_sample=False,
            truncation=False,
        )
        summaries.append(result[0]["summary_text"].strip())

    combined = " ".join(summaries)

    # ✅ 3. Restore URLs (URLTOKENx → original URL)
    final_summary = restore_urls(combined, url_map)

    return final_summary



# def generate_ai_summary(text: str):
#     """
#     Generate an AI summary safely using lazy-loaded model.
#     """
#     if not text:
#         return ""
#
#     raw = text.strip()
#     if len(raw) < 50:
#         return raw
#
#     # Load model lazily (THIS is the important fix)
#     summarizer_model = get_summarizer()
#
#     # Protect URLs
#     safe_text, url_map = protect_urls(raw)
#
#     # Chunking
#     chunks = chunk_by_words(safe_text, max_chars=900)
#
#     summaries = []
#
#     for chunk in chunks:
#         result = summarizer_model(
#             chunk,
#             max_length=200,
#             min_length=60,
#             do_sample=False,
#         )
#         summaries.append(result[0]["summary_text"].strip())
#
#     combined = " ".join(summaries)
#
#     # Restore URLs
#     final_summary = restore_urls(combined, url_map)
#
#     return final_summary

