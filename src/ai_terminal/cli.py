"""Command-line interface for ai-terminal."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer


app = typer.Typer(add_completion=False, no_args_is_help=True)
MODEL = "gpt-5.6-luna"
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": ["string", "null"]},
        "command": {"type": ["string", "null"]},
    },
    "required": ["message", "command"],
    "additionalProperties": False,
}
INSTRUCTIONS = """You are a quick AI terminal assistant. Return a JSON object matching the
provided schema. Choose exactly one of these outcomes:
- For a question, put a direct, very brief plain-text answer in message and null in command.
- When the user asks to do something that requires the terminal, do not run any tool, instead put
  the needed shell command in the command field. The ai terminal assistant will automatically fill
  the commmand for the user to run.
- If a brief explanation is useful alongside a command, use both fields.

Do not use anytools. You may use web search only when fresh external information is necessary;
otherwise answer immediately. Do not include Markdown or decorative formatting in message. Do not put newlines in command.

User request: """
ZSHRC_BLOCK = r'''# ai-terminal autofill
ai() {
  local ai_result ai_message ai_command
  local -a ai_fields
  if [[ $# -eq 0 || "$1" == "init" || "$1" == "-h" || "$1" == "--help" ]]; then
    command ai "$@"
    return $?
  fi
  [[ "$1" == "ask" ]] && shift
  ai_result="$(command ai ask "$@")" || return $?
  ai_fields=("${(@f)$(print -r -- "$ai_result" | python3 -c '
import base64, json, sys
result = json.load(sys.stdin)
for field in ("message", "command"):
    value = result.get(field) or ""
    print(base64.b64encode(value.encode()).decode())
')}")
  ai_message="$(print -rn -- "$ai_fields[1]" | base64 -D)"
  ai_command="$(print -rn -- "$ai_fields[2]" | base64 -D)"
  [[ -n "$ai_message" ]] && print -r -- "$ai_message"
  [[ -n "$ai_command" ]] && print -z -- "$ai_command"
}'''


@app.command()
def init() -> None:
    """Show how to enable safe command autofill in Zsh."""
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists() and ZSHRC_BLOCK in zshrc.read_text(encoding="utf-8"):
        typer.echo(f"Autofill is configured in {zshrc}.")
        return

    typer.echo("Command autofill is not configured. ai will still return JSON, but it cannot prefill commands yet.")
    typer.echo("\nTo enable autofill:")
    typer.echo(f"1. Open {zshrc} in an editor.")
    typer.echo("2. Add this text at the end of the file:")
    typer.echo(f"\n{ZSHRC_BLOCK}")
    typer.echo("\n3. Restart your terminal, or run: source ~/.zshrc")
    typer.echo("\nAutofill only places a suggested command at your prompt. It never runs it.")


@app.command()
def ask(query: Annotated[list[str], typer.Argument(help="Question or terminal request.")]) -> None:
    """Return JSON containing a concise message and/or a suggested command."""
    zshrc = Path.home() / ".zshrc"
    if not zshrc.exists() or ZSHRC_BLOCK not in zshrc.read_text(encoding="utf-8"):
        typer.echo("Command autofill is not configured.\n", err=True)
        typer.echo("To enable autofill:", err=True)
        typer.echo(f"1. Open {zshrc} in an editor.", err=True)
        typer.echo("2. Add this text at the end of the file:\n", err=True)
        typer.echo(ZSHRC_BLOCK, err=True)
        typer.echo("\n3. Restart your terminal, or run: source ~/.zshrc", err=True)
        typer.echo("\nAutofill only places a suggested command at your prompt. It never runs it.", err=True)
        raise typer.Exit(1)
    if shutil.which("codex") is None:
        typer.echo("Codex CLI was not found on PATH.", err=True)
        raise typer.Exit(127)

    with tempfile.TemporaryDirectory(prefix="ai-terminal-") as directory:
        directory_path = Path(directory)
        output_path = directory_path / "answer.json"
        schema_path = directory_path / "schema.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA), encoding="utf-8")
        result = subprocess.run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--model",
                MODEL,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                f"{INSTRUCTIONS}{' '.join(query)}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            typer.echo(result.stderr or result.stdout or "Codex exited without an error message.", err=True)
            raise typer.Exit(result.returncode)
        try:
            response = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(response, dict) or set(response) != {"message", "command"}:
                raise ValueError("Codex did not return the expected JSON object.")
            if not all(value is None or isinstance(value, str) for value in response.values()):
                raise ValueError("Codex returned invalid field values.")
            if "\n" in (response["command"] or "") or "\r" in (response["command"] or ""):
                raise ValueError("Codex returned a multi-line command.")
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
            typer.echo(f"Could not read Codex's response: {error}", err=True)
            raise typer.Exit(1) from error
    typer.echo(json.dumps(response, ensure_ascii=False))


def main() -> None:
    """Run `ask` when no explicit subcommand was given."""
    if len(sys.argv) > 1 and sys.argv[1] not in {"ask", "init", "-h", "--help"}:
        app(args=["ask", *sys.argv[1:]])
        return
    app()
