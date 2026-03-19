# Adversarial Review Pipeline

A token-aware multi-agent review system with multi-provider LLM support.

**Pipeline:** Proposer -> Critic -> Arbiter

Each agent can use a different LLM provider (Claude, GPT-4o, Gemini) optimized for its role.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
# Windows
set ANTHROPIC_API_KEY=your-key-here
set OPENAI_API_KEY=your-key-here        # Optional: if using OpenAI
set GOOGLE_API_KEY=your-key-here        # Optional: if using Gemini

# Linux/Mac
export ANTHROPIC_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here
export GOOGLE_API_KEY=your-key-here
```

### 3. Run Demo

```bash
python main.py
```

**Expected output:**
```
=== Revision round 1/3 ===
INFO | [proposer] complete | 6/6 items | 100% coverage | 1,234 tokens
INFO | [critic] complete | 6/6 items | 100% coverage | 987 tokens
INFO | [arbiter] complete | verdict=approved | 543 tokens

============================================================
FINAL VERDICT  : APPROVED
REVISION ROUNDS: 1
TOTAL TOKENS   : 2,764
============================================================
```

## Project Structure

```
adversarial-review-with-agent/
├── main.py              # Demo entry point
├── orchestrator.py      # Pipeline: Proposer -> Critic -> Arbiter loop
├── llm_providers.py     # Multi-provider abstraction (Anthropic, OpenAI, Gemini)
├── config.py            # Per-agent model configuration
├── budget_manager.py    # Token budget assignment & tracking
├── guardrails.py        # Project integrity + persona guardrails
├── core_types.py        # CompletionStatus, TokenBudget, AgentResult, ReviewVerdict
├── requirements.txt     # Dependencies
└── roles/
    ├── PROPOSER_AGENT.md
    ├── CRITIC_AGENT.md
    └── ARBITER_AGENT.md
```

## Multi-Provider LLM Support

Different providers excel at different tasks:

| Provider | Best For | Models |
|----------|----------|--------|
| Anthropic | Reasoning, nuanced decisions | claude-sonnet-4-20250514 |
| OpenAI | Structured JSON, function calling | gpt-4o, gpt-4o-mini |
| Gemini | Long context, cost efficiency | gemini-2.0-flash |

### Per-Agent Configuration

Edit `config.py` to assign models per agent:

```python
# Default: All agents use Claude
AGENT_MODEL_CONFIG = {
    "proposer": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "critic":   {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "arbiter":  {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
}

# Optimized: Each agent uses its best provider
OPTIMIZED_CONFIG = {
    "proposer": {"provider": "gemini", "model": "gemini-2.0-flash"},      # Long context
    "critic":   {"provider": "openai", "model": "gpt-4o"},                # Structured JSON
    "arbiter":  {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},  # Best reasoning
}
```

Switch configurations by editing `ACTIVE_CONFIG` in `config.py`.

## Token Protection Layers

### 1. Budget Contract (before agent runs)
`TokenBudgetManager.assign()` sets limits per agent based on complexity:

| Complexity | Input | Output | Turns |
|------------|-------|--------|-------|
| simple | 2,000 | 1,000 | 2 |
| normal | 4,000 | 2,000 | 3 |
| complex | 8,000 | 4,000 | 5 |

- **15% safety margin**: Agents stop before hitting hard limit
- **40% retry expansion**: Budget increases on retry

### 2. Prompt Injection (agent sees limits)
`budget.to_prompt_block()` injects limits into system prompt:
- Check budget before each unit of work
- Never start a unit you can't finish
- Return `CompletionStatus` explicitly

### 3. Orchestrator Gate (after agent returns)

| Status | Action |
|--------|--------|
| `complete` | Proceed normally |
| `partial_safe` | Use data, retry remaining |
| `partial_unsafe` | Discard, retry with expanded budget |
| `budget_exceeded` | Resume from checkpoint |
| `failed` | Retry up to limit, then abort |

## Guardrails

### Project Integrity Guardrails
- Task ID integrity (result matches assigned task)
- Completeness honesty (COMPLETE requires 100% coverage)
- Unsafe partial blocking (PARTIAL_UNSAFE never forwarded)
- Empty result detection
- Missing checkpoint on budget exceeded

### Persona Guardrails
| Agent | May Produce | May NOT Produce |
|-------|-------------|-----------------|
| Proposer | draft, proposal | verdict, critique |
| Critic | critique, issues | draft, verdict |
| Arbiter | verdict, rationale | draft, new critique |

## Pipeline Flow

```
Proposer Draft
      |
      v
  Critic Review
      |
      v
   Arbiter
      |
      +-- approved/approved_minor --> Done
      +-- revise                  --> Back to Proposer (with instructions)
      +-- reject                  --> Full restart (new draft)
      +-- escalate                --> Human decision required
```

- Max revision rounds: **3**
- Max critic retries: **2** per round

## Usage Examples

### Basic Usage

```python
from orchestrator import AdversarialReviewOrchestrator

result = AdversarialReviewOrchestrator().run(
    task_id="my_task",
    task_spec="Write a product description for...",
    criteria=[
        "Must state the primary benefit in the first sentence.",
        "Must include a quantifiable claim.",
        "Word count: 150-200.",
    ],
    complexity="normal",
)

print(result["verdict"])       # approved / revise / escalate / ...
print(result["total_tokens"])  # Total tokens spent
```

### Custom Multi-Provider Config

```python
from config import set_active_config, OPTIMIZED_CONFIG
from orchestrator import AdversarialReviewOrchestrator

# Switch to optimized multi-provider config
set_active_config(OPTIMIZED_CONFIG)

# Run with different providers per agent
result = AdversarialReviewOrchestrator().run(...)
```

### Custom Criteria

```python
result = orchestrator.run(
    task_id="blog_post",
    task_spec="Write a 500-word blog post about remote work trends.",
    criteria=[
        "Hook reader in first paragraph.",
        "Include at least 3 data points with sources.",
        "No jargon - accessible to general audience.",
        "End with actionable takeaway.",
        "Word count: 450-550.",
    ],
    complexity="complex",  # More tokens for longer content
)
```

## API Keys

| Provider | Environment Variable | Get Key |
|----------|---------------------|---------|
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| Google | `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) |

Only set keys for providers you plan to use. The default config uses Anthropic only.
