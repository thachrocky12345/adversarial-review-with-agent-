"""
budget_manager.py
─────────────────
Token budget management for the adversarial review pipeline.

The TokenBudgetManager assigns budgets to agents BEFORE they run,
tracks usage across the pipeline, and expands budgets on retry.

Token Protection Layers:
  1. Budget contract (this module): Sets limits before agent runs
  2. Prompt injection: Agent sees limits in system prompt via TokenBudget.to_prompt_block()
  3. Orchestrator gate: AgentResult.status checked after every call
"""

from dataclasses import dataclass, field
from typing import Optional

from core_types import TokenBudget


# ─── Budget Profiles ─────────────────────────────────────────────────────────
# Predefined budgets based on task complexity

BUDGET_PROFILES = {
    "simple": {
        "input": 2000,
        "output": 1000,
        "turns": 2,
    },
    "normal": {
        "input": 4000,
        "output": 2000,
        "turns": 3,
    },
    "complex": {
        "input": 8000,
        "output": 4000,
        "turns": 5,
    },
}

# Safety margin: stop before hitting limit to allow clean shutdown
SAFETY_MARGIN_PCT = 0.15  # 15% buffer

# Retry expansion: increase budget when retrying after partial completion
RETRY_EXPANSION = 1.4  # 40% increase on retry


# ─── Usage Record ────────────────────────────────────────────────────────────

@dataclass
class UsageRecord:
    """Track token usage for a single agent invocation."""
    agent_id: str
    tokens_used: int
    budget_assigned: int
    was_retry: bool = False


# ─── Token Budget Manager ────────────────────────────────────────────────────

class TokenBudgetManager:
    """
    Manages token budgets across the adversarial review pipeline.

    Responsibilities:
      - Assign budgets per agent role based on task complexity
      - Track token usage across runs
      - Expand budgets on retry (40% increase)
      - Enforce 15% safety margin
    """

    def __init__(self):
        self._usage_history: list[UsageRecord] = []
        self._assigned_budgets: dict[str, TokenBudget] = {}

    def assign(
        self,
        agent_id: str,
        complexity: str = "normal",
        retry_of: Optional[dict] = None,
    ) -> TokenBudget:
        """
        Assign a token budget to an agent.

        Args:
            agent_id: Identifier for the agent (e.g., "proposer", "critic")
            complexity: Task complexity ("simple", "normal", "complex")
            retry_of: Checkpoint from previous attempt (triggers budget expansion)

        Returns:
            TokenBudget instance with assigned limits
        """
        if complexity not in BUDGET_PROFILES:
            complexity = "normal"

        profile = BUDGET_PROFILES[complexity]

        input_tokens = profile["input"]
        output_tokens = profile["output"]
        max_turns = profile["turns"]

        # Expand budget on retry
        if retry_of is not None:
            input_tokens = int(input_tokens * RETRY_EXPANSION)
            output_tokens = int(output_tokens * RETRY_EXPANSION)
            max_turns = max_turns + 1

        # Calculate safety margin
        safety_margin = int(input_tokens * SAFETY_MARGIN_PCT)

        budget = TokenBudget(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            max_turns=max_turns,
            safety_margin=safety_margin,
        )

        self._assigned_budgets[agent_id] = budget
        return budget

    def record_usage(self, agent_id: str, tokens_used: int) -> None:
        """
        Record token usage for an agent run.

        Args:
            agent_id: Identifier for the agent
            tokens_used: Number of tokens consumed
        """
        budget = self._assigned_budgets.get(agent_id)
        budget_assigned = budget.input_tokens if budget else 0

        record = UsageRecord(
            agent_id=agent_id,
            tokens_used=tokens_used,
            budget_assigned=budget_assigned,
        )
        self._usage_history.append(record)

    def get_usage_report(self) -> dict:
        """
        Get a summary of token usage across all agents.

        Returns:
            Dict with usage statistics per agent and totals
        """
        if not self._usage_history:
            return {
                "agents": {},
                "total_tokens": 0,
                "total_budget": 0,
                "efficiency": 0.0,
            }

        # Aggregate by agent
        agent_stats: dict[str, dict] = {}
        for record in self._usage_history:
            if record.agent_id not in agent_stats:
                agent_stats[record.agent_id] = {
                    "invocations": 0,
                    "tokens_used": 0,
                    "budget_assigned": 0,
                }
            stats = agent_stats[record.agent_id]
            stats["invocations"] += 1
            stats["tokens_used"] += record.tokens_used
            stats["budget_assigned"] += record.budget_assigned

        # Calculate efficiency for each agent
        for agent_id, stats in agent_stats.items():
            if stats["budget_assigned"] > 0:
                stats["efficiency"] = stats["tokens_used"] / stats["budget_assigned"]
            else:
                stats["efficiency"] = 0.0

        # Calculate totals
        total_tokens = sum(r.tokens_used for r in self._usage_history)
        total_budget = sum(r.budget_assigned for r in self._usage_history)

        return {
            "agents": agent_stats,
            "total_tokens": total_tokens,
            "total_budget": total_budget,
            "efficiency": total_tokens / total_budget if total_budget > 0 else 0.0,
        }

    def reset(self) -> None:
        """Clear all usage history and assigned budgets."""
        self._usage_history.clear()
        self._assigned_budgets.clear()

    def get_remaining_budget(self, agent_id: str, tokens_used: int) -> int:
        """
        Calculate remaining budget for an agent.

        Args:
            agent_id: Identifier for the agent
            tokens_used: Tokens already consumed

        Returns:
            Remaining tokens available (may be negative if over budget)
        """
        budget = self._assigned_budgets.get(agent_id)
        if not budget:
            return 0
        return budget.effective_input_limit - tokens_used
