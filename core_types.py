"""
core_types.py
─────────────
Shared types for the adversarial review pipeline.
Every agent — Proposer, Critic, Arbiter — speaks this language.
No ambiguous returns. No silent failures.

Note: This file is named core_types.py (not types.py) to avoid
shadowing Python's built-in types module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime


# ─── Completion Status ──────────────────────────────────────────────────────
# The envelope every agent wraps around its output.
# The Orchestrator inspects this before passing data downstream.

class CompletionStatus(Enum):
    COMPLETE        = "complete"         # All work done, result fully reliable
    PARTIAL_SAFE    = "partial_safe"     # Incomplete, but finished units are correct
    PARTIAL_UNSAFE  = "partial_unsafe"   # Mid-unit stop — DO NOT USE data downstream
    BUDGET_EXCEEDED = "budget_exceeded"  # Hard token limit hit, checkpoint saved
    FAILED          = "failed"           # Unrecoverable error


# ─── Review Verdict ─────────────────────────────────────────────────────────
# Output of the Critic and Arbiter roles specifically.

class ReviewVerdict(Enum):
    APPROVED        = "approved"         # Passes all guardrails
    APPROVED_MINOR  = "approved_minor"   # Passes, with non-blocking notes
    REVISE          = "revise"           # Specific issues found, revision required
    REJECT          = "reject"           # Fundamental violation, do not proceed
    ESCALATE        = "escalate"         # Ambiguous — needs human review


# ─── Token Budget ────────────────────────────────────────────────────────────
# Assigned to each agent BEFORE it starts. Not enforced after — a contract.

@dataclass
class TokenBudget:
    input_tokens:  int   # Max tokens the agent may receive as input
    output_tokens: int   # Max tokens the agent may generate
    max_turns:     int   # Max agentic loop iterations
    safety_margin: int   # Stop BEFORE hitting limit (15% recommended)
    on_exceed:     str = "return_partial_with_checkpoint"

    @property
    def effective_input_limit(self) -> int:
        """Real limit agents check against — includes safety buffer."""
        return self.input_tokens - self.safety_margin

    def to_prompt_block(self) -> str:
        return f"""
TOKEN BUDGET FOR THIS TASK:
  Input available : {self.effective_input_limit:,} tokens (hard cap: {self.input_tokens:,})
  Output limit    : {self.output_tokens:,} tokens
  Max turns       : {self.max_turns}
  On exceed       : {self.on_exceed}

RULES:
1. Check budget BEFORE starting each review unit (section, claim, criterion).
   Never start a unit you cannot finish — a clean partial beats corrupt output.
2. Return an AgentResult envelope. Always declare your CompletionStatus explicitly.
3. Partial results are expected and handled upstream. Never hallucinate completion.
""".strip()


# ─── Agent Result ────────────────────────────────────────────────────────────
# Universal return type. Completeness is always explicit.

@dataclass
class AgentResult:
    agent_id:        str
    task_id:         str
    status:          CompletionStatus
    data:            Any                     # The actual payload
    verdict:         Optional[ReviewVerdict] = None
    items_processed: int = 0
    items_total:     int = 0
    tokens_used:     int = 0
    elapsed_sec:     float = 0.0
    checkpoint:      Optional[dict] = None   # State to resume from
    issues:          list = field(default_factory=list)
    error:           Optional[str] = None
    warning:         Optional[str] = None
    timestamp:       str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    @property
    def coverage(self) -> float:
        if self.items_total == 0:
            return 1.0
        return self.items_processed / self.items_total

    @property
    def is_usable(self) -> bool:
        """Can the Orchestrator safely pass this downstream?"""
        return self.status in (
            CompletionStatus.COMPLETE,
            CompletionStatus.PARTIAL_SAFE,
        )

    def summary(self) -> str:
        verdict_str = f" | verdict={self.verdict.value}" if self.verdict else ""
        return (
            f"[{self.agent_id}] {self.status.value}{verdict_str} | "
            f"{self.items_processed}/{self.items_total} items | "
            f"{self.coverage:.0%} coverage | "
            f"{self.tokens_used:,} tokens"
        )
