"""
convergence.py
──────────────
Check topic convergence and generate synthesis recommendations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConvergenceTag(Enum):
    NEW_TOPIC = "#new-topic"
    NARROWING = "#narrowing"
    UNCHANGED = "#unchanged"
    WIDENING = "#widening"


class StakesTag(Enum):
    EASILY_REVERSIBLE = "#easily-reversible"
    MODERATE_TO_REVERSE = "#moderate-to-reverse"
    HARD_TO_REVERSE = "#hard-to-reverse"


class Recommendation(Enum):
    CONTINUE = "continue-collaboration"
    ESCALATE = "escalate"
    AWAIT_HUMAN = "await-human"


@dataclass
class ConvergenceResult:
    """Result of convergence check for a topic."""
    topic_id: str
    current_tag: ConvergenceTag
    pass_count: int
    stakes: StakesTag
    requires_escalation: bool
    reason: Optional[str] = None
    suggested_action: str = "continue"


@dataclass
class SynthesisResult:
    """Result of synthesis analysis."""
    recommendation: Recommendation
    basis: str
    topics_resolved: list[str]
    topics_narrowed: list[str]
    topics_unchanged: list[str]
    topics_widened: list[str]
    new_topics: list[str]
    escalation_required: bool
    human_review_required: bool


class ConvergenceChecker:
    """
    Check convergence patterns and generate recommendations.

    Rules:
    1. #widening on any topic → escalate
    2. #unchanged + NOT #easily-reversible for 2+ passes → escalate
    3. #new-topic not #narrowing on second pass + NOT #easily-reversible → escalate
    4. 4+ passes without resolution → await-human
    5. All material topics #narrowing or #easily-reversible → continue
    """

    def check_topic(
        self,
        topic_id: str,
        convergence_history: list[str],
        stakes: str,
        material: bool = True,
    ) -> ConvergenceResult:
        """
        Check convergence for a single topic.

        Args:
            topic_id: Topic identifier
            convergence_history: List of convergence tags per pass
            stakes: Stakes tag string
            material: Whether topic is material

        Returns:
            ConvergenceResult with escalation determination
        """
        # Parse tags
        parsed_history = []
        for tag in convergence_history:
            tag_str = tag if tag.startswith("#") else f"#{tag}"
            try:
                parsed_history.append(ConvergenceTag(tag_str))
            except ValueError:
                parsed_history.append(ConvergenceTag.UNCHANGED)

        stakes_str = stakes if stakes.startswith("#") else f"#{stakes}"
        try:
            stakes_tag = StakesTag(stakes_str)
        except ValueError:
            stakes_tag = StakesTag.MODERATE_TO_REVERSE

        current = parsed_history[-1] if parsed_history else ConvergenceTag.NEW_TOPIC
        pass_count = len(parsed_history)

        # Non-material topics don't trigger escalation
        if not material:
            return ConvergenceResult(
                topic_id=topic_id,
                current_tag=current,
                pass_count=pass_count,
                stakes=stakes_tag,
                requires_escalation=False,
                reason="Non-material topic",
                suggested_action="monitor",
            )

        # Rule 1: Widening always escalates
        if current == ConvergenceTag.WIDENING:
            return ConvergenceResult(
                topic_id=topic_id,
                current_tag=current,
                pass_count=pass_count,
                stakes=stakes_tag,
                requires_escalation=True,
                reason="Topic is widening — disagreement expanding",
                suggested_action="escalate",
            )

        # Rule 2: Unchanged + high stakes for 2+ passes
        if (current == ConvergenceTag.UNCHANGED
                and stakes_tag != StakesTag.EASILY_REVERSIBLE
                and pass_count >= 2):
            return ConvergenceResult(
                topic_id=topic_id,
                current_tag=current,
                pass_count=pass_count,
                stakes=stakes_tag,
                requires_escalation=True,
                reason=f"Unchanged for {pass_count} passes with {stakes_tag.value} stakes",
                suggested_action="escalate",
            )

        # Rule 3: New topic not narrowing on second pass + high stakes
        if (pass_count >= 2
                and parsed_history[0] == ConvergenceTag.NEW_TOPIC
                and current != ConvergenceTag.NARROWING
                and stakes_tag != StakesTag.EASILY_REVERSIBLE):
            return ConvergenceResult(
                topic_id=topic_id,
                current_tag=current,
                pass_count=pass_count,
                stakes=stakes_tag,
                requires_escalation=True,
                reason="New topic not narrowing after first collaboration pass",
                suggested_action="escalate",
            )

        # Safe to continue
        if current == ConvergenceTag.NARROWING:
            action = "continue"
            reason = "Topic is converging"
        elif stakes_tag == StakesTag.EASILY_REVERSIBLE:
            action = "continue"
            reason = "Low stakes — safe to continue autonomously"
        elif current == ConvergenceTag.NEW_TOPIC:
            action = "continue"
            reason = "New topic — one collaboration pass allowed"
        else:
            action = "monitor"
            reason = "Unchanged but within acceptable bounds"

        return ConvergenceResult(
            topic_id=topic_id,
            current_tag=current,
            pass_count=pass_count,
            stakes=stakes_tag,
            requires_escalation=False,
            reason=reason,
            suggested_action=action,
        )

    def check_all_topics(
        self,
        topics: list[dict],
    ) -> list[ConvergenceResult]:
        """
        Check convergence for all topics.

        Args:
            topics: List of topic dicts with keys:
                - id/topic_id
                - passes: dict of pass_num -> tag or list of tags
                - stakes/stakes_tag
                - material/material_topic

        Returns:
            List of ConvergenceResult
        """
        results = []
        for topic in topics:
            topic_id = topic.get("id", topic.get("topic_id", "?"))

            # Extract convergence history
            passes = topic.get("passes", {})
            if isinstance(passes, dict):
                history = [passes.get(str(i), "") for i in range(1, 10) if passes.get(str(i))]
            elif isinstance(passes, list):
                history = passes
            else:
                history = []

            stakes = topic.get("stakes", topic.get("stakes_tag", "#moderate-to-reverse"))

            material_val = topic.get("material", topic.get("material_topic", "yes"))
            material = str(material_val).lower() in ("yes", "true", "1")

            result = self.check_topic(topic_id, history, stakes, material)
            results.append(result)

        return results

    def generate_synthesis(
        self,
        topics: list[dict],
        current_pass: int = 1,
        overall_stakes: Optional[str] = None,
    ) -> SynthesisResult:
        """
        Generate synthesis summary and recommendation.

        Args:
            topics: List of topic dicts
            current_pass: Current pass number
            overall_stakes: Overall dispute stakes (optional)

        Returns:
            SynthesisResult with recommendation
        """
        results = self.check_all_topics(topics)

        # Categorize topics
        resolved = []
        narrowed = []
        unchanged = []
        widened = []
        new_topics = []

        for result in results:
            if result.current_tag == ConvergenceTag.NARROWING:
                if result.pass_count >= 2:
                    resolved.append(result.topic_id)
                else:
                    narrowed.append(result.topic_id)
            elif result.current_tag == ConvergenceTag.UNCHANGED:
                unchanged.append(result.topic_id)
            elif result.current_tag == ConvergenceTag.WIDENING:
                widened.append(result.topic_id)
            elif result.current_tag == ConvergenceTag.NEW_TOPIC:
                new_topics.append(result.topic_id)

        # Determine escalation
        escalation_topics = [r for r in results if r.requires_escalation]
        escalation_required = len(escalation_topics) > 0

        # Rule 4: 4+ passes
        human_review_required = current_pass >= 4

        # Elevated overall stakes
        if overall_stakes and "high" in overall_stakes.lower():
            human_review_required = True

        # Determine recommendation
        if escalation_required:
            recommendation = Recommendation.ESCALATE
            basis = (
                f"{len(escalation_topics)} topic(s) require escalation: "
                f"{', '.join(r.topic_id for r in escalation_topics[:5])}"
            )
        elif human_review_required:
            recommendation = Recommendation.AWAIT_HUMAN
            if current_pass >= 4:
                basis = f"Dispute has continued for {current_pass} passes without resolution"
            else:
                basis = "Overall stakes require human review"
        else:
            # Check if all material topics are safe to continue
            material_results = [r for r in results
                               if r.stakes != StakesTag.EASILY_REVERSIBLE
                               or r.current_tag not in (ConvergenceTag.NARROWING, ConvergenceTag.NEW_TOPIC)]

            if not material_results or all(
                r.current_tag in (ConvergenceTag.NARROWING, ConvergenceTag.NEW_TOPIC)
                or r.stakes == StakesTag.EASILY_REVERSIBLE
                for r in results
            ):
                recommendation = Recommendation.CONTINUE
                basis = "All topics are narrowing, new, or easily reversible"
            else:
                recommendation = Recommendation.CONTINUE
                basis = "No immediate escalation triggers; continued monitoring recommended"

        return SynthesisResult(
            recommendation=recommendation,
            basis=basis,
            topics_resolved=resolved,
            topics_narrowed=narrowed,
            topics_unchanged=unchanged,
            topics_widened=widened,
            new_topics=new_topics,
            escalation_required=escalation_required,
            human_review_required=human_review_required,
        )

    def format_synthesis_report(self, synthesis: SynthesisResult) -> str:
        """Format synthesis result as markdown."""
        lines = [
            "## Synthesis Summary",
            "",
        ]

        if synthesis.topics_resolved:
            lines.append(f"- **topics_resolved_this_pass**: {', '.join(synthesis.topics_resolved)}")
        if synthesis.topics_narrowed:
            lines.append(f"- **topics_narrowed_this_pass**: {', '.join(synthesis.topics_narrowed)}")
        if synthesis.topics_unchanged:
            lines.append(f"- **topics_unchanged_this_pass**: {', '.join(synthesis.topics_unchanged)}")
        if synthesis.topics_widened:
            lines.append(f"- **topics_widened_this_pass**: {', '.join(synthesis.topics_widened)}")
        if synthesis.new_topics:
            lines.append(f"- **new_topics_this_pass**: {', '.join(synthesis.new_topics)}")

        lines.extend([
            "",
            f"- **recommendation**: `{synthesis.recommendation.value}`",
            f"- **recommendation_basis**: {synthesis.basis}",
            "",
        ])

        if synthesis.escalation_required:
            lines.append("**ESCALATION REQUIRED** - Route to arbitration step")
        elif synthesis.human_review_required:
            lines.append("**HUMAN REVIEW REQUIRED** - Stop autonomous progress")

        return "\n".join(lines)
