"""History-compaction (summarization) prompt for the ordering agent.

LangChain's built-in ``SummarizationMiddleware`` ships a *generic coding-agent*
summary prompt (its sections are SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS and
it asks for "file paths") — wrong domain for a WhatsApp food-ordering chat, which is why
the default summaries read generic and drop the details that matter to an order.

This replacement tells the summary model exactly what to preserve for *this* domain: the
customer's identity, delivery details, dietary constraints, what they were ordering, and
the open thread of the conversation. The live cart, fulfillment, address and step are kept
separately in graph state (``OrderingState``) and the business facts are re-injected into
the system prompt every turn — so this summary only has to carry the *conversation*
context that would otherwise be lost when older messages are compacted.

Contract (enforced by ``SummarizationMiddleware``): the string is formatted with
``.format(messages=...)``, so it must contain the ``{messages}`` placeholder and must NOT
contain any other unescaped ``{`` / ``}``.
"""
from __future__ import annotations

ORDERING_SUMMARY_PROMPT = """\
You are compacting the earlier part of a live WhatsApp conversation between a food \
business's ordering assistant and a customer. The older messages below will be REPLACED by \
your summary, while the most recent messages are kept verbatim. Capture everything needed to \
continue the order without asking the customer to repeat themselves.

Write concise notes under these headings. Use a heading only if you have real information for \
it; write "None" if you do not. Never invent details that are not in the messages.

CUSTOMER
- Name (if they gave one), and anything they told you about themselves.
- Preferences and constraints to honor: dietary needs, allergies, spice level, "no onions", \
budget, language quirks, etc.

ORDER SO FAR
- Items discussed and decisions made (what they chose, rejected, or are still deciding), with \
sizes/options/quantities and any special instructions per item.
- Fulfillment: delivery or pickup; delivery address / area and whether it was confirmed \
serviceable; anything said about timing.
- Any quoted totals, fees, or minimum-order issues already raised.

CONVERSATION STATE
- What the customer last asked for and what the assistant was about to do next.
- Open questions or unresolved problems (item unavailable, outside delivery area, below \
minimum, missing required option, etc.).
- Whether the conversation was handed off to a human, and why.

Keep it short and factual — bullet points, not prose. Do not include greetings, menu dumps, \
tool mechanics, or anything the customer no longer needs.

Conversation to summarize:
{messages}"""
