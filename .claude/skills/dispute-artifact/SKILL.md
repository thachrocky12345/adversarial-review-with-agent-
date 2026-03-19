# /dispute-artifact — Dispute Analysis and Database Export Skill

When `/dispute-artifact` is invoked, follow the workflow below based on the subcommand.

---

## Subcommands

### `/dispute-artifact export <source>`
Export data from a database source to CSV for analysis.

**Supported sources:**
- `sqlite:<path>` — SQLite database file
- `postgres:<connection_string>` — PostgreSQL database
- `mysql:<connection_string>` — MySQL database
- `json:<path>` — JSON file with dispute data
- `csv:<path>` — Existing CSV (for validation/re-analysis)

**Actions:**
1. Connect to the specified data source
2. Detect dispute-related tables/collections
3. Export to CSV files in `./dispute_exports/`
4. Generate a manifest file listing all exported files

### `/dispute-artifact analyze [--file <csv_path>] [--dispute-id <id>]`
Analyze dispute data and generate a structured report.

**Actions:**
1. Load dispute data from CSV or database
2. Parse into Dispute Artifact format
3. Analyze convergence patterns across passes
4. Identify:
   - Topics trending `#widening` (escalation candidates)
   - Topics stuck `#unchanged` with high stakes
   - Stalled disputes (no progress across 2+ passes)
5. Output analysis summary within context window limits

### `/dispute-artifact create [--from <csv_path>]`
Create a new Dispute Artifact from data or interactively.

**Actions:**
1. If `--from` provided, populate from CSV data
2. Generate dispute_id (format: `DISP-YYYYMMDD-XXXX`)
3. Create structured artifact following template
4. Save to `./disputes/<dispute_id>.md`

### `/dispute-artifact status [--dispute-id <id>]`
Check the current status of a dispute.

**Actions:**
1. Load dispute artifact
2. Summarize:
   - Current lifecycle_status
   - Pass count and convergence trends
   - Recommendation (continue/escalate/await-human)
3. Flag issues requiring attention

### `/dispute-artifact synthesize <dispute_id>`
Run synthesis pass on an open dispute.

**Actions:**
1. Load current dispute state
2. Analyze topic convergence across all passes
3. Update synthesis summary section
4. Generate recommendation with basis
5. Flag any `#widening` or stalled high-stakes topics

---

## MCP Tools Available

This skill uses the following MCP tools from `dispute-artifact-server`:

| Tool | Description |
|------|-------------|
| `db_to_csv` | Export database tables to CSV files |
| `csv_analyze` | Analyze CSV data for dispute patterns |
| `dispute_parse` | Parse raw data into Dispute Artifact format |
| `convergence_check` | Check topic convergence across passes |
| `stakes_evaluate` | Evaluate stakes and reversibility |
| `synthesis_generate` | Generate synthesis summary |

---

## Database Schema Detection

The tool auto-detects dispute-related tables by looking for:
- Tables containing: `dispute`, `conflict`, `disagreement`, `position`, `topic`
- Columns containing: `actor`, `stance`, `pass`, `convergence`, `stakes`
- Foreign key relationships indicating topic → position → actor patterns

---

## Output Format

### CSV Export Structure
```
dispute_exports/
├── manifest.json
├── disputes.csv
├── topics.csv
├── positions.csv
├── passes.csv
├── actors.csv
└── synthesis.csv
```

### Analysis Report Structure
```markdown
## Dispute Analysis Report
- **dispute_id**: DISP-20240115-0001
- **status**: open | under-synthesis | awaiting-arbitration | closed
- **total_passes**: 3
- **overall_trajectory**: narrowing | stalled | widening

### Topic Summary
| Topic | Stakes | Trajectory | Action Required |
|-------|--------|------------|-----------------|
| T1    | hard   | #widening  | ESCALATE        |
| T2    | easy   | #narrowing | Continue        |

### Escalation Flags
- T1: High stakes + widening → Requires human arbitration
- T3: Unchanged for 2+ passes → Review needed

### Recommendation
`escalate` — Material topics with high stakes showing no convergence.
```

---

## Context Window Management

To fit analysis within context limits:

1. **Summarize large datasets**:
   - Max 50 topics per analysis
   - Truncate position summaries to 300 chars
   - Group similar topics

2. **Prioritize by materiality**:
   - Show `material_topic: yes` first
   - Sort by stakes (hard → moderate → easy)
   - Highlight escalation candidates

3. **Progressive disclosure**:
   - Summary view first
   - Detailed view on request
   - Full data export to files

---

## Example Usage

```bash
# Export SQLite dispute database to CSV
/dispute-artifact export sqlite:./data/disputes.db

# Analyze exported data
/dispute-artifact analyze --file ./dispute_exports/disputes.csv

# Create new dispute from CSV data
/dispute-artifact create --from ./raw_data/conflict_report.csv

# Check status of specific dispute
/dispute-artifact status --dispute-id DISP-20240115-0001

# Run synthesis on open dispute
/dispute-artifact synthesize DISP-20240115-0001
```

---

## Convergence Analysis Rules

When analyzing convergence:

1. **Flag for escalation if**:
   - Any topic is `#widening`
   - Any topic is `#unchanged` + NOT `#easily-reversible` for 2+ passes
   - `#new-topic` not `#narrowing` on second pass + NOT `#easily-reversible`

2. **Permit continuation if** all material topics are:
   - `#narrowing`, OR
   - `#easily-reversible`, OR
   - `#new-topic` on first pass

3. **Require human if**:
   - `overall_stakes` is elevated
   - Arbitration previously failed
   - 4+ passes without resolution

---

## Integration with Adversarial Review Pipeline

This skill integrates with the main pipeline:
- Proposer generates initial positions
- Critic identifies disagreements
- Arbiter may create Dispute Artifact for unresolved conflicts
- Dispute passes through collaboration until resolution or escalation
