"""
csv_analyzer.py
───────────────
Analyze dispute CSV data and generate structured reports.
Fits analysis within context window limits.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from enum import Enum


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
    CONTINUE_COLLABORATION = "continue-collaboration"
    ESCALATE = "escalate"
    AWAIT_HUMAN = "await-human"


class LifecycleStatus(Enum):
    OPEN = "open"
    UNDER_SYNTHESIS = "under-synthesis"
    AWAITING_ARBITRATION = "awaiting-arbitration"
    CLOSED = "closed"


@dataclass
class TopicAnalysis:
    """Analysis result for a single topic."""
    topic_id: str
    topic_name: str
    material: bool
    stakes: StakesTag
    pass_count: int
    convergence_history: list[ConvergenceTag]
    current_convergence: ConvergenceTag
    positions: dict[str, str]  # actor -> summary
    action_required: str
    escalation_reason: Optional[str] = None

    @property
    def is_escalation_candidate(self) -> bool:
        """Check if topic should be escalated."""
        # Widening = always escalate
        if self.current_convergence == ConvergenceTag.WIDENING:
            return True

        # Unchanged + not easily reversible for 2+ passes
        if (self.current_convergence == ConvergenceTag.UNCHANGED
                and self.stakes != StakesTag.EASILY_REVERSIBLE
                and self.pass_count >= 2):
            return True

        # New topic not narrowing on second pass + not easily reversible
        if (len(self.convergence_history) >= 2
                and self.convergence_history[0] == ConvergenceTag.NEW_TOPIC
                and self.current_convergence != ConvergenceTag.NARROWING
                and self.stakes != StakesTag.EASILY_REVERSIBLE):
            return True

        return False

    def to_summary_row(self) -> dict:
        """Generate summary row for report table."""
        return {
            "topic_id": self.topic_id,
            "topic_name": self.topic_name[:30] + "..." if len(self.topic_name) > 30 else self.topic_name,
            "material": "Yes" if self.material else "No",
            "stakes": self.stakes.value.replace("#", ""),
            "passes": self.pass_count,
            "trajectory": self.current_convergence.value,
            "action": self.action_required,
        }


@dataclass
class DisputeAnalysis:
    """Complete analysis of a dispute."""
    dispute_id: str
    lifecycle_status: LifecycleStatus
    total_passes: int
    topics: list[TopicAnalysis]
    actors: dict[str, dict]  # actor_id -> {role, stance}
    agreed_points: list[str]
    unresolved_points: list[str]
    recommendation: Recommendation
    recommendation_basis: str
    overall_trajectory: str
    escalation_flags: list[str]
    analysis_timestamp: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    @property
    def material_topics(self) -> list[TopicAnalysis]:
        return [t for t in self.topics if t.material]

    @property
    def escalation_candidates(self) -> list[TopicAnalysis]:
        return [t for t in self.topics if t.is_escalation_candidate]

    def generate_report(self, max_topics: int = 50) -> str:
        """Generate markdown report within context limits."""
        lines = [
            "## Dispute Analysis Report",
            "",
            f"- **dispute_id**: {self.dispute_id}",
            f"- **status**: {self.lifecycle_status.value}",
            f"- **total_passes**: {self.total_passes}",
            f"- **overall_trajectory**: {self.overall_trajectory}",
            f"- **analyzed_at**: {self.analysis_timestamp}",
            "",
        ]

        # Actor summary
        lines.append("### Actors")
        for actor_id, info in self.actors.items():
            lines.append(f"- **{actor_id}**: {info.get('role', 'Unknown')} — {info.get('stance', '')[:100]}")
        lines.append("")

        # Topic summary table
        lines.append("### Topic Summary")
        lines.append("")
        lines.append("| Topic | Stakes | Trajectory | Action Required |")
        lines.append("|-------|--------|------------|-----------------|")

        # Prioritize: material first, then by stakes severity
        sorted_topics = sorted(
            self.topics[:max_topics],
            key=lambda t: (
                not t.material,
                0 if t.stakes == StakesTag.HARD_TO_REVERSE else
                1 if t.stakes == StakesTag.MODERATE_TO_REVERSE else 2,
            )
        )

        for topic in sorted_topics:
            row = topic.to_summary_row()
            lines.append(
                f"| {row['topic_id']} | {row['stakes']} | {row['trajectory']} | {row['action']} |"
            )
        lines.append("")

        # Escalation flags
        if self.escalation_flags:
            lines.append("### Escalation Flags")
            lines.append("")
            for flag in self.escalation_flags:
                lines.append(f"- {flag}")
            lines.append("")

        # Agreed points
        if self.agreed_points:
            lines.append("### Shared Agreements")
            lines.append("")
            for point in self.agreed_points[:10]:
                lines.append(f"- {point}")
            lines.append("")

        # Unresolved points
        if self.unresolved_points:
            lines.append("### Remaining Disagreements")
            lines.append("")
            for point in self.unresolved_points[:10]:
                lines.append(f"- {point}")
            lines.append("")

        # Recommendation
        lines.append("### Recommendation")
        lines.append("")
        lines.append(f"**{self.recommendation.value}**")
        lines.append("")
        lines.append(f"*Basis*: {self.recommendation_basis}")
        lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "dispute_id": self.dispute_id,
            "lifecycle_status": self.lifecycle_status.value,
            "total_passes": self.total_passes,
            "overall_trajectory": self.overall_trajectory,
            "recommendation": self.recommendation.value,
            "recommendation_basis": self.recommendation_basis,
            "topic_count": len(self.topics),
            "material_topic_count": len(self.material_topics),
            "escalation_candidate_count": len(self.escalation_candidates),
            "escalation_flags": self.escalation_flags,
            "analysis_timestamp": self.analysis_timestamp,
        }


class DisputeAnalyzer:
    """
    Analyze dispute data from CSV files.

    Usage:
        analyzer = DisputeAnalyzer()
        analysis = analyzer.analyze_from_csv("./dispute_exports/")
        print(analysis.generate_report())
    """

    def __init__(self, max_topics: int = 50, max_summary_chars: int = 300):
        self.max_topics = max_topics
        self.max_summary_chars = max_summary_chars

    def analyze_from_csv(self, csv_dir: str) -> DisputeAnalysis:
        """
        Analyze dispute data from exported CSV files.

        Expects directory with:
            - disputes.csv or manifest.json
            - topics.csv
            - positions.csv (optional)
            - passes.csv (optional)
            - actors.csv (optional)
        """
        csv_path = Path(csv_dir)

        # Load manifest if available
        manifest_path = csv_path / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
        else:
            manifest = None

        # Load available data
        disputes = self._load_csv(csv_path / "disputes.csv")
        topics = self._load_csv(csv_path / "topics.csv")
        positions = self._load_csv(csv_path / "positions.csv")
        passes = self._load_csv(csv_path / "passes.csv")
        actors = self._load_csv(csv_path / "actors.csv")

        # Use first dispute if multiple
        dispute = disputes[0] if disputes else {}

        return self._build_analysis(dispute, topics, positions, passes, actors)

    def analyze_single_csv(self, csv_path: str) -> DisputeAnalysis:
        """Analyze a single CSV file containing dispute data."""
        data = self._load_csv(Path(csv_path))
        return self._analyze_flat_data(data)

    def _load_csv(self, path: Path) -> list[dict]:
        """Load CSV file to list of dicts."""
        if not path.exists():
            return []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _build_analysis(
        self,
        dispute: dict,
        topics: list[dict],
        positions: list[dict],
        passes: list[dict],
        actors: list[dict],
    ) -> DisputeAnalysis:
        """Build DisputeAnalysis from loaded data."""

        dispute_id = dispute.get("dispute_id", dispute.get("id", "UNKNOWN"))

        # Parse lifecycle status
        status_str = dispute.get("lifecycle_status", "open")
        try:
            lifecycle_status = LifecycleStatus(status_str)
        except ValueError:
            lifecycle_status = LifecycleStatus.OPEN

        # Build actor registry
        actor_registry = {}
        for actor in actors:
            actor_id = actor.get("actor_id", actor.get("id", ""))
            if actor_id:
                actor_registry[actor_id] = {
                    "role": actor.get("role", ""),
                    "stance": actor.get("stance", actor.get("general_stance", "")),
                }

        # Build topic analyses
        topic_analyses = []
        for topic_data in topics[:self.max_topics]:
            topic_analysis = self._analyze_topic(topic_data, positions, passes)
            topic_analyses.append(topic_analysis)

        # Calculate overall trajectory
        if not topic_analyses:
            overall_trajectory = "no-topics"
        else:
            widening = sum(1 for t in topic_analyses if t.current_convergence == ConvergenceTag.WIDENING)
            narrowing = sum(1 for t in topic_analyses if t.current_convergence == ConvergenceTag.NARROWING)
            unchanged = sum(1 for t in topic_analyses if t.current_convergence == ConvergenceTag.UNCHANGED)

            if widening > narrowing:
                overall_trajectory = "widening"
            elif narrowing > widening + unchanged:
                overall_trajectory = "narrowing"
            else:
                overall_trajectory = "stalled"

        # Generate escalation flags
        escalation_flags = []
        for topic in topic_analyses:
            if topic.is_escalation_candidate:
                escalation_flags.append(
                    f"{topic.topic_id}: {topic.escalation_reason or 'Requires review'}"
                )

        # Determine recommendation
        recommendation, basis = self._determine_recommendation(
            topic_analyses, overall_trajectory, int(dispute.get("current_pass", 1))
        )

        # Parse agreed/unresolved points
        agreed = self._parse_list_field(dispute.get("agreed_points", ""))
        unresolved = self._parse_list_field(dispute.get("unresolved_points", ""))

        return DisputeAnalysis(
            dispute_id=dispute_id,
            lifecycle_status=lifecycle_status,
            total_passes=int(dispute.get("current_pass", 1)),
            topics=topic_analyses,
            actors=actor_registry,
            agreed_points=agreed,
            unresolved_points=unresolved,
            recommendation=recommendation,
            recommendation_basis=basis,
            overall_trajectory=overall_trajectory,
            escalation_flags=escalation_flags,
        )

    def _analyze_topic(
        self,
        topic_data: dict,
        positions: list[dict],
        passes: list[dict],
    ) -> TopicAnalysis:
        """Analyze a single topic."""
        topic_id = topic_data.get("topic_id", topic_data.get("id", "T?"))
        topic_name = topic_data.get("topic_name", topic_data.get("name", "Unknown"))

        # Parse material flag
        material_str = str(topic_data.get("material_topic", topic_data.get("material", "yes"))).lower()
        material = material_str in ("yes", "true", "1")

        # Parse stakes
        stakes_str = topic_data.get("stakes_tag", topic_data.get("stakes", "#easily-reversible"))
        if not stakes_str.startswith("#"):
            stakes_str = f"#{stakes_str}"
        try:
            stakes = StakesTag(stakes_str)
        except ValueError:
            stakes = StakesTag.EASILY_REVERSIBLE

        # Parse convergence history from pass columns
        convergence_history = []
        for i in range(1, 10):
            pass_col = f"pass_{i}"
            if pass_col in topic_data and topic_data[pass_col]:
                tag_str = topic_data[pass_col]
                if not tag_str.startswith("#"):
                    tag_str = f"#{tag_str}"
                try:
                    convergence_history.append(ConvergenceTag(tag_str))
                except ValueError:
                    pass

        # Current convergence is last in history, or new-topic
        current_convergence = convergence_history[-1] if convergence_history else ConvergenceTag.NEW_TOPIC

        # Get positions for this topic
        topic_positions = {}
        for pos in positions:
            if pos.get("topic_id") == topic_id:
                actor = pos.get("actor_id", pos.get("actor", ""))
                summary = pos.get("summary", pos.get("position", ""))[:self.max_summary_chars]
                if actor:
                    topic_positions[actor] = summary

        # Determine action required
        if current_convergence == ConvergenceTag.WIDENING:
            action = "ESCALATE"
            escalation_reason = "Topic is widening — requires human arbitration"
        elif current_convergence == ConvergenceTag.UNCHANGED and stakes != StakesTag.EASILY_REVERSIBLE:
            if len(convergence_history) >= 2:
                action = "ESCALATE"
                escalation_reason = f"Unchanged for {len(convergence_history)} passes with {stakes.value} stakes"
            else:
                action = "Monitor"
                escalation_reason = None
        elif current_convergence == ConvergenceTag.NARROWING:
            action = "Continue"
            escalation_reason = None
        else:
            action = "Continue"
            escalation_reason = None

        return TopicAnalysis(
            topic_id=topic_id,
            topic_name=topic_name,
            material=material,
            stakes=stakes,
            pass_count=len(convergence_history),
            convergence_history=convergence_history,
            current_convergence=current_convergence,
            positions=topic_positions,
            action_required=action,
            escalation_reason=escalation_reason,
        )

    def _determine_recommendation(
        self,
        topics: list[TopicAnalysis],
        trajectory: str,
        pass_count: int,
    ) -> tuple[Recommendation, str]:
        """Determine overall recommendation."""

        material_topics = [t for t in topics if t.material]
        escalation_candidates = [t for t in material_topics if t.is_escalation_candidate]

        # Must escalate if any material topic is escalation candidate
        if escalation_candidates:
            return (
                Recommendation.ESCALATE,
                f"{len(escalation_candidates)} material topic(s) require escalation: "
                f"{', '.join(t.topic_id for t in escalation_candidates[:5])}"
            )

        # 4+ passes without resolution = await human
        if pass_count >= 4:
            return (
                Recommendation.AWAIT_HUMAN,
                f"Dispute has gone {pass_count} passes without resolution"
            )

        # All material topics converging = continue
        all_narrowing_or_safe = all(
            t.current_convergence == ConvergenceTag.NARROWING
            or t.stakes == StakesTag.EASILY_REVERSIBLE
            or t.current_convergence == ConvergenceTag.NEW_TOPIC
            for t in material_topics
        )

        if all_narrowing_or_safe:
            return (
                Recommendation.CONTINUE_COLLABORATION,
                "All material topics are narrowing or easily reversible"
            )

        # Default to continue with monitoring
        return (
            Recommendation.CONTINUE_COLLABORATION,
            "No immediate escalation triggers, but monitor unchanged topics"
        )

    def _parse_list_field(self, value: str) -> list[str]:
        """Parse a list stored as string."""
        if not value:
            return []
        # Try JSON parse
        if value.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        # Split by newlines or semicolons
        items = value.replace(";", "\n").split("\n")
        return [item.strip() for item in items if item.strip()]

    def _analyze_flat_data(self, data: list[dict]) -> DisputeAnalysis:
        """Analyze flat CSV data (all in one file)."""
        # Group by dispute_id if present
        if data and "dispute_id" in data[0]:
            dispute = {"dispute_id": data[0]["dispute_id"]}
        else:
            dispute = {"dispute_id": "INFERRED"}

        # Treat rows as topics
        return self._build_analysis(dispute, data, [], [], [])


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python csv_analyzer.py <csv_dir_or_file>")
        sys.exit(1)

    path = sys.argv[1]
    analyzer = DisputeAnalyzer()

    if Path(path).is_dir():
        analysis = analyzer.analyze_from_csv(path)
    else:
        analysis = analyzer.analyze_single_csv(path)

    print(analysis.generate_report())
