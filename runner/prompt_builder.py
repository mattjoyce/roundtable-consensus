"""Build mono context for agent CLIs from signal payloads.

Produces a self-contained context blob that includes:
- Session state (phase, tick, balance, proposals, feedback, stakes)
- OCEAN personality profile
- Engine API reference (endpoints, action format, auth)
- Curl examples for each action type
- Phase-specific instructions
"""

import json
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "simulator" / "prompts"


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Load a prompt template from the simulator's prompts directory."""
    try:
        return (_PROMPTS_DIR / name).read_text()
    except FileNotFoundError:
        return ""


def build_system_prompt(signal: dict) -> str:
    """Build the system prompt from agent_system.md + OCEAN profile."""
    base = load_prompt("agent_system.md")
    profile = signal.get("ocean_profile", {})
    if profile:
        traits = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        base += f"\n\nYour personality traits:\n{traits}"
    return base


def build_mono_context(signal: dict, engine_url: str, auth_token: str) -> str:
    """Build the complete mono context blob for an agent CLI.

    This is everything the agent needs to understand the situation and
    submit its action back to the engine via curl.
    """
    parts = []

    # --- Session State ---
    parts.append("# Session State\n")
    parts.append(f"- Session ID: {signal.get('session_id', 'unknown')}")
    parts.append(f"- Issue: {signal.get('issue_id', 'unknown')}")
    parts.append(f"- Phase: **{signal.get('type', 'unknown')}**")
    parts.append(f"- Tick: {signal.get('tick', 0)} (phase tick: {signal.get('phase_tick', 0)})")
    parts.append(f"- Your agent ID: {signal.get('agent_id', 'unknown')}")
    parts.append(f"- Your CP balance: {signal.get('agent_balance', 0)}")
    parts.append(f"- Your proposal ID: {signal.get('agent_proposal_id', 'none')}")

    # Protocol config
    protocol = signal.get("protocol", {})
    if protocol:
        parts.append("\n## Protocol Config")
        parts.append(f"- Proposal self-stake: {protocol.get('proposal_self_stake', '?')} CP")
        parts.append(f"- Feedback stake: {protocol.get('feedback_stake', '?')} CP")
        parts.append(f"- Max feedback per agent: {protocol.get('max_feedback_per_agent', '?')}")

    # Proposals
    proposals = signal.get("proposals", [])
    if proposals:
        parts.append("\n## Active Proposals")
        for p in proposals:
            parts.append(
                f"- **Proposal #{p['proposal_id']}** by {p['author']} "
                f"(type={p['type']}, rev={p['revision_number']}):\n"
                f"  {p['content'][:500]}"
            )

    # Feedback (revise phase)
    feedback = signal.get("feedback_for_proposal", [])
    if feedback:
        parts.append("\n## Feedback on Your Proposal")
        for fb in feedback:
            parts.append(f"- From {fb.get('from', '?')}: {fb.get('comment', '')}")

    # Own stakes (stake phase)
    stakes = signal.get("own_stakes", [])
    if stakes:
        parts.append("\n## Your Current Stakes")
        for s in stakes:
            parts.append(f"- {s['cp']} CP on proposal #{s['proposal_id']}")

    # Memory
    memory = signal.get("agent_memory", {})
    if memory:
        parts.append(f"\n## Your Memory\n{json.dumps(memory, default=str)[:500]}")

    # --- Phase Instructions ---
    phase_type = signal.get("type", "").lower()
    phase_prompt = _build_phase_instructions(phase_type)
    if phase_prompt:
        parts.append(f"\n# Phase Instructions\n\n{phase_prompt}")

    # --- API Reference ---
    agent_id = signal.get("agent_id", "unknown")
    session_id = signal.get("session_id", "unknown")
    action_url = f"{engine_url}/v1/sessions/{session_id}/agents/{agent_id}/action"

    parts.append("\n# How to Submit Your Action")
    parts.append("\nYou MUST submit your action by running a curl command.")
    parts.append("This is the ONLY way to participate — your text output alone does nothing.")
    parts.append(f"\n## Endpoint\n\n`POST {action_url}`")
    parts.append(f"\n## Authentication\n\n`Authorization: Bearer {auth_token}`")

    parts.append("\n## Action Format")
    parts.append(f"""
```json
{{
  "type": "<action_type>",
  "payload": {{ ... }}
}}
```

Valid action types for each phase:
- **PROPOSE**: `propose`, `signal_ready`, `wait`
- **FEEDBACK**: `feedback`, `signal_ready`, `wait`
- **REVISE**: `revise`, `signal_ready`, `wait`
- **STAKE**: `stake`, `switch_stake`, `unstake`, `signal_ready`, `wait`
- **FINALIZE**: `signal_ready`, `wait`
""")

    # Phase-specific curl examples
    parts.append(_build_curl_examples(phase_type, action_url, auth_token))

    parts.append("\n## Important")
    parts.append("- You MUST run the curl command — do not just output text")
    parts.append("- Submit exactly ONE action per signal")
    parts.append("- If unsure, submit `signal_ready` to advance the phase")

    return "\n".join(parts)


def _build_phase_instructions(phase_type: str) -> str:
    """Load phase-specific instructions from templates or generate inline."""
    prompt_map = {
        "propose": "propose_decision.md",
        "feedback": "feedback_decision.md",
        "revise": "revise_decision.md",
    }
    template_name = prompt_map.get(phase_type)
    if template_name:
        return load_prompt(template_name)

    if phase_type == "stake":
        return (
            "Decide how to allocate your CP across proposals.\n"
            "You can: stake (place CP on a proposal), switch_stake "
            "(move stake to another proposal), unstake (remove stake), "
            "signal_ready, or wait."
        )
    return "This phase requires no specific action. Submit signal_ready to proceed."


def _build_curl_examples(phase_type: str, action_url: str, auth_token: str) -> str:
    """Build curl examples for the current phase."""
    header = f'-H "Authorization: Bearer {auth_token}" -H "Content-Type: application/json"'
    base = f'curl -s -X POST {action_url} {header}'

    examples = ["\n## Curl Examples\n"]

    if phase_type == "propose":
        examples.append(f"**Submit a proposal:**")
        examples.append(f'```bash\n{base} -d \'{{"type": "propose", "payload": {{"content": "Your proposal text here"}}}}\'\n```')

    elif phase_type == "feedback":
        examples.append(f"**Submit feedback on a proposal:**")
        examples.append(f'```bash\n{base} -d \'{{"type": "feedback", "payload": {{"proposal_id": 1, "comment": "Your feedback here"}}}}\'\n```')

    elif phase_type == "revise":
        examples.append(f"**Submit a revision:**")
        examples.append(f'```bash\n{base} -d \'{{"type": "revise", "payload": {{"content": "Your revised proposal text"}}}}\'\n```')

    elif phase_type == "stake":
        examples.append(f"**Stake CP on a proposal:**")
        examples.append(f'```bash\n{base} -d \'{{"type": "stake", "payload": {{"proposal_id": 1, "amount": 20}}}}\'\n```')
        examples.append(f"\n**Switch stake:**")
        examples.append(f'```bash\n{base} -d \'{{"type": "switch_stake", "payload": {{"proposal_id": 2, "from_proposal_id": 1}}}}\'\n```')

    # Always include signal_ready
    examples.append(f"\n**Signal ready (skip/wait):**")
    examples.append(f'```bash\n{base} -d \'{{"type": "signal_ready", "payload": {{}}}}\'\n```')

    return "\n".join(examples)
