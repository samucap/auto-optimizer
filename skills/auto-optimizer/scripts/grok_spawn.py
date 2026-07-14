"""Spawn stage workers via grok CLI (headless) for script-driven orchestration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from logging_util import log_event


def grok_available() -> bool:
    return shutil.which("grok") is not None


def run_grok_prompt(
    prompt: str,
    *,
    cwd: Path,
    worktree: bool = False,
    timeout: int | None = None,
    yolo: bool = True,
    output_format: str = "json",
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Run `grok -p` and return parsed result dict."""
    if not grok_available():
        return {
            "ok": False,
            "error": "grok CLI not found on PATH",
            "text": "",
        }
    cmd = ["grok", "-p", prompt, "--cwd", str(cwd), "--output-format", output_format]
    if yolo:
        cmd.append("--yolo")
    if worktree:
        cmd.append("--worktree")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as e:
        if log_path:
            log_event(log_path, {"type": "grok_timeout", "error": str(e)})
        return {"ok": False, "error": f"timeout: {e}", "text": ""}
    except Exception as e:
        if log_path:
            log_event(log_path, {"type": "grok_error", "error": str(e)})
        return {"ok": False, "error": str(e), "text": ""}

    text = proc.stdout.strip()
    result: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "text": text,
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
    }
    if output_format == "json" and text:
        try:
            result["json"] = json.loads(text)
            result["text"] = result["json"].get("text", text)
        except json.JSONDecodeError:
            pass
    if log_path:
        log_event(
            log_path,
            {
                "type": "grok_complete",
                "ok": result["ok"],
                "returncode": proc.returncode,
                "worktree": worktree,
            },
        )
    return result


def build_stage_prompt(
    *,
    persona_instructions: str,
    stage: str,
    module_yaml_text: str,
    artifact_dir: Path,
    prior_context: str,
    extra: str = "",
) -> str:
    return textwrap.dedent(
        f"""\
        {persona_instructions}

        ---

        You are the **{stage}** stage of an auto-optimizer cycle.

        ## Rules
        - Do **not** spawn subagents (depth limit). Write outputs only.
        - Write your primary structured result to: `{artifact_dir / "output.json"}`
        - Write a JSON Schema for that output to: `{artifact_dir / "schema.json"}`
        - Also write a short human summary to: `{artifact_dir / "summary.md"}`
        - Stay within module budgets and files_to_edit / files_forbidden.

        ## Module
        ```yaml
        {module_yaml_text}
        ```

        ## Prior context
        {prior_context or "(none)"}

        {extra}

        When done, ensure output.json validates against schema.json.
        """
    )


def load_persona_instructions(persona_name: str) -> str:
    """Load instructions from ~/.grok/personas or repo personas via symlink."""
    candidates = [
        Path.home() / ".grok" / "personas" / f"{persona_name}.toml",
        Path(__file__).resolve().parents[3] / "personas" / f"{persona_name}.toml",
    ]
    for p in candidates:
        if p.exists():
            return _extract_instructions(p.read_text(encoding="utf-8"))
    return f"(persona {persona_name} not found; proceed with stage best practices)"


def _extract_instructions(toml_text: str) -> str:
    # Lightweight extract of instructions = """...""" without full TOML parse
    marker = "instructions"
    if marker not in toml_text:
        return toml_text
    # find triple-quoted block after instructions
    import re

    m = re.search(
        r"instructions\s*=\s*\"\"\"(.*?)\"\"\"",
        toml_text,
        flags=re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"instructions\s*=\s*'''(.*?)'''",
        toml_text,
        flags=re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return toml_text
