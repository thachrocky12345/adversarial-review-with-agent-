"""
artifact_parser.py
──────────────────
Parse raw data into structured Dispute Artifact format.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class DisputeArtifact:
    """Structured representation of a Dispute Artifact."""

    # Metadata
    dispute_id: str
    change_id: Optional[str] = None
    stage: str = "planning"  # planning | design | implementation | review
    artifact_under_review: Optional[str] = None
    opened_by: Optional[str] = None
    opened_at: Optional[str] = None
    current_pass: int = 1
    lifecycle_status: str = "open"  # open | under-synthesis | awaiting-arbitration | closed

    # Core question
    question: str = ""
    overall_stakes: Optional[str] = None

    # Actors
    actors: dict = field(default_factory=dict)

    # Agreements
    agreed_points: list[str] = field(default_factory=list)

    # Topics
    topics: list[dict] = field(default_factory=list)

    # Synthesis
    synthesis: dict = field(default_factory=dict)

    # Arbitration
    arbitration: dict = field(default_factory=dict)

    # Unresolved
    unresolved_points: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Generate markdown representation."""
        lines = [
            "# Dispute Artifact",
            "",
            "## Dispute metadata",
            "",
            f"- **dispute_id**: {self.dispute_id}",
            f"- **change_id**: {self.change_id or ''}",
            f"- **stage**: `{self.stage}`",
            f"- **artifact_under_review**: {self.artifact_under_review or ''}",
            f"- **opened_by**: {self.opened_by or ''}",
            f"- **opened_at**: {self.opened_at or ''}",
            f"- **current_pass**: {self.current_pass}",
            f"- **lifecycle_status**: `{self.lifecycle_status}`",
            "",
            "---",
            "",
            "## Question to resolve",
            "",
            f"- **question**: {self.question}",
            "",
        ]

        if self.overall_stakes:
            lines.extend([
                "---",
                "",
                "## Overall stakes",
                "",
                f"- **overall_stakes**: {self.overall_stakes}",
                "",
            ])

        # Actors
        lines.extend([
            "---",
            "",
            "## Actor registry",
            "",
        ])
        for actor_id, info in self.actors.items():
            lines.extend([
                f"- **{actor_id}**:",
                f"  - **role / actor**: {info.get('role', '')}",
                f"  - **general stance**: {info.get('stance', '')}",
                "",
            ])

        # Agreed points
        lines.extend([
            "---",
            "",
            "## Shared agreements",
            "",
            "- **agreed_points**:",
        ])
        for point in self.agreed_points:
            lines.append(f"  - {point}")
        lines.append("")

        # Topic tracker table
        lines.extend([
            "---",
            "",
            "## Topic Convergence Tracker",
            "",
            "| topic_id | topic_name | material_topic | stakes_tag | autonomous_pass_count | pass_1 | pass_2 | pass_3 | pass_4 |",
            "|---|---|---|---|---|---|---|---|---|",
        ])
        for topic in self.topics:
            passes = topic.get("passes", {})
            lines.append(
                f"| {topic.get('id', '')} | {topic.get('name', '')} | "
                f"{topic.get('material', 'yes')} | {topic.get('stakes', '')} | "
                f"{topic.get('pass_count', 0)} | "
                f"{passes.get('1', '')} | {passes.get('2', '')} | "
                f"{passes.get('3', '')} | {passes.get('4', '')} |"
            )
        lines.append("")

        # Topic details
        for topic in self.topics:
            lines.extend([
                "---",
                "",
                f"### Topic {topic.get('id', '')}",
                "",
                f"- **topic_name**: {topic.get('name', '')}",
                f"- **why_material**: {topic.get('why_material', '')}",
                f"- **stakes_detail**: {topic.get('stakes_detail', '')}",
                "",
            ])

            for actor_id in self.actors.keys():
                pos = topic.get("positions", {}).get(actor_id, {})
                lines.extend([
                    f"#### Position {actor_id}",
                    f"- **summary**: {pos.get('summary', '')}",
                    "- **supporting_evidence**:",
                ])
                for ev in pos.get("evidence", []):
                    lines.append(f"  - {ev}")
                lines.append("- **assumptions**:")
                for asm in pos.get("assumptions", []):
                    lines.append(f"  - {asm}")
                lines.append("")

        # Unresolved
        lines.extend([
            "---",
            "",
            "## Remaining disagreements",
            "",
            "- **unresolved_points**:",
        ])
        for point in self.unresolved_points:
            lines.append(f"  - {point}")
        lines.append("")

        # Synthesis
        if self.synthesis:
            lines.extend([
                "---",
                "",
                "## Synthesis summary",
                "",
                f"- **recommendation**: `{self.synthesis.get('recommendation', '')}`",
                f"- **recommendation_basis**: {self.synthesis.get('basis', '')}",
                "",
            ])

        # Arbitration
        if self.arbitration.get("outcome"):
            lines.extend([
                "---",
                "",
                "## Arbitration outcome",
                "",
                f"- **overall_outcome**: `{self.arbitration.get('outcome', 'unresolved')}`",
                f"- **arbitrated_by**: {self.arbitration.get('by', '')}",
                f"- **arbitrated_at**: {self.arbitration.get('at', '')}",
                f"- **decision_rationale**: {self.arbitration.get('rationale', '')}",
                "",
            ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "dispute_id": self.dispute_id,
            "change_id": self.change_id,
            "stage": self.stage,
            "artifact_under_review": self.artifact_under_review,
            "opened_by": self.opened_by,
            "opened_at": self.opened_at,
            "current_pass": self.current_pass,
            "lifecycle_status": self.lifecycle_status,
            "question": self.question,
            "overall_stakes": self.overall_stakes,
            "actors": self.actors,
            "agreed_points": self.agreed_points,
            "topics": self.topics,
            "synthesis": self.synthesis,
            "arbitration": self.arbitration,
            "unresolved_points": self.unresolved_points,
        }

    def save(self, output_dir: str) -> str:
        """Save artifact to file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save markdown
        md_path = output_path / f"{self.dispute_id}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())

        # Save JSON
        json_path = output_path / f"{self.dispute_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        return str(md_path)


class ArtifactParser:
    """
    Parse various data formats into DisputeArtifact.

    Supported sources:
        - CSV files (from database export)
        - JSON files
        - Raw conflict data
    """

    def __init__(self):
        self._dispute_counter = 0

    def generate_dispute_id(self) -> str:
        """Generate unique dispute ID."""
        self._dispute_counter += 1
        date_str = datetime.utcnow().strftime("%Y%m%d")
        return f"DISP-{date_str}-{self._dispute_counter:04d}"

    def from_csv_export(self, csv_dir: str) -> DisputeArtifact:
        """Parse from CSV export directory."""
        import csv
        csv_path = Path(csv_dir)

        # Load available files
        disputes = self._load_csv(csv_path / "disputes.csv")
        topics = self._load_csv(csv_path / "topics.csv")
        positions = self._load_csv(csv_path / "positions.csv")
        actors = self._load_csv(csv_path / "actors.csv")

        dispute = disputes[0] if disputes else {}

        return self._build_artifact(dispute, topics, positions, actors)

    def from_json(self, json_path: str) -> DisputeArtifact:
        """Parse from JSON file."""
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            # List of topics/conflicts
            return self._from_conflict_list(data)
        else:
            # Structured dispute data
            return self._from_structured_json(data)

    def from_conflict_data(
        self,
        conflicts: list[dict],
        actors: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> DisputeArtifact:
        """
        Create artifact from raw conflict data.

        Args:
            conflicts: List of conflict dicts with keys:
                - topic/issue: The topic name
                - positions: Dict of actor -> position
                - stakes: Stakes level (optional)
            actors: Actor registry (optional)
            metadata: Dispute metadata (optional)
        """
        metadata = metadata or {}
        actors = actors or {}

        artifact = DisputeArtifact(
            dispute_id=metadata.get("dispute_id", self.generate_dispute_id()),
            change_id=metadata.get("change_id"),
            stage=metadata.get("stage", "planning"),
            opened_by=metadata.get("opened_by"),
            opened_at=metadata.get("opened_at", datetime.utcnow().isoformat()),
            question=metadata.get("question", ""),
        )

        # Add actors
        for actor_id, info in actors.items():
            if isinstance(info, str):
                artifact.actors[actor_id] = {"role": info, "stance": ""}
            else:
                artifact.actors[actor_id] = info

        # Infer actors from conflicts if not provided
        if not artifact.actors:
            all_actors = set()
            for conflict in conflicts:
                positions = conflict.get("positions", {})
                all_actors.update(positions.keys())
            for i, actor in enumerate(sorted(all_actors)):
                artifact.actors[chr(65 + i)] = {"role": actor, "stance": ""}

        # Build topics
        for i, conflict in enumerate(conflicts, 1):
            topic_id = conflict.get("id", f"T{i}")
            topic = {
                "id": topic_id,
                "name": conflict.get("topic", conflict.get("issue", f"Topic {i}")),
                "material": conflict.get("material", "yes"),
                "stakes": conflict.get("stakes", "#moderate-to-reverse"),
                "why_material": conflict.get("why_material", ""),
                "stakes_detail": conflict.get("stakes_detail", ""),
                "pass_count": 1,
                "passes": {"1": "#new-topic"},
                "positions": {},
            }

            for actor_id, position in conflict.get("positions", {}).items():
                if isinstance(position, str):
                    topic["positions"][actor_id] = {
                        "summary": position[:300],
                        "evidence": [],
                        "assumptions": [],
                    }
                else:
                    topic["positions"][actor_id] = {
                        "summary": position.get("summary", "")[:300],
                        "evidence": position.get("evidence", []),
                        "assumptions": position.get("assumptions", []),
                    }

            artifact.topics.append(topic)

        return artifact

    def _load_csv(self, path: Path) -> list[dict]:
        """Load CSV file."""
        if not path.exists():
            return []
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _build_artifact(
        self,
        dispute: dict,
        topics: list[dict],
        positions: list[dict],
        actors: list[dict],
    ) -> DisputeArtifact:
        """Build artifact from parsed CSV data."""
        artifact = DisputeArtifact(
            dispute_id=dispute.get("dispute_id", self.generate_dispute_id()),
            change_id=dispute.get("change_id"),
            stage=dispute.get("stage", "planning"),
            artifact_under_review=dispute.get("artifact_under_review"),
            opened_by=dispute.get("opened_by"),
            opened_at=dispute.get("opened_at"),
            current_pass=int(dispute.get("current_pass", 1)),
            lifecycle_status=dispute.get("lifecycle_status", "open"),
            question=dispute.get("question", ""),
            overall_stakes=dispute.get("overall_stakes"),
        )

        # Add actors
        for actor in actors:
            actor_id = actor.get("actor_id", actor.get("id", ""))
            if actor_id:
                artifact.actors[actor_id] = {
                    "role": actor.get("role", ""),
                    "stance": actor.get("stance", actor.get("general_stance", "")),
                }

        # Build position lookup
        pos_lookup = {}
        for pos in positions:
            topic_id = pos.get("topic_id")
            actor_id = pos.get("actor_id", pos.get("actor", ""))
            if topic_id and actor_id:
                if topic_id not in pos_lookup:
                    pos_lookup[topic_id] = {}
                pos_lookup[topic_id][actor_id] = {
                    "summary": pos.get("summary", "")[:300],
                    "evidence": self._parse_list(pos.get("evidence", "")),
                    "assumptions": self._parse_list(pos.get("assumptions", "")),
                }

        # Build topics
        for topic_data in topics:
            topic_id = topic_data.get("topic_id", topic_data.get("id", ""))
            topic = {
                "id": topic_id,
                "name": topic_data.get("topic_name", topic_data.get("name", "")),
                "material": topic_data.get("material_topic", topic_data.get("material", "yes")),
                "stakes": topic_data.get("stakes_tag", topic_data.get("stakes", "")),
                "why_material": topic_data.get("why_material", ""),
                "stakes_detail": topic_data.get("stakes_detail", ""),
                "pass_count": int(topic_data.get("autonomous_pass_count", 0)),
                "passes": {},
                "positions": pos_lookup.get(topic_id, {}),
            }

            # Extract pass history
            for i in range(1, 10):
                pass_val = topic_data.get(f"pass_{i}", "")
                if pass_val:
                    topic["passes"][str(i)] = pass_val

            artifact.topics.append(topic)

        # Parse agreed/unresolved points
        artifact.agreed_points = self._parse_list(dispute.get("agreed_points", ""))
        artifact.unresolved_points = self._parse_list(dispute.get("unresolved_points", ""))

        return artifact

    def _from_conflict_list(self, data: list) -> DisputeArtifact:
        """Create artifact from list of conflicts."""
        return self.from_conflict_data(data)

    def _from_structured_json(self, data: dict) -> DisputeArtifact:
        """Create artifact from structured JSON."""
        return DisputeArtifact(
            dispute_id=data.get("dispute_id", self.generate_dispute_id()),
            change_id=data.get("change_id"),
            stage=data.get("stage", "planning"),
            artifact_under_review=data.get("artifact_under_review"),
            opened_by=data.get("opened_by"),
            opened_at=data.get("opened_at"),
            current_pass=data.get("current_pass", 1),
            lifecycle_status=data.get("lifecycle_status", "open"),
            question=data.get("question", ""),
            overall_stakes=data.get("overall_stakes"),
            actors=data.get("actors", {}),
            agreed_points=data.get("agreed_points", []),
            topics=data.get("topics", []),
            synthesis=data.get("synthesis", {}),
            arbitration=data.get("arbitration", {}),
            unresolved_points=data.get("unresolved_points", []),
        )

    def _parse_list(self, value: Any) -> list[str]:
        """Parse a list from various formats."""
        if isinstance(value, list):
            return value
        if not value:
            return []
        if isinstance(value, str):
            if value.startswith("["):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in value.split(";") if item.strip()]
        return []
