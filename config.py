"""
config.py
─────────
Per-agent model configuration for the adversarial review pipeline.

Different LLM providers excel at different tasks:
  - Anthropic Claude: Best reasoning, nuanced decisions
  - OpenAI GPT-4o: Better function calling, structured JSON
  - Google Gemini: Long context, cost efficiency

Configure each agent to use the optimal provider for its role.
"""

# ─── Default Configuration ───────────────────────────────────────────────────
# Uses Anthropic for all agents (simplest setup, requires only one API key)

AGENT_MODEL_CONFIG = {
    "proposer": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    },
    "critic": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    },
    "arbiter": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    },
}


# ─── Optimized Multi-Provider Configuration ──────────────────────────────────
# Uses each provider's strengths for different agent roles
# Requires: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY

OPTIMIZED_CONFIG = {
    "proposer": {
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        # Gemini: Long context window for complex drafts
    },
    "critic": {
        "provider": "openai",
        "model": "gpt-4o",
        # OpenAI: Better structured JSON output for critique lists
    },
    "arbiter": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        # Anthropic: Best reasoning for nuanced verdicts
    },
}


# ─── Cost-Optimized Configuration ────────────────────────────────────────────
# Uses smaller/faster models where appropriate

COST_OPTIMIZED_CONFIG = {
    "proposer": {
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        # Flash: Fast, cheap, good for drafts
    },
    "critic": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        # Mini: Cheaper, still good structured output
    },
    "arbiter": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        # Keep best reasoning for final decisions
    },
}


# ─── Active Configuration ────────────────────────────────────────────────────
# Change this to switch between configurations
# Options: AGENT_MODEL_CONFIG, OPTIMIZED_CONFIG, COST_OPTIMIZED_CONFIG

ACTIVE_CONFIG = AGENT_MODEL_CONFIG


def get_agent_config(agent_id: str) -> dict:
    """
    Get the model configuration for a specific agent.

    Args:
        agent_id: One of "proposer", "critic", "arbiter"

    Returns:
        Dict with "provider" and "model" keys

    Raises:
        ValueError: If agent_id is not recognized
    """
    if agent_id not in ACTIVE_CONFIG:
        raise ValueError(
            f"Unknown agent: {agent_id}. "
            f"Available: {list(ACTIVE_CONFIG.keys())}"
        )
    return ACTIVE_CONFIG[agent_id]


def set_active_config(config: dict) -> None:
    """
    Set the active configuration at runtime.

    Args:
        config: Dict mapping agent_id to {"provider", "model"} dicts
    """
    global ACTIVE_CONFIG
    ACTIVE_CONFIG = config
