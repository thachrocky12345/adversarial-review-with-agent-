# Architecture Overview

**Last Updated:** 2026-03-18

## Overview

The Adversarial Review Pipeline is a token-aware multi-agent system that implements a Proposer → Critic → Arbiter review loop. Each agent can use a different LLM provider (Anthropic, OpenAI, or Google Gemini) optimized for its specific role, with guardrails ensuring output quality and role compliance.

## Tech Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| Language | Python 3.10+ | Core implementation |
| LLM - Primary | Anthropic Claude | Reasoning, nuanced decisions |
| LLM - Structured | OpenAI GPT-4o | JSON output, function calling |
| LLM - Long Context | Google Gemini | Large documents, cost efficiency |

## System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│                    (Demo Entry Point)                       │
├─────────────────────────────────────────────────────────────┤
│                    orchestrator.py                          │
│         AdversarialReviewOrchestrator + AgentRunner         │
│              RollingContextBuffer (compression)             │
├──────────────────┬──────────────────┬───────────────────────┤
│   guardrails.py  │ budget_manager.py│   llm_providers.py    │
│   - Project      │ - TokenBudget    │   - Anthropic         │
│   - Persona      │ - Usage Tracking │   - OpenAI            │
│                  │ - Retry Logic    │   - Gemini            │
├──────────────────┴──────────────────┴───────────────────────┤
│                     core_types.py                           │
│   CompletionStatus, ReviewVerdict, TokenBudget, AgentResult │
├─────────────────────────────────────────────────────────────┤
│                       config.py                             │
│              Per-Agent Model Configuration                  │
└─────────────────────────────────────────────────────────────┘
```

## Key Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `core_types.py` | Shared type definitions | `CompletionStatus`, `ReviewVerdict`, `TokenBudget`, `AgentResult` |
| `llm_providers.py` | Multi-provider LLM abstraction | `BaseLLMProvider`, `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` |
| `config.py` | Per-agent model configuration | `AGENT_MODEL_CONFIG`, `get_agent_config()` |
| `budget_manager.py` | Token budget management | `TokenBudgetManager`, `BUDGET_PROFILES` |
| `guardrails.py` | Output validation | `ProjectIntegrityGuardrails`, `PersonaGuardrails` |
| `orchestrator.py` | Pipeline coordination | `AdversarialReviewOrchestrator`, `AgentRunner`, `RollingContextBuffer` |
| `main.py` | Demo entry point | `main()` |

## Data Flow

```
1. Task Input
      │
      ▼
2. Proposer (generates draft)
   └── Budget assigned → LLM call → Guardrails check
      │
      ▼
3. Critic (reviews draft)
   └── Budget assigned → LLM call → Guardrails check
      │
      ▼
4. Arbiter (renders verdict)
   └── Budget assigned → LLM call → Guardrails check
      │
      ▼
5. Decision
   ├── APPROVED → Return final draft
   ├── REVISE → Loop to Proposer with feedback
   ├── REJECT → Restart with new draft
   └── ESCALATE → Return for human review
```

## Token Protection Layers

1. **Budget Contract** (`TokenBudgetManager`): Assigns limits before each agent runs
2. **Prompt Injection** (`TokenBudget.to_prompt_block()`): Agent sees limits in system prompt
3. **Orchestrator Gate** (`AgentResult.status`): Status checked after every call

## Recent Decisions

| ADR | Title | Status |
|-----|-------|--------|
| - | No ADRs yet | - |

## Open Questions

1. Should context compression use a dedicated summarizer model?
2. How to handle multi-modal content in future versions?
3. Optimal budget profiles for different content types?
