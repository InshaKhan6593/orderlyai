"""Application settings, loaded from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "OrderlyAI API"
    env: str = "local"
    debug: bool = False  # opt in via DEBUG=true in .env for local dev
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str

    # Auth / JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Uploads
    upload_dir: str = "uploads"
    max_product_image_bytes: int = 2_000_000

    # WhatsApp Cloud API
    whatsapp_verify_token: str | None = None
    # Meta App Secret — verifies the X-Hub-Signature-256 header on inbound webhooks.
    whatsapp_app_secret: str | None = None
    # Fernet key (urlsafe base64, 32 bytes) encrypting stored access tokens at rest.
    whatsapp_token_encryption_key: str | None = None

    # AI agent (LangChain v1). Provider is pluggable: "anthropic" (direct) or
    # "openrouter" (OpenAI-compatible gateway, many models behind one key).
    llm_provider: str = "openrouter"  # "anthropic" | "openrouter"

    # Direct Anthropic (used when llm_provider == "anthropic").
    anthropic_api_key: str | None = None

    # OpenRouter (used when llm_provider == "openrouter"). Get a key at openrouter.ai.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model ids. For "anthropic" use "anthropic:<model>"; for "openrouter" use the
    # OpenRouter slug (e.g. "anthropic/claude-sonnet-4.6", "openai/gpt-5.5").
    agent_model: str = "anthropic/claude-sonnet-4.6"
    agent_escalation_model: str = "anthropic/claude-opus-4.1"
    agent_summary_model: str = "anthropic/claude-haiku-4.5"

    # Summarization (history compaction) — a SAFETY VALVE for long/repeat threads, NOT a per-turn
    # step. Trigger when the running history reaches `trigger_tokens`; keep the most recent
    # `keep_messages` verbatim; trim the block handed to the summary model to `trim_tokens`.
    # Size `trigger_tokens` to the MODEL'S CONTEXT WINDOW: best practice is to compact at ~70-80%
    # of the window, with a floor (~50k) so short sessions never thrash. On a large-context model
    # (e.g. 1M) keep this high so a normal ordering chat is NEVER summarized (full fidelity) — it
    # then fires only on very long or repeat-customer threads. Always use a CHEAP summary model
    # (Haiku/Flash), never the main model. Keep `trim_tokens` >= the summarized block (i.e. >=
    # trigger) so the summary input isn't truncated and details lost. See app/agent/runtime.py.
    agent_summary_trigger_tokens: int = 50000
    agent_summary_keep_messages: int = 30
    agent_summary_trim_tokens: int = 50000
    # Per-turn ceiling on model calls (loop/cost guard) — see ModelCallLimitMiddleware.
    agent_max_model_calls: int = 12

    # Context editing (model-agnostic, via ContextEditingMiddleware): once the running
    # history exceeds ~`agent_context_edit_trigger_tokens`, clear the *output* of older tool
    # calls from what's sent to the model (keeping the most recent `agent_context_edit_keep`).
    # This trims the per-call payload — repeated get_menu/view_cart/get_item_details dumps —
    # WITHOUT rewriting stored history, and triggers below the summarizer so cheap, lossless
    # tool-result clearing happens before lossy summarization. See app/agent/runtime.py.
    agent_context_edit_trigger_tokens: int = 3000
    agent_context_edit_keep: int = 3

    # Agent business snapshot cache. The agent reads the same tenant facts (identity, hours,
    # fees, categories) and the current menu on (nearly) every model call; loading them from
    # Postgres on each of the up-to-`agent_max_model_calls` calls per turn is wasteful, so the
    # rendered snapshot is cached per business for this many seconds (0 disables the cache).
    # Hard guards (accepting_orders, open hours, pricing) are ALWAYS re-validated live at order
    # time in order_service, so a few seconds of prompt staleness is safe. See app/agent/snapshot.py.
    agent_snapshot_ttl_seconds: float = 15.0
    # Inline the menu into the system prompt when its rendered size is within this many chars,
    # so the agent answers menu questions from context instead of round-tripping the get_menu
    # tool. Larger menus fall back to the get_menu tool. 0 disables preloading entirely.
    agent_menu_preload_max_chars: int = 8000
    # Disable "thinking/reasoning" mode for OpenRouter models. The agent forces a structured
    # `AgentReply` tool call (tool_choice=required), which reasoning models (Qwen3 *thinking*,
    # DeepSeek-R1, etc.) REJECT in thinking mode — causing a 400. Disabling reasoning makes
    # those models usable (and faster); ignored by non-reasoning models. See app/agent/runtime.py.
    agent_disable_reasoning: bool = True

    # OpenRouter provider routing (only used when llm_provider == "openrouter"). An OpenRouter
    # model slug is load-balanced across MANY upstream providers; one can blip and return an
    # opaque "Provider returned error" (400), or not honor the agent's forced structured-output
    # tool call. Pin which providers may serve the model so a turn never lands on a flaky one.
    # `openrouter_provider_order`: comma-separated provider slugs in preference order, e.g.
    # "Alibaba,DeepInfra,Novita" (Alibaba is Qwen's first-party host). Empty = OpenRouter's
    # default routing. The slugs MUST be providers that actually serve YOUR model — a Qwen pin
    # won't serve a Claude slug (that needs Anthropic/Amazon Bedrock/Google), so clear/adjust
    # this if you change AGENT_MODEL's family. With `allow_fallbacks` False, OpenRouter uses
    # ONLY these (tried in order) and errors if none can serve — the worker then retries.
    # See `_make_model` in app/agent/runtime.py.
    openrouter_provider_order: str = ""
    openrouter_provider_allow_fallbacks: bool = True

    # Agent durable memory + inbound worker.
    # `whatsapp_durable_memory`: use the Postgres checkpointer (survives restarts) instead
    # of the in-process MemorySaver. `run_agent_worker`: on app startup, build the durable
    # agent and start the inbox sweeper. Both are disabled in tests (RUN_AGENT_WORKER=false).
    whatsapp_durable_memory: bool = True
    run_agent_worker: bool = True

    # Inbound message processing (durable inbox + per-conversation serialization).
    # `coalesce_seconds`: brief debounce so a burst of rapid messages is answered as one
    # turn (0 = process promptly). `inbox_max_attempts`: give up + dead-letter after N
    # failures. `inbox_sweep_seconds`: how often the background sweeper re-drives pending
    # rows (crash recovery / lock-contention backstop).
    whatsapp_coalesce_seconds: float = 0.0
    whatsapp_inbox_max_attempts: int = 5
    whatsapp_inbox_sweep_seconds: int = 30
    # Cap concurrent conversation drains so a webhook burst can't exhaust the DB pool — each
    # drain holds two connections (a pinned advisory-lock connection + the work session).
    whatsapp_max_concurrent_drains: int = 6
    # Auto-resume the bot after a human handoff once the customer has been silent this long
    # (0 = stay handed off until manually cleared). Stops one "talk to a human" muting a
    # customer forever on their permanent conversation thread.
    whatsapp_handoff_mute_hours: int = 24
    # Retention: purge inbox rows and delete the LangGraph checkpoint for a conversation that
    # has been inactive this many days (0 disables) — bounds unbounded per-customer growth of
    # the inbox and the checkpoint tables. `retention_sweep_hours`: how often to run the purge.
    whatsapp_retention_days: int = 90
    whatsapp_retention_sweep_hours: int = 24
    # Meta's free-form customer-service window. Outside it, only template messages send.
    whatsapp_customer_window_hours: int = 24
    # Per-customer inbound rate limit (protects LLM spend from a flood/spam).
    whatsapp_rate_limit_per_min: int = 20
    # Outbound send retries (transient Graph API / network errors).
    whatsapp_send_max_retries: int = 3

    # Notify the customer on WhatsApp when an order's status changes (accepted/ready/etc.).
    whatsapp_notify_on_status_change: bool = True

    # Proactive notifications outside the 24h window need pre-approved templates. Leave
    # unset to skip out-of-window pushes (in-window confirmations/updates still send as
    # free-form text). Set the approved template names + language to enable them later.
    whatsapp_template_lang: str = "en"
    whatsapp_order_confirm_template: str | None = None
    whatsapp_order_status_template: str | None = None

    # Agent prompt management (LangSmith Prompt Hub). Code is the source of truth: the
    # in-code template is pushed to `agent_prompt_name` by `sync_prompt.py` (versioning,
    # Playground, evals). Set `agent_prompt_ref` (e.g. "orderlyai-agent:production") to
    # pull-override the prompt at runtime; leave unset to always use the in-code template.
    agent_prompt_name: str = "orderlyai-agent"
    agent_prompt_ref: str | None = None

    # LangSmith tracing / evals (optional; off unless tracing is enabled).
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str | None = None
    langsmith_project: str = "orderlyai"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
