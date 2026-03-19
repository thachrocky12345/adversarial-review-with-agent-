"""
db_exporter.py
──────────────
Export database tables to CSV for dispute artifact analysis.
Supports SQLite, PostgreSQL, MySQL, and JSON sources.
"""

import csv
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class ExportManifest:
    """Manifest tracking all exported files."""
    source: str
    exported_at: str
    files: list[dict] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)

    def add_file(self, name: str, path: str, row_count: int) -> None:
        self.files.append({"name": name, "path": path, "rows": row_count})
        self.row_counts[name] = row_count

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "exported_at": self.exported_at,
            "total_files": len(self.files),
            "total_rows": sum(self.row_counts.values()),
            "files": self.files,
        }

    def save(self, output_dir: Path) -> str:
        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return str(manifest_path)


class BaseExporter(ABC):
    """Abstract base for database exporters."""

    DISPUTE_TABLE_PATTERNS = [
        "dispute", "conflict", "disagreement", "contention",
        "position", "topic", "actor", "pass", "synthesis",
    ]

    DISPUTE_COLUMN_PATTERNS = [
        "dispute_id", "topic_id", "actor", "stance", "position",
        "pass", "convergence", "stakes", "verdict", "outcome",
    ]

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to data source."""
        pass

    @abstractmethod
    def get_tables(self) -> list[str]:
        """List available tables/collections."""
        pass

    @abstractmethod
    def get_columns(self, table: str) -> list[str]:
        """Get column names for a table."""
        pass

    @abstractmethod
    def fetch_data(self, table: str) -> list[dict]:
        """Fetch all rows from a table as dicts."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close connection."""
        pass

    def detect_dispute_tables(self) -> list[str]:
        """Auto-detect tables related to disputes."""
        tables = self.get_tables()
        dispute_tables = []

        for table in tables:
            table_lower = table.lower()
            # Check table name patterns
            if any(p in table_lower for p in self.DISPUTE_TABLE_PATTERNS):
                dispute_tables.append(table)
                continue

            # Check column patterns
            try:
                columns = self.get_columns(table)
                column_str = " ".join(c.lower() for c in columns)
                if any(p in column_str for p in self.DISPUTE_COLUMN_PATTERNS):
                    dispute_tables.append(table)
            except Exception:
                pass

        return dispute_tables

    def export_to_csv(
        self,
        output_dir: Path,
        tables: Optional[list[str]] = None,
        auto_detect: bool = True,
    ) -> ExportManifest:
        """Export tables to CSV files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest = ExportManifest(
            source=self.__class__.__name__,
            exported_at=datetime.utcnow().isoformat(),
        )

        if tables is None:
            if auto_detect:
                tables = self.detect_dispute_tables()
            else:
                tables = self.get_tables()

        for table in tables:
            try:
                data = self.fetch_data(table)
                if not data:
                    continue

                csv_path = output_dir / f"{table}.csv"
                self._write_csv(csv_path, data)
                manifest.add_file(table, str(csv_path), len(data))

            except Exception as e:
                print(f"Warning: Failed to export {table}: {e}")

        manifest.save(output_dir)
        return manifest

    def _write_csv(self, path: Path, data: list[dict]) -> None:
        """Write list of dicts to CSV."""
        if not data:
            return

        fieldnames = list(data[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


class SQLiteExporter(BaseExporter):
    """Export from SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def get_tables(self) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table: str) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cursor.fetchall()]

    def fetch_data(self, table: str) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self.conn:
            self.conn.close()


class PostgresExporter(BaseExporter):
    """Export from PostgreSQL database."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.conn = None

    def connect(self) -> None:
        try:
            import psycopg2
            import psycopg2.extras
            self.conn = psycopg2.connect(self.connection_string)
        except ImportError:
            raise ImportError("psycopg2 required: pip install psycopg2-binary")

    def get_tables(self) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table: str) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table,))
        return [row[0] for row in cursor.fetchall()]

    def fetch_data(self, table: str) -> list[dict]:
        import psycopg2.extras
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(f"SELECT * FROM {table}")
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        if self.conn:
            self.conn.close()


class MySQLExporter(BaseExporter):
    """Export from MySQL database."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.conn = None

    def connect(self) -> None:
        try:
            import mysql.connector
            # Parse connection string: user:pass@host:port/database
            self.conn = mysql.connector.connect(
                **self._parse_connection_string()
            )
        except ImportError:
            raise ImportError("mysql-connector-python required: pip install mysql-connector-python")

    def _parse_connection_string(self) -> dict:
        # Simple parser for user:pass@host:port/database
        import re
        match = re.match(
            r"(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<database>.+)",
            self.connection_string
        )
        if not match:
            raise ValueError(f"Invalid connection string format")
        return match.groupdict()

    def get_tables(self) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute("SHOW TABLES")
        return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table: str) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute(f"DESCRIBE {table}")
        return [row[0] for row in cursor.fetchall()]

    def fetch_data(self, table: str) -> list[dict]:
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {table}")
        return list(cursor.fetchall())

    def close(self) -> None:
        if self.conn:
            self.conn.close()


class JSONExporter(BaseExporter):
    """Export from JSON file."""

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data: dict = {}

    def connect(self) -> None:
        with open(self.json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def get_tables(self) -> list[str]:
        if isinstance(self.data, dict):
            return list(self.data.keys())
        return ["data"]

    def get_columns(self, table: str) -> list[str]:
        table_data = self._get_table_data(table)
        if table_data and isinstance(table_data[0], dict):
            return list(table_data[0].keys())
        return []

    def _get_table_data(self, table: str) -> list:
        if isinstance(self.data, dict):
            return self.data.get(table, [])
        return self.data if isinstance(self.data, list) else []

    def fetch_data(self, table: str) -> list[dict]:
        table_data = self._get_table_data(table)
        if not table_data:
            return []
        if isinstance(table_data[0], dict):
            return table_data
        # Convert non-dict items to dicts
        return [{"value": item} for item in table_data]

    def close(self) -> None:
        self.data = {}


class DatabaseExporter:
    """
    Factory class for creating appropriate database exporters.

    Usage:
        exporter = DatabaseExporter.from_source("sqlite:./data/disputes.db")
        manifest = exporter.export("./dispute_exports/")
    """

    @staticmethod
    def from_source(source: str) -> BaseExporter:
        """
        Create exporter from source string.

        Formats:
            sqlite:<path>
            postgres:<connection_string>
            mysql:<connection_string>
            json:<path>
        """
        if ":" not in source:
            raise ValueError(f"Invalid source format: {source}. Expected type:connection")

        source_type, connection = source.split(":", 1)
        source_type = source_type.lower()

        exporters = {
            "sqlite": SQLiteExporter,
            "postgres": PostgresExporter,
            "postgresql": PostgresExporter,
            "mysql": MySQLExporter,
            "json": JSONExporter,
        }

        if source_type not in exporters:
            raise ValueError(f"Unknown source type: {source_type}. Supported: {list(exporters.keys())}")

        return exporters[source_type](connection)

    @staticmethod
    def export(
        source: str,
        output_dir: str = "./dispute_exports",
        tables: Optional[list[str]] = None,
        auto_detect: bool = True,
    ) -> ExportManifest:
        """
        Export from source to CSV files.

        Args:
            source: Database source string (e.g., "sqlite:./data.db")
            output_dir: Output directory for CSV files
            tables: Specific tables to export (None = auto-detect or all)
            auto_detect: If True, detect dispute-related tables

        Returns:
            ExportManifest with details of exported files
        """
        exporter = DatabaseExporter.from_source(source)
        try:
            exporter.connect()
            return exporter.export_to_csv(Path(output_dir), tables, auto_detect)
        finally:
            exporter.close()


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python db_exporter.py <source> [output_dir]")
        print("  source: sqlite:<path> | postgres:<conn> | mysql:<conn> | json:<path>")
        print("  output_dir: Directory for CSV files (default: ./dispute_exports)")
        sys.exit(1)

    source = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./dispute_exports"

    print(f"Exporting from {source} to {output_dir}...")
    manifest = DatabaseExporter.export(source, output_dir)

    print(f"\nExport complete!")
    print(f"  Files: {len(manifest.files)}")
    print(f"  Total rows: {sum(manifest.row_counts.values())}")
    print(f"  Manifest: {output_dir}/manifest.json")
