"""
Prompt loading utilities for LLM integration.
Handles loading and parsing prompt files from the prompts/ directory.
"""

import os
import json
from typing import Dict, Tuple, Any
from pathlib import Path

# Cache for loaded prompts to avoid repeated file I/O
_prompt_cache: Dict[str, str] = {}

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
    
    content = prompt_file.read_text(encoding='utf-8').strip()
    
    # Cache the result
    _prompt_cache[prompt_name] = content
    
    return content

def load_agent_system_prompt(traits: Dict[str, float]) -> str:
    """
    Load the agent system prompt and inject personality traits.
    
    Args:
        traits: Dictionary of agent personality traits (0.0-1.0 scale)
    
    Returns:
        System prompt with traits injected
    
    Raises:
        FileNotFoundError: If agent_system.md doesn't exist
    """
    system_template = load_prompt("agent_system")
    traits_json = json.dumps(traits, indent=2)
    return system_template.format(traits_json=traits_json)

def clear_prompt_cache():
    """Clear the prompt cache. Useful for development/testing."""
    global _prompt_cache
    _prompt_cache.clear()