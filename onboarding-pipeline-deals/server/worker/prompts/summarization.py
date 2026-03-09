"""
Prompts for single-document summarization.

Used by worker.summarizer to generate two-sentence document descriptions.
"""

SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a financial analyst assistant. Be concise and precise. "
    "Write in plain, professional English."
)

SUMMARIZATION_USER_PROMPT = "Summarize this investment document in two sentences:\n\n{text}"
