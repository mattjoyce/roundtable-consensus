"""LLM integration and structured response handling for consensus simulation."""

import json
from pathlib import Path
from typing import Dict, Literal, Type, TypeVar

import ollama
from pydantic import BaseModel

# Cache for loaded prompts to avoid repeated file I/O
_prompt_cache: Dict[str, str] = {}


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


T = TypeVar("T", bound=BaseModel)


def one_shot(
    system: str,
    context: str,
    prompt: str,
    model: str = "gemma3n:e4b",
    seed: int = None,
    context_window: int = None,
) -> str:
    """
    Generates structured prose using a local Ollama model.
    Combines a system directive, contextual setup, and user prompt.

    Args:
        system: System message/directive for the model
        context: Contextual information for the generation
        prompt: User prompt/request
        model: Ollama model name to use
        seed: Random seed for deterministic generation (optional)
        context_window: Context window size for the model (optional)
    """

    # print(f"system: {system}")
    # print(f"context: {context}")
    # print(f"prompt: {prompt}")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": context},
        {"role": "user", "content": prompt},
    ]

    # Build options dict with seed and context window if provided
    options = {}
    if seed is not None:
        options["seed"] = seed
    if context_window is not None:
        options["num_ctx"] = context_window

    try:
        response = ollama.chat(model=model, messages=messages, options=options)
        print(f"Response from model {model}: {response['message']['content']}")
        return response["message"]["content"]
    except Exception as exc:
        print(f"Error during one_shot: {exc}")
        return ""


def one_shot_json(
    system: str,
    context: str,
    prompt: str,
    response_model: Type[T],
    model: str = "gemma3n:e4b",
    seed: int = None,
    context_window: int = None,
) -> T:
    """
    Generates structured JSON response using a local Ollama model with Pydantic validation.

    Args:
        system: System message/directive for the model
        context: Contextual information for the generation
        prompt: User prompt/request
        response_model: Pydantic model class for structured response
        model: Ollama model name to use
        seed: Random seed for deterministic generation (optional)
        context_window: Context window size for the model (optional)

    Returns:
        Validated Pydantic model instance

    Raises:
        Exception: If LLM call fails or response validation fails
    """

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{context}\n\n{prompt}"},
    ]

    # Build options dict with seed and context window if provided
    options = {}
    if seed is not None:
        options["seed"] = seed
    if context_window is not None:
        options["num_ctx"] = context_window

    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            format=response_model.model_json_schema(),
            options=options,
        )
        print(
            f"Structured response from model {model}: {response['message']['content']}"
        )
        return response_model.model_validate_json(response["message"]["content"])
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

    Traits and context are now provided via JSON context instead of injection.

    Returns:
        Generic system prompt for all agents

    Raises:
        FileNotFoundError: If agent_system.md doesn't exist
    """
    return load_prompt("agent_system")


def clear_prompt_cache():
    """Clear the prompt cache. Useful for development/testing."""
    _prompt_cache.clear()
