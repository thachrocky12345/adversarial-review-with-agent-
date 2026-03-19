"""
cli.py
──────
Command-line interface for Dispute Artifact tools.

Usage:
    python -m tools.dispute_artifact.cli export sqlite:./data.db
    python -m tools.dispute_artifact.cli analyze ./dispute_exports/
    python -m tools.dispute_artifact.cli create --from ./conflicts.json
    python -m tools.dispute_artifact.cli status DISP-20240115-0001
    python -m tools.dispute_artifact.cli synthesize DISP-20240115-0001
"""

import argparse
import json
import sys
from pathlib import Path

from .db_exporter import DatabaseExporter
from .csv_analyzer import DisputeAnalyzer
from .artifact_parser import ArtifactParser
from .convergence import ConvergenceChecker


def cmd_export(args):
    """Export database to CSV."""
    print(f"Exporting from {args.source}...")

    manifest = DatabaseExporter.export(
        source=args.source,
        output_dir=args.output,
        tables=args.tables,
        auto_detect=not args.all_tables,
    )

    print(f"\nExport complete!")
    print(f"  Files: {len(manifest.files)}")
    print(f"  Rows: {sum(manifest.row_counts.values())}")
    print(f"  Output: {args.output}")

    for file_info in manifest.files:
        print(f"    - {file_info['name']}: {file_info['rows']} rows")


def cmd_analyze(args):
    """Analyze dispute data."""
    analyzer = DisputeAnalyzer(max_topics=args.max_topics)

    path = Path(args.path)
    if path.is_dir():
        analysis = analyzer.analyze_from_csv(args.path)
    else:
        analysis = analyzer.analyze_single_csv(args.path)

    if args.format == "json":
        print(json.dumps(analysis.to_dict(), indent=2))
    else:
        print(analysis.generate_report(args.max_topics))


def cmd_create(args):
    """Create new dispute artifact."""
    parser = ArtifactParser()

    if args.source:
        # Load from file
        source_path = Path(args.source)
        if source_path.suffix == ".json":
            with open(source_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                artifact = parser.from_conflict_data(data)
            else:
                conflicts = data.get("conflicts", [])
                actors = data.get("actors", {})
                metadata = data.get("metadata", {})
                artifact = parser.from_conflict_data(conflicts, actors, metadata)
        else:
            artifact = parser.from_csv_export(str(source_path.parent))
    else:
        # Interactive mode
        print("Interactive dispute creation not implemented.")
        print("Use --from <file> to create from JSON or CSV data.")
        sys.exit(1)

    saved_path = artifact.save(args.output)
    print(f"Created dispute: {artifact.dispute_id}")
    print(f"Saved to: {saved_path}")


def cmd_status(args):
    """Check dispute status."""
    dispute_path = Path(args.output) / f"{args.dispute_id}.json"

    if not dispute_path.exists():
        print(f"Dispute not found: {args.dispute_id}")
        sys.exit(1)

    with open(dispute_path) as f:
        data = json.load(f)

    print(f"Dispute: {data['dispute_id']}")
    print(f"Status: {data['lifecycle_status']}")
    print(f"Pass: {data['current_pass']}")
    print(f"Topics: {len(data.get('topics', []))}")

    # Check convergence
    checker = ConvergenceChecker()
    topics = data.get("topics", [])
    if topics:
        synthesis = checker.generate_synthesis(topics, data.get("current_pass", 1))
        print(f"\nRecommendation: {synthesis.recommendation.value}")
        print(f"Basis: {synthesis.basis}")
        if synthesis.escalation_required:
            print("\n** ESCALATION REQUIRED **")


def cmd_synthesize(args):
    """Run synthesis on dispute."""
    dispute_path = Path(args.output) / f"{args.dispute_id}.json"

    if not dispute_path.exists():
        print(f"Dispute not found: {args.dispute_id}")
        sys.exit(1)

    with open(dispute_path) as f:
        data = json.load(f)

    checker = ConvergenceChecker()
    topics = data.get("topics", [])
    current_pass = data.get("current_pass", 1)
    overall_stakes = data.get("overall_stakes")

    synthesis = checker.generate_synthesis(topics, current_pass, overall_stakes)
    print(checker.format_synthesis_report(synthesis))


def main():
    parser = argparse.ArgumentParser(
        description="Dispute Artifact CLI",
        prog="dispute-artifact",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export command
    export_parser = subparsers.add_parser("export", help="Export database to CSV")
    export_parser.add_argument("source", help="Database source (sqlite:<path>, postgres:<conn>, etc.)")
    export_parser.add_argument("-o", "--output", default="./dispute_exports", help="Output directory")
    export_parser.add_argument("-t", "--tables", nargs="+", help="Specific tables to export")
    export_parser.add_argument("--all-tables", action="store_true", help="Export all tables (disable auto-detect)")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze dispute CSV data")
    analyze_parser.add_argument("path", help="Path to CSV file or directory")
    analyze_parser.add_argument("-f", "--format", choices=["markdown", "json"], default="markdown")
    analyze_parser.add_argument("--max-topics", type=int, default=50, help="Max topics to analyze")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create new dispute artifact")
    create_parser.add_argument("--from", dest="source", help="Source JSON file with conflict data")
    create_parser.add_argument("-o", "--output", default="./disputes", help="Output directory")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check dispute status")
    status_parser.add_argument("dispute_id", help="Dispute ID to check")
    status_parser.add_argument("-d", "--output", default="./disputes", help="Disputes directory")

    # Synthesize command
    synth_parser = subparsers.add_parser("synthesize", help="Run synthesis on dispute")
    synth_parser.add_argument("dispute_id", help="Dispute ID to synthesize")
    synth_parser.add_argument("-d", "--output", default="./disputes", help="Disputes directory")

    args = parser.parse_args()

    commands = {
        "export": cmd_export,
        "analyze": cmd_analyze,
        "create": cmd_create,
        "status": cmd_status,
        "synthesize": cmd_synthesize,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
