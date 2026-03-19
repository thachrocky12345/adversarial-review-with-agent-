# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the demo pipeline
python main.py

# Syntax check all modules
python -m py_compile core_types.py llm_providers.py config.py budget_manager.py guardrails.py orchestrator.py main.py
```

## Environment Setup

Set API keys for the LLM providers you plan to use (default config only requires Anthropic):

```bash
# Required for default config
set ANTHROPIC_API_KEY=your-key    # Windows
export ANTHROPIC_API_KEY=your-key # Linux/Mac

# Optional: for multi-provider configs
set OPENAI_API_KEY=your-key
set GOOGLE_API_KEY=your-key
```

## Architecture

This is a **token-aware multi-agent review pipeline** with three roles in a loop:

```
Proposer → Critic → Arbiter → Decision
                                  │
              ┌───────────────────┼───────────────────┐
              ↓                   ↓                   ↓
          APPROVED            REVISE              REJECT
          (return)       (loop w/feedback)    (restart draft)
```

### Core Data Flow

1. **Orchestrator** (`orchestrator.py:AdversarialReviewOrchestrator.run()`) coordinates the loop
2. **AgentRunner** calls LLM with budget + guardrails injected into system prompt
3. Each agent returns `AgentResult` with explicit `CompletionStatus` and optional `ReviewVerdict`
4. **Guardrails** validate output before routing downstream

### Token Protection (3 Layers)

| Layer | Location | Mechanism |
|-------|----------|-----------|
| Budget Contract | `TokenBudgetManager.assign()` | Sets limits BEFORE agent runs |
| Prompt Injection | `TokenBudget.to_prompt_block()` | Agent sees limits in system prompt |
| Orchestrator Gate | `AgentResult.is_usable` | Status checked after every call |

### Multi-Provider LLM Support

Each agent can use a different provider via `config.py`:
- **Anthropic**: Best reasoning (default for all agents)
- **OpenAI**: Better structured JSON output
- **Gemini**: Long context, cost efficiency

Provider abstraction in `llm_providers.py` - all implement `BaseLLMProvider.complete()`.

### Key Type Contracts

All agents communicate via types in `core_types.py`:

- `CompletionStatus`: `COMPLETE | PARTIAL_SAFE | PARTIAL_UNSAFE | BUDGET_EXCEEDED | FAILED`
- `ReviewVerdict`: `APPROVED | APPROVED_MINOR | REVISE | REJECT | ESCALATE`
- `AgentResult`: Universal return envelope with `status`, `verdict`, `data`, `checkpoint`
- `TokenBudget`: Budget contract with `to_prompt_block()` for injection

### Guardrails System

Two layers in `guardrails.py`:

1. **ProjectIntegrityGuardrails**: Task ID integrity, completeness honesty, unsafe partial blocking
2. **PersonaGuardrails**: Role enforcement via `ROLE_PERMISSIONS` dict - prevents role bleed (e.g., Critic rewriting)

### Pipeline Constants

In `orchestrator.py`:
- `MAX_REVISION_ROUNDS = 3` - Proposer revision attempts
- `MAX_CRITIC_RETRIES = 2` - Critic retries per round
- `TURN_SUMMARY_EVERY = 4` - Context compression frequency

Budget profiles in `budget_manager.py`:
- `simple`: 2K input, 1K output, 2 turns
- `normal`: 4K input, 2K output, 3 turns
- `complex`: 8K input, 4K output, 5 turns
- 15% safety margin, 40% expansion on retry

## Conventions

- Type hints required on all function signatures
- Google-style docstrings
- File named `core_types.py` (not `types.py`) to avoid shadowing Python's built-in
