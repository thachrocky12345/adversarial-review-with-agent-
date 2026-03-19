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
