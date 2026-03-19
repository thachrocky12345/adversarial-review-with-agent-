"""
main.py
───────
Adversarial Review Pipeline Demo

Demonstrates the full Proposer -> Critic -> Arbiter loop with:
  - Token budget management
  - Multi-provider LLM support
  - Guardrails enforcement

Run with: python main.py
"""

import logging
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from orchestrator import AdversarialReviewOrchestrator
from llm_providers import check_api_keys
from config import ACTIVE_CONFIG

# ─── Logging Setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Demo Task ───────────────────────────────────────────────────────────────

DEMO_TASK = """
Write a product description for an AI-powered calendar assistant.
The description should be suitable for a B2B SaaS landing page.
Target audience: operations managers at mid-sized companies.
Length: 150-200 words.
"""

DEMO_CRITERIA = [
    "Must clearly state the product's primary benefit in the first sentence.",
    "Must address at least two specific pain points of operations managers.",
    "Must include a concrete, quantifiable claim (e.g., saves X hours/week).",
    "Must NOT use vague buzzwords like 'revolutionary' or 'game-changing'.",
    "Must end with a clear call-to-action.",
    "Word count must be between 150 and 200 words.",
]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ADVERSARIAL REVIEW PIPELINE DEMO")
    print("=" * 60)

    # Check API keys
    api_keys = check_api_keys()
    print("\nAPI Key Status:")
    for provider, configured in api_keys.items():
        status = "configured" if configured else "NOT SET"
        print(f"  {provider}: {status}")

    # Show active configuration
    print("\nAgent Configuration:")
    for agent_id, config in ACTIVE_CONFIG.items():
        print(f"  {agent_id}: {config['provider']}/{config['model']}")

    # Verify at least one required provider is configured
    required_providers = set(c["provider"] for c in ACTIVE_CONFIG.values())
    missing = [p for p in required_providers if not api_keys.get(p)]
    if missing:
        print(f"\nERROR: Missing API keys for: {', '.join(missing)}")
        print("\nSet the required environment variables:")
        if "anthropic" in missing:
            print("  set ANTHROPIC_API_KEY=your-key-here")
        if "openai" in missing:
            print("  set OPENAI_API_KEY=your-key-here")
        if "gemini" in missing:
            print("  set GOOGLE_API_KEY=your-key-here")
        sys.exit(1)

    print("\n" + "-" * 60)
    print("TASK:")
    print(DEMO_TASK.strip())
    print("\nCRITERIA:")
    for i, criterion in enumerate(DEMO_CRITERIA, 1):
        print(f"  {i}. {criterion}")
    print("-" * 60 + "\n")

    # Run the pipeline
    orchestrator = AdversarialReviewOrchestrator()

    result = orchestrator.run(
        task_id="demo_001",
        task_spec=DEMO_TASK,
        criteria=DEMO_CRITERIA,
        complexity="normal",
    )

    # Print results
    print("\n" + "=" * 60)
    print(f"FINAL VERDICT  : {result['verdict'].upper()}")
    print(f"REVISION ROUNDS: {result.get('revision_rounds', 'N/A')}")
    print(f"TOTAL TOKENS   : {result.get('total_tokens', 0):,}")
    print("=" * 60)

    if result["verdict"] in ("approved", "approved_minor"):
        print(f"\nRATIONALE: {result.get('arbiter_rationale', 'N/A')}")
        draft = result.get("final_draft", {})
        if isinstance(draft, dict):
            draft_text = draft.get("draft") or draft.get("content") or draft.get("raw_text", "")
        else:
            draft_text = str(draft)
        print(f"\nFINAL DRAFT:\n{draft_text}")

    elif result["verdict"] == "escalate":
        print(f"\nESCALATION REASON: {result.get('reason', 'N/A')}")

    else:
        print(f"\nOUTCOME: {result.get('reason', 'See review_history for details')}")

    print("\nREVIEW HISTORY:")
    for entry in result.get("review_history", []):
        attempt = f" (attempt {entry['attempt']})" if "attempt" in entry else ""
        print(f"  Round {entry['round']} | {entry['role'].upper()}{attempt}")
        print(f"    {entry.get('summary', '')}")
        if "verdict" in entry:
            print(f"    -> verdict: {entry['verdict']}")


if __name__ == "__main__":
    main()
