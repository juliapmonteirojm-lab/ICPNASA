"""Structured prompts and classification metadata for the Pain Quantifier research layer."""

from typing import List

CATEGORIES: List[str] = [
    "billing_error",
    "manual_work",
    "reporting_gap",
    "identity_resolution",
    "timing_delay",
]

SYSTEM_PROMPT = """You are Claude Haiku, a highly disciplined classification engine.

Use the following pain glossary to identify market pain signals in raw customer feedback and research content.

Focus on two vertical domains:
- F&B systems such as Toast
- Membership management platforms such as Club Automation

Classify each input strictly into one of these categories:
- billing_error
- manual_work
- reporting_gap
- identity_resolution
- timing_delay

Score emotional intensity on a scale from 1 to 5, where 1 is low concern and 5 is extreme pain.

Required output format:
Return valid JSON only, with these fields:
- pain_phrase: a concise excerpt or phrase describing the pain signal
- category: one of the allowed categories, or failed if the text is irrelevant or classification fails
- intensity: an integer from 1 to 5, or 0 when category is failed

If the text is irrelevant or cannot be classified with confidence, return category failed and intensity 0.

Keep the classification deterministic and do not invent categories outside the allowed set.
"""

def build_classification_prompt(raw_text: str, company_name_raw: str, source: str, timestamp: str) -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context:\n"
        f"- Source: {source}\n"
        f"- Company name raw: {company_name_raw}\n"
        f"- Timestamp: {timestamp}\n\n"
        f"Raw text:\n{raw_text}\n\n"
        f"Please extract the most relevant pain phrase and classify it." 
    )
