# Learning Prompt: Multi-Agent Review Pipeline Patterns

Use this prompt with Claude Code after cloning this repository. Copy and paste it to help Claude learn these patterns and apply them to your own agent application.

---

## Prompt to Use

```
I've cloned an adversarial review pipeline repository that demonstrates best practices for multi-agent systems. Please study the following files to learn the patterns, then help me apply them to improve my own agent application.

## Files to Study

Read these files in order to understand the architecture:

1. **core_types.py** - Universal types all agents speak
2. **guardrails.py** - Role enforcement and integrity checks
3. **budget_manager.py** - Token budget management
4. **orchestrator.py** - Pipeline coordination
5. **PROPOSER_AGENT.md**, **CRITIC_AGENT.md**, **ARBITER_AGENT.md** - Role definitions

## Key Patterns to Extract

### 1. Explicit Completion Status
Every agent returns a status envelope that the orchestrator can trust:
- `COMPLETE` - All work done, fully reliable
- `PARTIAL_SAFE` - Incomplete but usable (stopped at clean boundary)
- `PARTIAL_UNSAFE` - Mid-unit stop, DO NOT USE downstream
- `BUDGET_EXCEEDED` - Hard limit hit, checkpoint saved
- `FAILED` - Unrecoverable error

**Apply to my project:** Create an enum/type for completion status. Never let agents return ambiguous results.

### 2. Token Budget Contract (3 Layers)
Protection happens BEFORE, DURING, and AFTER each agent run:
- **Layer 1 (Before):** `TokenBudgetManager.assign()` sets limits
- **Layer 2 (During):** Budget injected into system prompt via `to_prompt_block()`
- **Layer 3 (After):** `AgentResult.is_usable` gate blocks unsafe outputs

**Apply to my project:** Add budget awareness to agent prompts. Track usage. Gate outputs.

### 3. Role-Based Guardrails
Each role has explicit permissions that prevent "role bleed":
```python
ROLE_PERMISSIONS = {
    "proposer": {
        "may_produce": ["draft", "proposal"],
        "may_not": ["verdict", "approval", "critique"],
        "constraint": "Must not evaluate its own output"
    },
    "critic": {
        "may_produce": ["critique", "issues_list"],
        "may_not": ["draft", "rewrite", "final_decision"],
        "constraint": "Must cite specific lines/sections"
    }
}
```

**Apply to my project:** Define what each agent role CAN and CANNOT do. Enforce at runtime.

### 4. Adversarial Review Loop
The Proposer → Critic → Arbiter pattern creates accountability:
- Proposer generates, but cannot approve itself
- Critic finds problems, but cannot rewrite
- Arbiter decides, but cannot introduce new critique

**Apply to my project:** Separate generation from evaluation. No agent should mark its own homework.

### 5. Checkpoint + Resume on Partial
When an agent exceeds budget:
- Save checkpoint state: `{"last_completed_section": N, "remaining": [...]}`
- Return `PARTIAL_SAFE` or `BUDGET_EXCEEDED`
- Orchestrator can retry with expanded budget (40% increase)

**Apply to my project:** Design for graceful degradation. Partial results > crashed runs.

### 6. Structured Output Format
Every agent returns the same envelope:
```python
@dataclass
class AgentResult:
    agent_id: str
    task_id: str
    status: CompletionStatus
    data: Any
    verdict: Optional[ReviewVerdict]
    items_processed: int
    items_total: int
    tokens_used: int
    checkpoint: Optional[dict]
```

**Apply to my project:** Create a universal result type all agents return.

## Now Help Me Apply These Patterns

My agent application is located at: [YOUR_PROJECT_PATH]

Please:
1. Read my current agent code
2. Identify which patterns are missing
3. Suggest specific changes to add:
   - Explicit completion status types
   - Token budget management
   - Role-based guardrails
   - Structured result envelopes
   - Checkpoint/resume capability

Start by reading my main agent files and give me a gap analysis.
```

---

## Quick Reference Card

### Completion Status Values
| Status | Meaning | Orchestrator Action |
|--------|---------|---------------------|
| `COMPLETE` | All done | Forward downstream |
| `PARTIAL_SAFE` | Clean stop | Forward + note incompleteness |
| `PARTIAL_UNSAFE` | Mid-unit stop | RETRY, do not forward |
| `BUDGET_EXCEEDED` | Hit limit | Expand budget, retry with checkpoint |
| `FAILED` | Error | Escalate or abort |

### Review Verdict Values
| Verdict | Meaning | Next Step |
|---------|---------|-----------|
| `APPROVED` | Passes all criteria | Output to user |
| `APPROVED_MINOR` | Passes with notes | Output with caveats |
| `REVISE` | Fixable issues | Return to Proposer |
| `REJECT` | Fundamental failure | Restart from scratch |
| `ESCALATE` | Ambiguous | Human decision needed |

### Budget Profiles
| Complexity | Input | Output | Turns |
|------------|-------|--------|-------|
| `simple` | 2K | 1K | 2 |
| `normal` | 4K | 2K | 3 |
| `complex` | 8K | 4K | 5 |

- 15% safety margin applied automatically
- 40% budget expansion on retry

### Guardrail Check Sequence
```
1. ProjectIntegrityGuardrails.check()
   ├── task_id matches?
   ├── coverage matches claimed status?
   ├── PARTIAL_UNSAFE blocked?
   └── checkpoint present if budget exceeded?

2. PersonaGuardrails.check()
   ├── output_type in may_produce?
   └── no forbidden keys in data?
```

---

## Folder Structure to Replicate

```
your-project/
├── core_types.py      # CompletionStatus, ReviewVerdict, AgentResult, TokenBudget
├── guardrails.py      # ProjectIntegrityGuardrails, PersonaGuardrails, ROLE_PERMISSIONS
├── budget_manager.py  # TokenBudgetManager, BUDGET_PROFILES
├── orchestrator.py    # Main loop: assign budget → run agent → check guardrails → route
├── llm_providers.py   # Provider abstraction (Anthropic, OpenAI, Gemini)
├── config.py          # Which provider/model per agent role
├── PROPOSER_AGENT.md  # Role definition for Proposer
├── CRITIC_AGENT.md    # Role definition for Critic
├── ARBITER_AGENT.md   # Role definition for Arbiter
└── main.py            # Demo entry point
```

---

## Example: Adding to Your Project

If your current agent just returns a string:

```python
# BEFORE (unsafe)
def my_agent(prompt: str) -> str:
    return llm.complete(prompt)

# AFTER (with patterns applied)
def my_agent(prompt: str, budget: TokenBudget) -> AgentResult:
    # Inject budget into system prompt
    system = f"{base_system}\n\n{budget.to_prompt_block()}"

    response = llm.complete(system, prompt)

    return AgentResult(
        agent_id="my_agent",
        task_id=current_task_id,
        status=CompletionStatus.COMPLETE,  # Or PARTIAL_SAFE if incomplete
        data=response,
        tokens_used=response.usage.total_tokens,
    )
```

Then in your orchestrator:

```python
budget = budget_manager.assign("my_agent", complexity="normal")
result = my_agent(prompt, budget)

# Gate the output
if not result.is_usable:
    # Retry with expanded budget
    budget = budget_manager.assign("my_agent", retry_of=result.checkpoint)
    result = my_agent(prompt, budget)

# Check guardrails
guardrail_result = integrity_guardrails.check(result, expected_task_id)
if not guardrail_result.passed:
    handle_guardrail_failure(guardrail_result)
```

---

## Dispute Artifact System

When multi-agent disagreements cannot be resolved in a single pass, use the **Dispute Artifact** system to track, analyze, and resolve conflicts systematically.

### 7. Structured Dispute Resolution

The Dispute Artifact provides a durable, comparable, and reviewable record:

```
Proposer → Critic → Arbiter → REVISE/REJECT
                                    │
                         ┌──────────┴──────────┐
                         ↓                     ↓
                   Create Dispute        Resolve & Close
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
         Collaboration          Escalation
         (autonomous)           (human review)
```

**Apply to my project:** When agents disagree, create a formal dispute record rather than losing context.

### 8. Convergence Tracking

Track how disagreements evolve across collaboration passes:

| Tag | Meaning | Action |
|-----|---------|--------|
| `#new-topic` | First pass, no trajectory yet | Allow 1 autonomous pass |
| `#narrowing` | Getting closer to resolution | Continue collaboration |
| `#unchanged` | No progress this pass | Monitor (escalate if high stakes) |
| `#widening` | Disagreement expanding | **Escalate immediately** |

**Escalation Rules:**
- `#widening` on any topic → escalate
- `#unchanged` + NOT `#easily-reversible` for 2+ passes → escalate
- `#new-topic` not `#narrowing` on second pass + high stakes → escalate
- 4+ passes without resolution → await human

**Apply to my project:** Track convergence per topic. Escalate stalled high-stakes disagreements.

### 9. Stakes-Aware Decision Making

Not all disagreements are equal. Tag by reversibility:

| Stakes | Meaning | Autonomy Level |
|--------|---------|----------------|
| `#easily-reversible` | Low cost to change later | Full autonomous resolution |
| `#moderate-to-reverse` | Meaningful rework needed | Monitor, escalate if stalled |
| `#hard-to-reverse` | Major migration/policy change | Escalate early |

**Apply to my project:** Classify decisions by reversibility. Invest review effort proportionally.

### 10. Database Export & Analysis Tools

Extract dispute data from databases for analysis within context windows:

```python
from tools.dispute_artifact import DatabaseExporter, DisputeAnalyzer

# Export database tables to CSV
manifest = DatabaseExporter.export("sqlite:./data.db", "./exports/")

# Analyze with context-aware limits
analyzer = DisputeAnalyzer(max_topics=50)
analysis = analyzer.analyze_from_csv("./exports/")
print(analysis.generate_report())  # Fits in context window
```

**Apply to my project:** Export large datasets to CSV, then analyze summaries within context limits.

---

## Dispute Artifact Key Features

### 1. Database Export
Auto-detects dispute-related tables by scanning for patterns:
- Table names: `dispute`, `conflict`, `position`, `topic`, `actor`
- Column names: `dispute_id`, `stance`, `convergence`, `stakes`, `verdict`

### 2. Convergence Analysis
Identifies escalation candidates automatically:
- Topics trending `#widening`
- Topics stuck `#unchanged` with high stakes
- Stalled disputes (no progress across 2+ passes)

### 3. Context-Aware Reports
Fits analysis within context window limits:
- Max 50 topics per analysis (configurable)
- Position summaries truncated to 300 chars
- Prioritized by materiality and stakes

### 4. Synthesis Generation
Automatic recommendations with basis:
- `continue-collaboration` — all topics narrowing or low stakes
- `escalate` — material topics with escalation triggers
- `await-human` — 4+ passes or elevated overall stakes

---

## Dispute Artifact Structure

```markdown
## Dispute metadata
- **dispute_id**: DISP-20240115-0001
- **lifecycle_status**: open | under-synthesis | awaiting-arbitration | closed

## Actor registry
- **A**: {role: "Proposer", stance: "..."}
- **B**: {role: "Critic", stance: "..."}

## Topic Convergence Tracker
| topic_id | stakes | pass_1 | pass_2 | pass_3 |
|----------|--------|--------|--------|--------|
| T1 | #hard-to-reverse | #new-topic | #narrowing | #narrowing |
| T2 | #easily-reversible | #new-topic | #unchanged | #unchanged |

## Synthesis summary
- **recommendation**: continue-collaboration
- **recommendation_basis**: All material topics narrowing or easily reversible
```

---

## MCP Tools Available

The dispute-artifact skill exposes these MCP tools:

| Tool | Description |
|------|-------------|
| `db_to_csv` | Export database tables to CSV files |
| `csv_analyze` | Analyze CSV data for dispute patterns |
| `dispute_create` | Create new dispute artifact from conflicts |
| `dispute_parse` | Parse raw data into artifact format |
| `convergence_check` | Check topic convergence patterns |
| `synthesis_generate` | Generate synthesis with recommendation |

### CLI Usage

```bash
# Export database
python -m tools.dispute_artifact.cli export sqlite:./data.db

# Analyze exported data
python -m tools.dispute_artifact.cli analyze ./dispute_exports/

# Create dispute from JSON
python -m tools.dispute_artifact.cli create --from ./conflicts.json

# Check status
python -m tools.dispute_artifact.cli status DISP-20240115-0001

# Run synthesis
python -m tools.dispute_artifact.cli synthesize DISP-20240115-0001
```

### Skill Invocation

```
/dispute-artifact export sqlite:./data.db
/dispute-artifact analyze --file ./dispute_exports/
/dispute-artifact status --dispute-id DISP-20240115-0001
/dispute-artifact synthesize DISP-20240115-0001
```

---

## Updated Folder Structure

```
your-project/
├── core_types.py
├── guardrails.py
├── budget_manager.py
├── orchestrator.py
├── llm_providers.py
├── config.py
├── PROPOSER_AGENT.md
├── CRITIC_AGENT.md
├── ARBITER_AGENT.md
├── main.py
│
├── tools/
│   └── dispute_artifact/
│       ├── __init__.py
│       ├── db_exporter.py      # SQLite/Postgres/MySQL/JSON → CSV
│       ├── csv_analyzer.py     # Analyze disputes, generate reports
│       ├── artifact_parser.py  # Parse data into Dispute Artifact
│       ├── convergence.py      # Convergence checking, synthesis
│       ├── mcp_server.py       # MCP tool server
│       └── cli.py              # Command-line interface
│
└── .claude/
    └── skills/
        └── dispute-artifact/
            └── SKILL.md        # Skill definition
```
