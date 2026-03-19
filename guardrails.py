"""
core/guardrails.py
──────────────────
Project integrity guardrails and persona guardrails.
Every agent must pass these before its output is forwarded downstream.
The Orchestrator calls check() on every AgentResult before routing it.
"""

from dataclasses import dataclass
from typing import Optional
from core_types import AgentResult, ReviewVerdict, CompletionStatus


# ─── Guardrail Issue ─────────────────────────────────────────────────────────

@dataclass
class GuardrailIssue:
    guardrail:   str    # Which guardrail fired
    severity:    str    # "block" | "warn" | "note"
    description: str
    remedy:      str    # What the agent should do to fix it


# ─── Guardrail Result ────────────────────────────────────────────────────────

@dataclass
class GuardrailResult:
    passed:  bool
    issues:  list[GuardrailIssue]
    verdict: ReviewVerdict

    @property
    def is_blocked(self) -> bool:
        return any(i.severity == "block" for i in self.issues)

    def summary(self) -> str:
        if self.passed:
            return "✅ All guardrails passed."
        lines = [f"❌ Guardrail failures ({len(self.issues)}):"]
        for issue in self.issues:
            icon = "🚫" if issue.severity == "block" else "⚠️"
            lines.append(f"  {icon} [{issue.guardrail}] {issue.description}")
            lines.append(f"     Remedy: {issue.remedy}")
        return "\n".join(lines)


# ─── Project Integrity Guardrails ────────────────────────────────────────────
# These protect the pipeline as a whole.
# Violations here block the run entirely.

class ProjectIntegrityGuardrails:
    """
    Checks output against project-level rules:
    - Completeness: result must be usable before forwarding
    - Token honesty: agents must not claim full completion when partial
    - No hallucinated data: structured fields must be present if declared complete
    - Scope creep: output must stay within the assigned task
    """

    def check(self, result: AgentResult, expected_task_id: str) -> GuardrailResult:
        issues: list[GuardrailIssue] = []

        # 1. Task ID integrity — result must match the assigned task
        if result.task_id != expected_task_id:
            issues.append(GuardrailIssue(
                guardrail="task_id_integrity",
                severity="block",
                description=f"Result task_id '{result.task_id}' != expected '{expected_task_id}'.",
                remedy="Ensure the agent returns the exact task_id it was assigned.",
            ))

        # 2. Completeness honesty — COMPLETE status requires full coverage
        if (result.status == CompletionStatus.COMPLETE
                and result.items_total > 0
                and result.coverage < 1.0):
            issues.append(GuardrailIssue(
                guardrail="completeness_honesty",
                severity="block",
                description=(
                    f"Agent claimed COMPLETE but coverage is only {result.coverage:.0%} "
                    f"({result.items_processed}/{result.items_total} items)."
                ),
                remedy="Return PARTIAL_SAFE if not all items were processed.",
            ))

        # 3. Unsafe partial — PARTIAL_UNSAFE must not be forwarded downstream
        if result.status == CompletionStatus.PARTIAL_UNSAFE:
            issues.append(GuardrailIssue(
                guardrail="unsafe_partial_block",
                severity="block",
                description="Result status is PARTIAL_UNSAFE — mid-unit stop detected.",
                remedy="Retry the task. Do not pass PARTIAL_UNSAFE data downstream.",
            ))

        # 4. Empty data on claimed success
        if result.status == CompletionStatus.COMPLETE and not result.data:
            issues.append(GuardrailIssue(
                guardrail="empty_complete_result",
                severity="block",
                description="Status is COMPLETE but data payload is empty.",
                remedy="Return actual result data, or downgrade status to FAILED.",
            ))

        # 5. Missing checkpoint on BUDGET_EXCEEDED
        if result.status == CompletionStatus.BUDGET_EXCEEDED and not result.checkpoint:
            issues.append(GuardrailIssue(
                guardrail="missing_checkpoint",
                severity="warn",
                description="Budget exceeded but no checkpoint returned — cannot resume.",
                remedy="Always save checkpoint state when budget is exceeded.",
            ))

        passed  = not any(i.severity == "block" for i in issues)
        verdict = ReviewVerdict.APPROVED if passed else ReviewVerdict.REJECT
        return GuardrailResult(passed=passed, issues=issues, verdict=verdict)


# ─── Persona Guardrails ──────────────────────────────────────────────────────
# These protect the role/persona of each agent.
# An agent must stay within its defined role — no role bleed.

ROLE_PERMISSIONS = {
    "proposer": {
        "may_produce":   ["draft", "proposal", "structured_content"],
        "may_not":       ["verdict", "approval", "critique", "final_decision"],
        "tone":          "constructive, generative",
        "constraint":    "Must not evaluate its own output or claim its draft is final.",
    },
    "critic": {
        "may_produce":   ["critique", "issues_list", "revision_requests"],
        "may_not":       ["draft", "rewrite", "final_decision"],
        "tone":          "analytical, specific, evidence-based",
        "constraint":    "Must cite specific lines/sections. No vague criticism.",
    },
    "arbiter": {
        "may_produce":   ["verdict", "rationale", "final_decision"],
        "may_not":       ["draft", "rewrite", "new_critique"],
        "tone":          "neutral, decisive",
        "constraint":    "Must weigh both Proposer and Critic outputs. Cannot skip either.",
    },
    "summarizer": {
        "may_produce":   ["summary", "changelog", "status_report"],
        "may_not":       ["verdict", "new_content", "critique"],
        "tone":          "concise, factual",
        "constraint":    "Must compress without distorting. Flag omissions explicitly.",
    },
    "orchestrator": {
        "may_produce":   ["task_assignment", "routing_decision", "escalation"],
        "may_not":       ["content_draft", "critique", "verdict"],
        "tone":          "directive, clear",
        "constraint":    "Must not do agent work itself — delegate, don't execute.",
    },
}


class PersonaGuardrails:
    """
    Checks that an agent's output is consistent with its defined role.
    Catches role bleed (e.g. a Critic rewriting instead of critiquing).
    """

    def check(
        self,
        agent_id: str,
        output_type: str,   # What the agent claims its output is
        result: AgentResult,
    ) -> GuardrailResult:
        issues: list[GuardrailIssue] = []
        role = ROLE_PERMISSIONS.get(agent_id)

        if not role:
            issues.append(GuardrailIssue(
                guardrail="unknown_role",
                severity="block",
                description=f"Agent '{agent_id}' has no defined role in ROLE_PERMISSIONS.",
                remedy="Add the agent's role definition to ROLE_PERMISSIONS.",
            ))
            return GuardrailResult(passed=False, issues=issues, verdict=ReviewVerdict.REJECT)

        # Check output type is permitted
        if output_type not in role["may_produce"]:
            issues.append(GuardrailIssue(
                guardrail="role_violation",
                severity="block",
                description=(
                    f"Agent '{agent_id}' produced output of type '{output_type}', "
                    f"which is outside its role. Permitted: {role['may_produce']}."
                ),
                remedy=f"Role constraint: {role['constraint']}",
            ))

        # Check for forbidden output types in the data
        if isinstance(result.data, dict):
            for forbidden in role["may_not"]:
                if forbidden in result.data:
                    issues.append(GuardrailIssue(
                        guardrail="forbidden_output_key",
                        severity="warn",
                        description=(
                            f"Agent '{agent_id}' result contains key '{forbidden}', "
                            f"which is a forbidden output type for this role."
                        ),
                        remedy=f"Remove '{forbidden}' from output. "
                               f"Role constraint: {role['constraint']}",
                    ))

        passed  = not any(i.severity == "block" for i in issues)
        verdict = ReviewVerdict.APPROVED if passed else ReviewVerdict.REJECT
        return GuardrailResult(passed=passed, issues=issues, verdict=verdict)


    def get_system_prompt_block(self, agent_id: str) -> str:
        """Inject role constraints directly into the agent's system prompt."""
        role = ROLE_PERMISSIONS.get(agent_id)
        if not role:
            return ""
        return f"""
YOUR ROLE: {agent_id.upper()}
  You MAY produce : {', '.join(role['may_produce'])}
  You MAY NOT     : {', '.join(role['may_not'])}
  Tone            : {role['tone']}
  Constraint      : {role['constraint']}

Violating your role definition will cause your output to be rejected by the pipeline.
""".strip()
