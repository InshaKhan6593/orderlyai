"""History-compaction (summarization) prompt for the ordering agent.

LangChain's built-in ``SummarizationMiddleware`` ships a *generic coding-agent* summary
prompt (its sections are SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS and it asks for
"file paths") — wrong domain for a WhatsApp food-ordering chat, which is why the default
summaries read generic and drop the details that matter to an order.

How the middleware uses this (so the wording matches the mechanics):
  * It summarizes only the OLDER messages once the history passes the token trigger; the most
    recent ``agent_summary_keep_messages`` messages are kept VERBATIM (not summarized).
  * The summary is written back into state as a message and PERSISTS. On the next trigger that
    prior summary is fed back through ``{messages}`` to be extended — so the prompt tells the
    model to CARRY earlier facts forward and merge, never to drop them.
  * The live cart, fulfillment, address and step live in graph state (``OrderingState``), not in
    the messages, so summarization never alters them; ``view_cart`` re-reads them authoritatively.
    The business facts are re-injected into the system prompt every turn. So this summary only has
    to carry the *conversation* context that would otherwise be lost when older messages compact —
    and must NOT pose as the authoritative cart.

Contract (enforced by ``SummarizationMiddleware``): the string is formatted with
``.format(messages=...)``, so it must contain the ``{messages}`` placeholder and must NOT contain
any other unescaped ``{`` / ``}``.
"""
from __future__ import annotations

ORDERING_SUMMARY_PROMPT = """\
You are the memory compactor for a live WhatsApp food-ordering chat between a business's ordering \
assistant and one customer. The messages below are the OLDER part of that chat; they will be \
permanently REPLACED by your summary, while the most recent messages are kept verbatim. Produce a \
compact, factual hand-off so the assistant can continue the order without the customer repeating \
anything.

RULES
- Summarize the CONVERSATION, not the plumbing: ignore tool-call and tool-result mechanics, menu \
and item listings, system notices, and greetings. Keep only what affects this customer's order.
- Preserve specifics EXACTLY as the customer or assistant stated them: item names, sizes, chosen \
options and add-ons, quantities, per-item special instructions, the delivery address, the \
customer's name, and any order numbers or amounts already quoted. Never rename, round, merge, or \
invent — if something was not stated, leave it out.
- If an earlier summary already appears in the messages, treat its facts as established and CARRY \
THEM FORWARD, merging the newer messages into it. Never drop older facts.
- The live cart, fulfillment, address, and step are tracked separately in app state and are the \
source of truth for the CURRENT order; the assistant re-reads them with view_cart. Record what was \
decided and discussed here — do not present your list as the authoritative cart, and do not invent \
totals.
- Be brief and factual: short bullets, not prose. Under each heading write the facts, or "None". \
This is an internal note — do not address the customer.

CUSTOMER
- Name, and anything they shared about themselves.
- Standing preferences and constraints to honor: dietary needs, allergies, spice level, dislikes \
(e.g. no onions), budget.

ORDER
- Items the customer chose, rejected, or is still deciding — each with size, options, quantity, and \
any special instruction.
- Fulfillment: delivery or pickup; delivery address or area and whether it was confirmed \
serviceable; any timing request.
- Amounts, fees, delivery-zone, or minimum-order points already raised.

STATE
- What the customer last asked for and what the assistant was about to do next.
- Open or unresolved issues: item unavailable, outside delivery area, below minimum, missing \
required option, awaiting the customer's Confirm tap, etc.
- Whether the chat was handed off to a human, and why.

Conversation to summarize:
{messages}"""
