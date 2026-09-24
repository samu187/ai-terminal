"""Command-line interface for ai-terminal."""

from __future__ import annotations

import json
import os
import platform
import sys
from typing import Annotated

import typer
from openai import OpenAI, OpenAIError


app = typer.Typer(add_completion=False, no_args_is_help=True)
MODEL = "gpt-6-luna"
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": ["string", "null"]},
        "command": {
            "type": ["string", "null"],
            "pattern": r"^[^\u0000-\u001f\u007f]*$",
        },
    },
    "required": ["message", "command"],
    "additionalProperties": False,
}
INSTRUCTIONS = r"""You suggest shell commands and answer short technical questions.
Return the requested JSON object.
- For a terminal task (including "how do I.." requests and "do this.." requests for a command), put
  only the single-line command in command and set message to null. Do not explain routine
  commands, introduce them, or repeat them in message.
- For a conceptual question, give a brief plain-text message and set command to null.
- Add a brief message alongside a command only if the user explicitly asks for an
  explanation or essential context is needed to use it correctly.
- If required details are missing, ask a short clarification in message and set
  command to null. Never invent paths or claim to have inspected the user's machine.
Do not use tools, browse, or execute commands. No tools are available.
Do not include Markdown, code fences, or newlines in command.
The decoded command must contain no literal control characters, including tabs.
For printf/awk formats, preserve shell escapes as backslash characters: the shell
command printf '%s\n' hello must be encoded in JSON as "printf '%s\\n' hello".
Use spaces between arguments and keep pipelines on one line.
Use syntax and standard utilities compatible with the OS and shell given below.
Do not assume tools from a different OS are installed.
"""
ZSHRC_BLOCK = r'''# ai-terminal autofill
ai() {
  local ai_result ai_command
  if [[ $# -eq 0 || "$1" == "init" || "$1" == "-h" || "$1" == "--help" ]]; then
    command ai "$@"
    return $?
  fi
  [[ "$1" == "ask" ]] && shift
  ai_result="$(AI_TERMINAL_SHELL=zsh command ai ask "$@")" || return $?
  ai_command="$(print -r -- "$ai_result" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("command") or "", end="")
')" || return $?
  if [[ -n "$ai_command" ]]; then
    print -rz -- "$ai_command"
  fi
}'''


def _request(query: list[str]) -> dict[str, str | None]:
    shell = os.environ.get("AI_TERMINAL_SHELL") or os.environ.get("SHELL") or "unknown"
    with OpenAI(timeout=30.0, max_retries=0) as client:
        result = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS + f"\nHost OS: {platform.system()}; shell: {shell}.",
            input=" ".join(query),
            reasoning={"effort": "none"},
            tools=[],
            stream=False,
            store=False,
            text={"format": {
                "type": "json_schema",
                "name": "terminal_response",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }},
        )
    if result.status != "completed" or not result.output_text:
        raise ValueError("The API returned no complete answer. Try rephrasing your request.")
    response = json.loads(result.output_text)
    if not isinstance(response, dict) or set(response) != {"message", "command"}:
        raise ValueError("The API returned an unexpected JSON object.")
    if not all(value is None or isinstance(value, str) for value in response.values()):
        raise ValueError("The API returned invalid field values.")
    for char in response["command"] or "":
        if ord(char) < 32 or ord(char) == 127:
            raise ValueError(f"The API returned a command containing control character U+{ord(char):04X}.")
    if not any(response.values()):
        raise ValueError("The API returned an empty answer.")
    return response


@app.command()
def init() -> None:
    """Show how to enable safe command autofill in Zsh."""
    typer.echo("Add this function to ~/.zshrc (replace any previous ai-terminal function):")
    typer.echo(f"\n{ZSHRC_BLOCK}")
    typer.echo("\nThen restart your terminal, or run: source ~/.zshrc")
    typer.echo("Autofill places a command at your prompt. Review it and press Enter to run it.")


@app.command()
def ask(query: Annotated[list[str], typer.Argument(help="Question or terminal request.")]) -> None:
    """Return JSON containing a concise message and/or a suggested command."""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        typer.echo("Set OPENAI_API_KEY in your environment before using ai.", err=True)
        raise typer.Exit(1)
    try:
        response = _request(query)
    except OpenAIError as error:
        typer.echo(f"OpenAI request failed ({type(error).__name__}). Check your API key, quota, and connection.", err=True)
        raise typer.Exit(1) from error
    except ValueError as error:
        typer.echo(f"Could not read the response: {error}", err=True)
        raise typer.Exit(1) from error
    if response["message"]:
        typer.echo(response["message"], err=True)
    typer.echo(json.dumps(response, ensure_ascii=False))



def main() -> None:
    # ensures that `ai` behaves like `ai ask` when no subcommand is given
    if len(sys.argv) > 1 and sys.argv[1] not in {"ask", "init", "-h", "--help"}:
        app(args=["ask", *sys.argv[1:]])
        return
    app()
