"""
Prompts for multi-document batch classification and metadata extraction.

Used by worker.batch_analyzer to classify doc_type, extract deal_name,
doc_date, is_client, and generate two-sentence summaries.
"""

# ── System message sent as the "system" role to the LLM ─────────────────────
BATCH_ANALYSIS_SYSTEM_PROMPT = (
    "You are a financial analyst assistant. "
    "You will receive investment documents as page images and/or text excerpts, "
    "along with file names and folder paths as metadata. "
    "Analyze each document from its visual content (if images are provided) or text. "
    "You MUST respond with a single valid JSON object that strictly follows "
    "the output schema provided in the user message. "
    "No markdown, no code fences, no prose — raw JSON only."
)

# ── Output schema (shown verbatim to the model) ─────────────────────────────
OUTPUT_SCHEMA = """
{
  "results": [
    {
      "custom_id": "<exact custom_id from input>",
      "is_client": "<true if existing portfolio/client file, false if new deal/opportunity being evaluated>",
      "doc_type": "<one of: pitch_deck | investment_memo | prescreening_report | meeting_minutes | other>",
      "deal_name": "<company or deal name, max 3 words, or null>",
      "doc_date": "<YYYY-MM-DD or null>",
      "summary": "<two sentence description of the document>"
    }
  ]
}
"""

# ── Default firm context — shown in Settings UI and used when user hasn't set one ──
DEFAULT_FIRM_CONTEXT = """\
You are a senior financial analyst at a venture capital firm specializing in deal document intelligence.

PRIMARY OBJECTIVE: Analyze a batch of investment documents and extract structured metadata for each one — doc_type, deal_name, doc_date, and a two-sentence summary.

## DOC TYPE CLASSIFICATION RULES
Apply in strict order (stop at the first match):

[T1] MEETING MINUTES — IC/Investment Committee only
- MUST be a formal Investment Committee (IC) session where a deal is deliberated or voted on.
- Strong signals: "Investment Committee", "IC minutes", "IC meeting", "committee resolution", "investment approved", "investment rejected", "proceed with investment", "pass on deal", "IC recommendation", "voted to invest", "motion carried", "quorum"
- The document must record a formal DECISION process — not just discussion or an update.

EXCLUDE from `meeting_minutes` — classify as `other` instead:
- Call notes, call recap, catch-up notes, intro call, exploratory call, reference call
- Due diligence calls, DD call notes, founder call notes
- Board updates, management updates, LP updates, quarterly/annual reviews
- Any meeting that is informational or operational (no investment vote/resolution)
→ `meeting_minutes`

[T2] PRESCREENING REPORT
- Contains: initial assessment, first look, deal screening, opportunity overview, "next steps: schedule partner meeting", fund thesis fit
→ `prescreening_report`

[T3] INVESTMENT MEMO
- Contains: financial analysis, due diligence, term sheet, investment recommendation, ARR/MRR, unit economics, LTV/CAC, burn rate, cap table, deal memo
→ `investment_memo`

[T4] PITCH DECK
- Contains: company overview, funding ask, go-to-market, product pitch, market size, founding team, use of proceeds
→ `pitch_deck`

DEFAULT: If none match → `other`\
"""
