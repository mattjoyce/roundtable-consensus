"""LLM integration and structured response handling for consensus simulation.

Uses Simon Willison's llm package (https://llm.datasette.io/) as the backend,
providing access to any registered model (OpenAI, Anthropic, Ollama, etc.)
through a unified interface.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Literal, Tuple, Type, TypeVar

import llm as llm_lib
from pydantic import BaseModel

# Cache for loaded prompts to avoid repeated file I/O
_prompt_cache: Dict[str, str] = {}

# Default model - matches the previously hardcoded Ollama model
DEFAULT_MODEL = "gemma3n:e4b"


# Pydantic models for structured LLM responses
class ProposeDecision(BaseModel):
    """Structured response model for agent propose decisions."""

    action: Literal["propose", "signal_ready", "wait"]
    reasoning: str


class FeedbackDecision(BaseModel):
    """Structured response model for agent feedback decisions."""

    action: Literal["provide_feedback", "wait"]
    target_proposals: list[
        int
    ]  # List of proposal IDs to give feedback to (empty if waiting)
    reasoning: str


class ReviseDecision(BaseModel):
    """Structured response model for agent revise decisions."""

    action: Literal["revise", "signal_ready"]
    reasoning: str


class PreferenceItem(BaseModel):
    """Individual preference item for a proposal."""

    proposal_id: int
    preference_score: float  # 0.0 to 1.0
    rank: int  # 1=most preferred
    reasoning: str


class PreferenceRanking(BaseModel):
    """Structured response model for stake phase proposal preference ranking."""

    preferences: list[PreferenceItem]  # List of preference items
    self_proposal_id: int | None = None  # Agent's own proposal ID
    strategy_summary: str  # Overall strategic approach for this phase


class StakeAction(BaseModel):
    """Structured response model for stake phase tactical actions."""

    action: Literal["stake", "switch_stake", "unstake", "wait"]
    proposal_id: int  # Target proposal for action
    cp_amount: int  # Amount to stake/switch/unstake
    source_proposal_id: int | None = None  # For switch actions only
    reasoning: str  # Tactical reasoning for this specific action


T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=16)
def _get_model(model: str | None = None) -> llm_lib.Model:
    """Get a cached llm model instance by name."""
    return llm_lib.get_model(model or DEFAULT_MODEL)


def _prepare(
    system: str,
    context: str,
    prompt: str,
    model: str | None,
    seed: int | None,
    context_window: int | None,
) -> Tuple[llm_lib.Model, str, dict]:
    """Shared setup for one_shot and one_shot_json.

    Returns:
        (model_instance, user_content, options_kwargs)
    """
    m = _get_model(model)

    # Build provider-specific options (only what the model supports)
    options = {}
    supported = set()
    if hasattr(m, "Options") and hasattr(m.Options, "model_fields"):
        supported = set(m.Options.model_fields.keys())
    if seed is not None and "seed" in supported:
        options["seed"] = seed
    if context_window is not None and "num_ctx" in supported:
        options["num_ctx"] = context_window

    user_content = f"{context}\n\n{prompt}" if context else prompt
    return m, user_content, options


def one_shot(
    system: str,
    context: str,
    prompt: str,
    model: str = None,
    seed: int = None,
    context_window: int = None,
) -> str:
    """
    Generates structured prose using an LLM model via the llm package.

    Args:
        system: System message/directive for the model
        context: Contextual information for the generation
        prompt: User prompt/request
        model: Model name as registered in llm (default: gemma3n:e4b)
        seed: Random seed for deterministic generation (optional, provider-dependent)
        context_window: Context window size (optional, Ollama-only)
    """
    m, user_content, options = _prepare(system, context, prompt, model, seed, context_window)

    try:
        response = m.prompt(
            user_content,
            system=system or None,
            stream=False,
            **options,
        )
        return response.text()
    except Exception as exc:
        print(f"Error during one_shot: {exc}")
        return ""


def one_shot_json(
    system: str,
    context: str,
    prompt: str,
    response_model: Type[T],
    model: str = None,
    seed: int = None,
    context_window: int = None,
) -> T:
    """
    Generates structured JSON response using an LLM model with Pydantic validation.

    Args:
        system: System message/directive for the model
        context: Contextual information for the generation
        prompt: User prompt/request
        response_model: Pydantic model class for structured response
        model: Model name as registered in llm (default: gemma3n:e4b)
        seed: Random seed for deterministic generation (optional, provider-dependent)
        context_window: Context window size (optional, Ollama-only)

    Returns:
        Validated Pydantic model instance

    Raises:
        Exception: If LLM call fails or response validation fails
    """
    m, user_content, options = _prepare(system, context, prompt, model, seed, context_window)

    try:
        if m.supports_schema:
            response = m.prompt(
                user_content,
                system=system or None,
                schema=response_model,
                stream=False,
                **options,
            )
            return response_model.model_validate_json(response.text())
        else:
            # Fallback: ask for JSON in the prompt and parse manually
            json_prompt = (
                f"{user_content}\n\n"
                f"Respond with ONLY valid JSON matching this schema:\n"
                f"{json.dumps(response_model.model_json_schema(), indent=2)}"
            )
            response = m.prompt(
                json_prompt,
                system=system or None,
                stream=False,
                **options,
            )
            return response_model.model_validate_json(response.text())
    except Exception as exc:
        print(f"Error during one_shot_json: {exc}")
        raise


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt file from the prompts/ directory.

    Args:
        prompt_name: Name of the prompt file (without .md extension)

    Returns:
        The prompt content as a string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """

    # Check cache first
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]

    # Load from file
    prompt_file = Path(__file__).parent / "prompts" / f"{prompt_name}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8").strip()

    # Cache the result
    _prompt_cache[prompt_name] = content

    return content


def load_agent_system_prompt() -> str:
    """
    Load the generic agent system prompt.

    Returns:
        Generic system prompt for all agents

    Raises:
        FileNotFoundError: If agent_system.md doesn't exist
    """
    return load_prompt("agent_system")


def clear_prompt_cache():
    """Clear the prompt cache. Useful for development/testing."""
    _prompt_cache.clear()
