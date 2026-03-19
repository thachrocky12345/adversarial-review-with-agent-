"""
orchestrator.py
───────────────
Runs the adversarial review loop:
  Proposer -> Critic -> Arbiter -> Decision

Token-aware at every step:
  - Assigns budgets before each agent runs
  - Enforces guardrails on every result
  - Handles partial/checkpoint/retry cleanly
  - Hard-caps total loop iterations to prevent runaway spend

Multi-provider support:
  - Each agent can use a different LLM provider
  - Configure via config.py or at runtime
"""

import json
import logging
import time
from typing import Optional

from core_types import (
    AgentResult, CompletionStatus, ReviewVerdict, TokenBudget
)
from budget_manager import TokenBudgetManager
from guardrails import ProjectIntegrityGuardrails, PersonaGuardrails
from llm_providers import get_provider, BaseLLMProvider
from config import get_agent_config

logger = logging.getLogger(__name__)

# ─── Orchestrator Config ─────────────────────────────────────────────────────

MAX_REVISION_ROUNDS = 3    # Proposer gets at most this many revision attempts
MAX_CRITIC_RETRIES  = 2    # Critic retried this many times on partial/fail
TURN_SUMMARY_EVERY  = 4    # Compress rolling buffer every N turns


# ─── Rolling Context Buffer ──────────────────────────────────────────────────

class RollingContextBuffer:
    """
    Prevents context explosion in multi-turn agent loops.
    Compresses oldest turns into a checkpoint summary every TURN_SUMMARY_EVERY turns.
    """

    def __init__(self, max_turns: int = TURN_SUMMARY_EVERY):
        self.max_turns = max_turns
        self.turns: list = []
        self.checkpoint_summary: str = ""
        # Use default provider for compression
        config = get_agent_config("arbiter")  # Use arbiter's provider for compression
        self._provider = get_provider(config["provider"], config["model"])

    def add(self, role: str, content: str) -> None:
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > self.max_turns:
            self._compress()

    def _compress(self) -> None:
        """Summarize oldest half of turns, keep recent half in full."""
        split = len(self.turns) // 2
        to_compress = self.turns[:split]
        self.turns = self.turns[split:]

        compress_prompt = (
            "Compress the following conversation turns into a concise summary "
            "that preserves all decisions, verdicts, issues, and checkpoints. "
            "Omit pleasantries and reasoning steps. Be dense and factual.\n\n"
            + "\n".join(f"{t['role'].upper()}: {t['content']}" for t in to_compress)
        )
        try:
            response = self._provider.complete(
                system="You are a compression assistant. Output only the summary.",
                messages=[{"role": "user", "content": compress_prompt}],
                max_tokens=600,
            )
            new_summary = response.text
            if self.checkpoint_summary:
                self.checkpoint_summary += "\n\n" + new_summary
            else:
                self.checkpoint_summary = new_summary
            logger.debug(f"Context compressed. Summary length: {len(self.checkpoint_summary)} chars")
        except Exception as e:
            logger.warning(f"Context compression failed: {e}. Keeping full turns.")

    def build_messages(self, new_user_message: str) -> list[dict]:
        """Build the message list to pass to the LLM."""
        messages = []
        if self.checkpoint_summary:
            messages.append({
                "role": "user",
                "content": f"[CONTEXT SUMMARY FROM EARLIER TURNS]\n{self.checkpoint_summary}"
            })
            messages.append({
                "role": "assistant",
                "content": "Understood. I have the prior context."
            })
        messages.extend(self.turns)
        messages.append({"role": "user", "content": new_user_message})
        return messages


# ─── Agent Runner ─────────────────────────────────────────────────────────────

class AgentRunner:
    """Runs a single agent turn via the configured LLM provider with budget enforcement."""

    def __init__(self):
        self._budget_mgr = TokenBudgetManager()
        self._proj_guard = ProjectIntegrityGuardrails()
        self._persona_guard = PersonaGuardrails()
        self._providers: dict[str, BaseLLMProvider] = {}

    def _get_provider(self, agent_id: str) -> BaseLLMProvider:
        """Get or create the LLM provider for an agent."""
        if agent_id not in self._providers:
            config = get_agent_config(agent_id)
            self._providers[agent_id] = get_provider(
                config["provider"], config["model"]
            )
        return self._providers[agent_id]

    def run(
        self,
        agent_id:      str,
        task_id:       str,
        system_prompt: str,
        user_message:  str,
        budget:        TokenBudget,
        output_type:   str,
        context:       Optional[RollingContextBuffer] = None,
    ) -> AgentResult:
        """
        Call the LLM as the given agent role with token budget enforcement.
        Returns an AgentResult — always, even on error.
        """
        start = time.time()

        # Build system prompt = role block + budget block
        full_system = (
            self._persona_guard.get_system_prompt_block(agent_id)
            + "\n\n"
            + budget.to_prompt_block()
            + "\n\n"
            + system_prompt
        )

        # Build messages (with rolling context if provided)
        if context:
            messages = context.build_messages(user_message)
        else:
            messages = [{"role": "user", "content": user_message}]

        try:
            provider = self._get_provider(agent_id)
            response = provider.complete(
                system=full_system,
                messages=messages,
                max_tokens=budget.output_tokens,
            )

            raw_text = response.text
            tokens_used = response.input_tokens
            elapsed = time.time() - start

            self._budget_mgr.record_usage(agent_id, tokens_used)

            # Parse JSON result from agent
            result_data = self._parse_json(raw_text)

            # Determine completion status from agent's declared status
            status = self._parse_status(result_data)
            verdict = self._parse_verdict(result_data)

            result = AgentResult(
                agent_id=agent_id,
                task_id=task_id,
                status=status,
                data=result_data,
                verdict=verdict,
                tokens_used=tokens_used,
                elapsed_sec=elapsed,
                checkpoint=result_data.get("checkpoint"),
                issues=result_data.get("issues", []),
            )

        except Exception as e:
            logger.error(f"[{agent_id}] API call failed: {e}")
            result = AgentResult(
                agent_id=agent_id,
                task_id=task_id,
                status=CompletionStatus.FAILED,
                data=None,
                error=str(e),
                elapsed_sec=time.time() - start,
            )

        # Run guardrails
        proj_check = self._proj_guard.check(result, task_id)
        if not proj_check.passed:
            logger.warning(f"[{agent_id}] Project guardrail failed:\n{proj_check.summary()}")
            result.issues.extend([vars(i) for i in proj_check.issues])
            if proj_check.is_blocked:
                result.status = CompletionStatus.FAILED
                result.verdict = ReviewVerdict.REJECT
                result.error = proj_check.summary()

        persona_check = self._persona_guard.check(agent_id, output_type, result)
        if not persona_check.passed:
            logger.warning(f"[{agent_id}] Persona guardrail failed:\n{persona_check.summary()}")
            result.issues.extend([vars(i) for i in persona_check.issues])

        logger.info(result.summary())
        return result

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict:
        try:
            clean = text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(clean)
        except Exception:
            return {"raw_text": text}

    def _parse_status(self, data: dict) -> CompletionStatus:
        status_map = {
            "complete":        CompletionStatus.COMPLETE,
            "partial_safe":    CompletionStatus.PARTIAL_SAFE,
            "partial_unsafe":  CompletionStatus.PARTIAL_UNSAFE,
            "budget_exceeded": CompletionStatus.BUDGET_EXCEEDED,
            "failed":          CompletionStatus.FAILED,
        }
        return status_map.get(
            data.get("status", "complete"), CompletionStatus.COMPLETE
        )

    def _parse_verdict(self, data: dict) -> Optional[ReviewVerdict]:
        verdict_map = {
            "approved":       ReviewVerdict.APPROVED,
            "approved_minor": ReviewVerdict.APPROVED_MINOR,
            "revise":         ReviewVerdict.REVISE,
            "reject":         ReviewVerdict.REJECT,
            "escalate":       ReviewVerdict.ESCALATE,
        }
        v = data.get("verdict") or data.get("verdict_recommendation")
        return verdict_map.get(v) if v else None


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class AdversarialReviewOrchestrator:
    """
    Runs the full adversarial review pipeline with token enforcement.

    Loop:
      1. Proposer generates draft (with budget)
      2. Critic reviews draft (with budget, adversarial posture)
      3. Arbiter renders verdict (with budget)
      4. Decision:
         - approved / approved_minor -> done
         - revise -> loop back to Proposer with revision instructions
         - reject -> start over (up to MAX_REVISION_ROUNDS)
         - escalate -> return to caller for human decision
         - partial/fail -> retry with expanded budget (up to MAX_CRITIC_RETRIES)
    """

    def __init__(self):
        self._runner = AgentRunner()
        self._budget_mgr = TokenBudgetManager()

    def run(
        self,
        task_id:      str,
        task_spec:    str,
        criteria:     list[str],
        complexity:   str = "normal",
    ) -> dict:
        """
        Run the adversarial review loop for a given task.

        Returns a dict with:
          verdict, final_draft, review_history, total_tokens_used
        """
        review_history = []
        total_tokens = 0
        revision_round = 0
        prior_feedback = ""  # Accumulates revision instructions across rounds
        proposer_result = None  # Track for final result

        while revision_round < MAX_REVISION_ROUNDS:
            revision_round += 1
            round_context = RollingContextBuffer()

            logger.info(f"=== Revision round {revision_round}/{MAX_REVISION_ROUNDS} ===")

            # ── Step 1: Proposer ──────────────────────────────────────────────
            proposer_budget = self._budget_mgr.assign("proposer", complexity)
            proposer_result = self._runner.run(
                agent_id="proposer",
                task_id=task_id,
                system_prompt=self._proposer_system(criteria),
                user_message=self._proposer_prompt(task_spec, prior_feedback),
                budget=proposer_budget,
                output_type="draft",
                context=round_context,
            )
            total_tokens += proposer_result.tokens_used
            review_history.append({"round": revision_round, "role": "proposer",
                                    "summary": proposer_result.summary()})
            round_context.add("assistant", json.dumps(proposer_result.data))

            if not proposer_result.is_usable:
                logger.error("Proposer failed. Aborting.")
                return self._terminal_result(
                    "proposer_failed", review_history, total_tokens
                )

            # ── Step 2: Critic ────────────────────────────────────────────────
            critic_result = None
            for critic_attempt in range(MAX_CRITIC_RETRIES + 1):
                retry_budget = (
                    self._budget_mgr.assign("critic", complexity,
                                            retry_of=critic_result.data.get("checkpoint")
                                            if critic_result else None)
                )
                critic_result = self._runner.run(
                    agent_id="critic",
                    task_id=task_id,
                    system_prompt=self._critic_system(criteria),
                    user_message=self._critic_prompt(
                        proposer_result.data,
                        checkpoint=critic_result.checkpoint if critic_result else None,
                    ),
                    budget=retry_budget,
                    output_type="critique",
                    context=round_context,
                )
                total_tokens += critic_result.tokens_used
                review_history.append({
                    "round": revision_round, "role": "critic",
                    "attempt": critic_attempt + 1,
                    "summary": critic_result.summary(),
                })

                if critic_result.is_usable:
                    break  # Good enough — proceed to Arbiter
                if critic_attempt == MAX_CRITIC_RETRIES:
                    logger.error("Critic failed after max retries.")
                    return self._terminal_result(
                        "critic_failed", review_history, total_tokens
                    )
                logger.warning(f"Critic attempt {critic_attempt+1} incomplete — retrying.")

            round_context.add("assistant", json.dumps(critic_result.data))

            # ── Step 3: Arbiter ───────────────────────────────────────────────
            arbiter_budget = self._budget_mgr.assign("arbiter", complexity)
            arbiter_result = self._runner.run(
                agent_id="arbiter",
                task_id=task_id,
                system_prompt=self._arbiter_system(),
                user_message=self._arbiter_prompt(proposer_result.data, critic_result.data),
                budget=arbiter_budget,
                output_type="verdict",
                context=round_context,
            )
            total_tokens += arbiter_result.tokens_used
            review_history.append({
                "round": revision_round, "role": "arbiter",
                "summary": arbiter_result.summary(),
                "verdict": arbiter_result.verdict.value if arbiter_result.verdict else "none",
            })

            # Arbiter PARTIAL_UNSAFE = no verdict — retry round
            if arbiter_result.status == CompletionStatus.PARTIAL_UNSAFE:
                logger.warning("Arbiter stopped mid-evaluation (PARTIAL_UNSAFE). Retrying round.")
                continue

            # ── Step 4: Decision ──────────────────────────────────────────────
            verdict = arbiter_result.verdict

            if verdict in (ReviewVerdict.APPROVED, ReviewVerdict.APPROVED_MINOR):
                logger.info(f"Draft approved ({verdict.value}) after {revision_round} round(s).")
                return {
                    "verdict":          verdict.value,
                    "final_draft":      proposer_result.data,
                    "arbiter_rationale": arbiter_result.data.get("rationale"),
                    "review_history":   review_history,
                    "total_tokens":     total_tokens,
                    "revision_rounds":  revision_round,
                }

            elif verdict == ReviewVerdict.ESCALATE:
                logger.info("Arbiter escalated to human review.")
                return {
                    "verdict":        "escalate",
                    "reason":         arbiter_result.data.get("human_escalation_reason"),
                    "draft":          proposer_result.data,
                    "critique":       critic_result.data,
                    "review_history": review_history,
                    "total_tokens":   total_tokens,
                }

            elif verdict == ReviewVerdict.REJECT:
                logger.warning("Draft rejected. Restarting proposal from scratch.")
                prior_feedback = (
                    "Previous draft was REJECTED. Do not reuse its structure. "
                    "Arbiter rationale: " + (arbiter_result.data.get("rationale") or "")
                )
                # Full restart — don't carry over the rejected draft

            elif verdict == ReviewVerdict.REVISE:
                instructions = arbiter_result.data.get("revision_instructions", [])
                prior_feedback = (
                    f"Round {revision_round} revision required. "
                    "Apply these specific changes:\n"
                    + "\n".join(f"- {i}" for i in instructions)
                )
                logger.info(f"Revision requested. Instructions: {prior_feedback}")

        # Exhausted revision rounds
        logger.error(f"Max revision rounds ({MAX_REVISION_ROUNDS}) reached without approval.")
        return {
            "verdict":        "max_rounds_exceeded",
            "review_history": review_history,
            "total_tokens":   total_tokens,
            "last_draft":     proposer_result.data if proposer_result else None,
        }

    # ─── Prompt Builders ──────────────────────────────────────────────────────

    def _proposer_system(self, criteria: list[str]) -> str:
        return (
            "You generate high-quality drafts. Always respond in valid JSON.\n"
            "Criteria your draft must satisfy:\n"
            + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))
        )

    def _proposer_prompt(self, task_spec: str, prior_feedback: str) -> str:
        base = f"Task specification:\n{task_spec}"
        if prior_feedback:
            base += f"\n\nRevision feedback from prior round:\n{prior_feedback}"
        return base

    def _critic_system(self, criteria: list[str]) -> str:
        return (
            "You are an adversarial critic. Review drafts against the criteria below. "
            "Be specific, cite locations, and flag all issues. Always respond in valid JSON.\n"
            "Criteria to check (in priority order — most critical first):\n"
            + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))
        )

    def _critic_prompt(self, draft: dict, checkpoint: Optional[dict] = None) -> str:
        prompt = f"Review this draft:\n{json.dumps(draft, indent=2)}"
        if checkpoint:
            prompt += (
                f"\n\nRESUMING FROM CHECKPOINT: You previously completed criteria: "
                f"{checkpoint.get('criteria_done', [])}. "
                f"Continue from: {checkpoint.get('criteria_remaining', [])}."
            )
        return prompt

    def _arbiter_system(self) -> str:
        return (
            "You are the Arbiter. You receive a draft and its critique. "
            "Render a binding verdict by weighing both sides. "
            "Address every 'block'-severity issue before approving. "
            "Always respond in valid JSON."
        )

    def _arbiter_prompt(self, draft: dict, critique: dict) -> str:
        return (
            f"DRAFT:\n{json.dumps(draft, indent=2)}\n\n"
            f"CRITIQUE:\n{json.dumps(critique, indent=2)}"
        )

    def _terminal_result(self, reason: str, history: list, tokens: int) -> dict:
        return {
            "verdict":        "pipeline_failure",
            "reason":         reason,
            "review_history": history,
            "total_tokens":   tokens,
        }
