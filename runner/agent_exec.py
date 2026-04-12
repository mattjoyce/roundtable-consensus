"""Agent executor — spawns external coding agent CLIs with mono context.

Reads agents.yaml for executable configuration, builds the command,
and launches the agent subprocess. The agent is responsible for
submitting its action back to the engine via curl.
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "agents.yaml"
_config_cache: Optional[dict] = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(_CONFIG_PATH) as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def get_agent_config(agent_name: Optional[str] = None) -> dict:
    """Get config for a named agent, or the default."""
    config = _load_config()
    if agent_name is None:
        agent_name = config.get("default_agent", "claude-sonnet")
    agents = config.get("agents", {})
    if agent_name not in agents:
        raise ValueError(
            f"Agent '{agent_name}' not found in agents.yaml. "
            f"Available: {', '.join(agents.keys())}"
        )
    return agents[agent_name]


def _merge_prompt(system_prompt: str, mono_context: str, has_system_arg: bool) -> str:
    """Combine system prompt and mono context into a single blob.

    If the CLI has a separate system_prompt_arg, return just the context.
    Otherwise prepend the system prompt.
    """
    if not has_system_arg and system_prompt:
        return f"{system_prompt}\n\n---\n\n{mono_context}"
    return mono_context


def _reap_process(
    proc: subprocess.Popen,
    tmp_path: Optional[str] = None,
    debug_files: Optional[tuple] = None,
):
    """Wait for process to exit and clean up temp files. Runs in a thread."""
    try:
        proc.wait()
    except Exception:
        pass
    if tmp_path:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    if debug_files:
        for fh in debug_files:
            try:
                fh.close()
            except OSError:
                pass


def spawn_agent(
    agent_name: Optional[str],
    system_prompt: str,
    mono_context: str,
    cwd: Optional[str] = None,
    debug_dir: str = "",
) -> subprocess.Popen:
    """Spawn an agent CLI subprocess with the mono context.

    Returns the Popen handle. The runner does NOT wait for completion —
    the agent is responsible for curling its action back to the engine.
    A background thread reaps the process to avoid zombies.
    """
    agent_cfg = get_agent_config(agent_name)

    executable = agent_cfg["executable"]
    args = list(agent_cfg.get("args", []))
    input_mode = agent_cfg.get("input_mode", "stdin")
    system_prompt_arg = agent_cfg.get("system_prompt_arg", "")
    extra_env = agent_cfg.get("env", {})
    has_system_arg = bool(system_prompt_arg)

    # Build command
    cmd = [executable] + args

    # Add system prompt if the CLI supports a separate flag
    if has_system_arg and system_prompt:
        cmd.extend([system_prompt_arg, system_prompt])

    # Prepare input based on input_mode
    stdin_data = None
    tmp_path = None

    if input_mode == "stdin":
        stdin_data = _merge_prompt(system_prompt, mono_context, has_system_arg)

    elif input_mode == "arg":
        prompt_arg = agent_cfg.get("prompt_arg", "-p")
        cmd.extend([prompt_arg, _merge_prompt(system_prompt, mono_context, has_system_arg)])

    elif input_mode == "file":
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="rtc_context_"
        )
        tmp.write(_merge_prompt(system_prompt, mono_context, has_system_arg))
        tmp.close()
        tmp_path = tmp.name
        prompt_arg = agent_cfg.get("prompt_arg", "-f")
        cmd.extend([prompt_arg, tmp_path])

    # Build environment
    env = {**os.environ, **extra_env}

    # Capture stdout/stderr to files if debug_dir is set
    debug_files = None
    if debug_dir:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        stdout_f = open(Path(debug_dir) / "stdout.txt", "wb")
        stderr_f = open(Path(debug_dir) / "stderr.txt", "wb")
        stdout_target, stderr_target = stdout_f, stderr_f
        debug_files = (stdout_f, stderr_f)
    else:
        stdout_target = subprocess.DEVNULL
        stderr_target = subprocess.DEVNULL

    # Spawn — fire and forget
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_data else None,
        stdout=stdout_target,
        stderr=stderr_target,
        env=env,
        cwd=cwd or str(Path(__file__).resolve().parent.parent),
    )

    # Write stdin and close
    if stdin_data:
        try:
            proc.stdin.write(stdin_data.encode())
            proc.stdin.close()
        except BrokenPipeError:
            pass  # Process may have exited already

    # Reap process in background to avoid zombies and clean up temp files
    threading.Thread(
        target=_reap_process, args=(proc, tmp_path, debug_files), daemon=True
    ).start()

    return proc
