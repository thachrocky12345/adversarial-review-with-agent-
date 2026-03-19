"""
mcp_server.py
─────────────
MCP (Model Context Protocol) server for Dispute Artifact tools.

Exposes tools for database export, CSV analysis, and dispute management
to Claude and other MCP-compatible clients.

Run with: python -m tools.dispute_artifact.mcp_server
Or configure in claude_desktop_config.json
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.dispute_artifact.db_exporter import DatabaseExporter
from tools.dispute_artifact.csv_analyzer import DisputeAnalyzer
from tools.dispute_artifact.artifact_parser import ArtifactParser
from tools.dispute_artifact.convergence import ConvergenceChecker


class DisputeArtifactMCPServer:
    """
    MCP Server exposing Dispute Artifact tools.

    Tools:
        - db_to_csv: Export database to CSV files
        - csv_analyze: Analyze dispute CSV data
        - dispute_create: Create new dispute artifact
        - dispute_parse: Parse raw data into artifact format
        - convergence_check: Check topic convergence
        - synthesis_generate: Generate synthesis summary
    """

    def __init__(self):
        self.analyzer = DisputeAnalyzer()
        self.parser = ArtifactParser()
        self.convergence = ConvergenceChecker()

    def get_tools(self) -> list[dict]:
        """Return tool definitions for MCP."""
        return [
            {
                "name": "db_to_csv",
                "description": "Export database tables to CSV files for dispute analysis. Supports SQLite, PostgreSQL, MySQL, and JSON sources.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "Database source string. Format: sqlite:<path>, postgres:<connection>, mysql:<connection>, or json:<path>"
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Output directory for CSV files. Default: ./dispute_exports",
                            "default": "./dispute_exports"
                        },
                        "tables": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific tables to export. If not provided, auto-detects dispute-related tables."
                        },
                        "auto_detect": {
                            "type": "boolean",
                            "description": "Auto-detect dispute-related tables. Default: true",
                            "default": True
                        }
                    },
                    "required": ["source"]
                }
            },
            {
                "name": "csv_analyze",
                "description": "Analyze dispute CSV data and generate a structured report with convergence patterns, escalation flags, and recommendations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "csv_path": {
                            "type": "string",
                            "description": "Path to CSV file or directory containing exported CSVs"
                        },
                        "max_topics": {
                            "type": "integer",
                            "description": "Maximum topics to include in analysis. Default: 50",
                            "default": 50
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["markdown", "json"],
                            "description": "Output format. Default: markdown",
                            "default": "markdown"
                        }
                    },
                    "required": ["csv_path"]
                }
            },
            {
                "name": "dispute_create",
                "description": "Create a new Dispute Artifact from conflict data.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "conflicts": {
                            "type": "array",
                            "description": "List of conflicts. Each conflict should have: topic, positions (dict of actor -> position), stakes (optional)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string"},
                                    "positions": {"type": "object"},
                                    "stakes": {"type": "string"}
                                },
                                "required": ["topic", "positions"]
                            }
                        },
                        "actors": {
                            "type": "object",
                            "description": "Actor registry. Keys are actor IDs, values are role descriptions or {role, stance} objects."
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Dispute metadata: question, stage, opened_by, etc."
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Directory to save artifact. Default: ./disputes",
                            "default": "./disputes"
                        }
                    },
                    "required": ["conflicts"]
                }
            },
            {
                "name": "dispute_parse",
                "description": "Parse raw data (CSV export or JSON) into structured Dispute Artifact format.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "Path to source data (CSV directory or JSON file)"
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["markdown", "json", "both"],
                            "description": "Output format. Default: markdown",
                            "default": "markdown"
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Directory to save parsed artifact. If not provided, returns content without saving."
                        }
                    },
                    "required": ["source_path"]
                }
            },
            {
                "name": "convergence_check",
                "description": "Check topic convergence patterns and identify escalation candidates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topics": {
                            "type": "array",
                            "description": "List of topics with convergence history",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "passes": {
                                        "type": "object",
                                        "description": "Pass history: {\"1\": \"#new-topic\", \"2\": \"#narrowing\", ...}"
                                    },
                                    "stakes": {"type": "string"},
                                    "material": {"type": "boolean"}
                                },
                                "required": ["id", "passes"]
                            }
                        }
                    },
                    "required": ["topics"]
                }
            },
            {
                "name": "synthesis_generate",
                "description": "Generate synthesis summary with recommendation for a dispute.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topics": {
                            "type": "array",
                            "description": "List of topics with convergence data"
                        },
                        "current_pass": {
                            "type": "integer",
                            "description": "Current pass number. Default: 1",
                            "default": 1
                        },
                        "overall_stakes": {
                            "type": "string",
                            "description": "Overall dispute stakes (optional)"
                        }
                    },
                    "required": ["topics"]
                }
            }
        ]

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Execute a tool and return result."""
        try:
            if name == "db_to_csv":
                return self._db_to_csv(arguments)
            elif name == "csv_analyze":
                return self._csv_analyze(arguments)
            elif name == "dispute_create":
                return self._dispute_create(arguments)
            elif name == "dispute_parse":
                return self._dispute_parse(arguments)
            elif name == "convergence_check":
                return self._convergence_check(arguments)
            elif name == "synthesis_generate":
                return self._synthesis_generate(arguments)
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

    def _db_to_csv(self, args: dict) -> dict:
        """Export database to CSV."""
        source = args["source"]
        output_dir = args.get("output_dir", "./dispute_exports")
        tables = args.get("tables")
        auto_detect = args.get("auto_detect", True)

        manifest = DatabaseExporter.export(source, output_dir, tables, auto_detect)

        return {
            "success": True,
            "manifest": manifest.to_dict(),
            "output_dir": output_dir,
        }

    def _csv_analyze(self, args: dict) -> dict:
        """Analyze CSV data."""
        csv_path = args["csv_path"]
        max_topics = args.get("max_topics", 50)
        output_format = args.get("output_format", "markdown")

        self.analyzer.max_topics = max_topics

        path = Path(csv_path)
        if path.is_dir():
            analysis = self.analyzer.analyze_from_csv(csv_path)
        else:
            analysis = self.analyzer.analyze_single_csv(csv_path)

        if output_format == "json":
            return {
                "success": True,
                "analysis": analysis.to_dict(),
            }
        else:
            return {
                "success": True,
                "report": analysis.generate_report(max_topics),
                "summary": analysis.to_dict(),
            }

    def _dispute_create(self, args: dict) -> dict:
        """Create new dispute artifact."""
        conflicts = args["conflicts"]
        actors = args.get("actors", {})
        metadata = args.get("metadata", {})
        output_dir = args.get("output_dir", "./disputes")

        artifact = self.parser.from_conflict_data(conflicts, actors, metadata)
        saved_path = artifact.save(output_dir)

        return {
            "success": True,
            "dispute_id": artifact.dispute_id,
            "saved_to": saved_path,
            "artifact": artifact.to_dict(),
        }

    def _dispute_parse(self, args: dict) -> dict:
        """Parse source data into artifact."""
        source_path = args["source_path"]
        output_format = args.get("output_format", "markdown")
        output_dir = args.get("output_dir")

        path = Path(source_path)
        if path.is_dir():
            artifact = self.parser.from_csv_export(source_path)
        elif path.suffix == ".json":
            artifact = self.parser.from_json(source_path)
        else:
            return {"error": f"Unsupported source type: {path.suffix}"}

        result = {"success": True, "dispute_id": artifact.dispute_id}

        if output_format in ("markdown", "both"):
            result["markdown"] = artifact.to_markdown()
        if output_format in ("json", "both"):
            result["data"] = artifact.to_dict()

        if output_dir:
            saved_path = artifact.save(output_dir)
            result["saved_to"] = saved_path

        return result

    def _convergence_check(self, args: dict) -> dict:
        """Check topic convergence."""
        topics = args["topics"]

        results = self.convergence.check_all_topics(topics)

        return {
            "success": True,
            "results": [
                {
                    "topic_id": r.topic_id,
                    "current_tag": r.current_tag.value,
                    "pass_count": r.pass_count,
                    "stakes": r.stakes.value,
                    "requires_escalation": r.requires_escalation,
                    "reason": r.reason,
                    "suggested_action": r.suggested_action,
                }
                for r in results
            ],
            "escalation_required": any(r.requires_escalation for r in results),
        }

    def _synthesis_generate(self, args: dict) -> dict:
        """Generate synthesis summary."""
        topics = args["topics"]
        current_pass = args.get("current_pass", 1)
        overall_stakes = args.get("overall_stakes")

        synthesis = self.convergence.generate_synthesis(topics, current_pass, overall_stakes)

        return {
            "success": True,
            "recommendation": synthesis.recommendation.value,
            "basis": synthesis.basis,
            "topics_resolved": synthesis.topics_resolved,
            "topics_narrowed": synthesis.topics_narrowed,
            "topics_unchanged": synthesis.topics_unchanged,
            "topics_widened": synthesis.topics_widened,
            "new_topics": synthesis.new_topics,
            "escalation_required": synthesis.escalation_required,
            "human_review_required": synthesis.human_review_required,
            "report": self.convergence.format_synthesis_report(synthesis),
        }


# MCP Protocol Handler
def handle_mcp_request(request: dict) -> dict:
    """Handle MCP protocol requests."""
    server = DisputeArtifactMCPServer()
    method = request.get("method")

    if method == "tools/list":
        return {
            "tools": server.get_tools()
        }
    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        result = server.call_tool(name, arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    else:
        return {"error": f"Unknown method: {method}"}


def main():
    """Run MCP server (stdio mode)."""
    server = DisputeArtifactMCPServer()

    # Print server info
    print(json.dumps({
        "name": "dispute-artifact-server",
        "version": "1.0.0",
        "description": "MCP server for Dispute Artifact management",
        "tools": [t["name"] for t in server.get_tools()]
    }), file=sys.stderr)

    # Handle stdin/stdout MCP protocol
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_mcp_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON: {e}"}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
