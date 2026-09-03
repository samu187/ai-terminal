"""Command-line interface for ai-terminal."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
  local ai_result ai_command
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
value = result.get("command") or ""
print(base64.b64encode(value.encode()).decode())
')}")
  ai_command="$(print -rn -- "$ai_fields[1]" | base64 -D)"
  [[ -n "$ai_command" ]] && print -z -- "$ai_command"
}'''


class MessageStream:
    """Extract the JSON ``message`` value as it arrives in small chunks."""

    def __init__(self) -> None:
        self.buffer = ""
        self.started = False
        self.done = False
        self.escaped = False
        self.unicode_escape = ""

    def write(self, chunk: str) -> None:
        if self.done:
            return
        self.buffer += chunk
        if not self.started:
            marker = '"message"'
            position = self.buffer.find(marker)
            if position < 0:
                self.buffer = self.buffer[-len(marker) :]
                return
            colon = self.buffer.find(":", position + len(marker))
            quote = self.buffer.find('"', colon + 1) if colon >= 0 else -1
            if quote < 0:
                return
            self.started = True
            self.buffer = self.buffer[quote + 1 :]

        while self.buffer:
            character, self.buffer = self.buffer[0], self.buffer[1:]
            if self.unicode_escape:
                self.unicode_escape += character
                if len(self.unicode_escape) == 4:
                    try:
                        typer.echo(chr(int(self.unicode_escape, 16)), nl=False, err=True)
                    except ValueError:
                        pass
                    self.unicode_escape = ""
                    self.escaped = False
                continue
            if self.escaped:
                if character == "u":
                    self.unicode_escape = ""
                    continue
                typer.echo({"n": "\n", "r": "\r", "t": "\t"}.get(character, character), nl=False, err=True)
                self.escaped = False
            elif character == "\\":
                self.escaped = True
            elif character == '"':
                self.done = True
                return
            else:
                typer.echo(character, nl=False, err=True)


def _send(process: subprocess.Popen[str], request: dict[str, object]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()


def _read_event(process: subprocess.Popen[str]) -> dict[str, object]:
    assert process.stdout is not None
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("Codex app server closed before returning a response.")
    return json.loads(line)


def _read_response(process: subprocess.Popen[str], request_id: int) -> dict[str, object]:
    """Read through notifications until the response to one request arrives."""
    while True:
        event = _read_event(process)
        if event.get("id") == request_id:
            return event


def _stream_response(query: list[str]) -> dict[str, object]:
    """Run an ephemeral Codex turn and display its message while it is generated."""
    process = subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        _send(process, {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "ai-terminal", "version": "0.1.0"}}})
        initialized = _read_response(process, 1)
        if "error" in initialized:
            raise RuntimeError(str(initialized["error"]))
        _send(process, {"method": "initialized", "params": {}})
        _send(process, {"id": 2, "method": "thread/start", "params": {"ephemeral": True, "model": MODEL, "sandbox": "read-only", "approvalPolicy": "never", "developerInstructions": INSTRUCTIONS}})
        thread = _read_response(process, 2)
        if "error" in thread:
            raise RuntimeError(str(thread["error"]))
        thread_id = thread["result"]["thread"]["id"]  # type: ignore[index]
        _send(process, {"id": 3, "method": "turn/start", "params": {"threadId": thread_id, "input": [{"type": "text", "text": " ".join(query)}], "outputSchema": OUTPUT_SCHEMA}})
        started = _read_response(process, 3)
        if "error" in started:
            raise RuntimeError(str(started["error"]))

        stream = MessageStream()
        final_message: str | None = None
        while True:
            event = _read_event(process)
            if event.get("method") == "item/agentMessage/delta":
                stream.write(event["params"]["delta"])  # type: ignore[index]
            elif event.get("method") == "item/completed":
                item = event["params"]["item"]  # type: ignore[index]
                if item.get("type") == "agentMessage":  # type: ignore[union-attr]
                    final_message = item["text"]  # type: ignore[index]
            elif event.get("method") == "turn/completed":
                break
        if stream.started:
            typer.echo(err=True)
        if final_message is None:
            raise RuntimeError("Codex completed without an assistant response.")
        return json.loads(final_message)
    finally:
        process.terminate()
        process.wait()


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

    try:
        response = _stream_response(query)
        if not isinstance(response, dict) or set(response) != {"message", "command"}:
            raise ValueError("Codex did not return the expected JSON object.")
        if not all(value is None or isinstance(value, str) for value in response.values()):
            raise ValueError("Codex returned invalid field values.")
        if "\n" in (response["command"] or "") or "\r" in (response["command"] or ""):
            raise ValueError("Codex returned a multi-line command.")
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        typer.echo(f"Could not read Codex's response: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(response, ensure_ascii=False))


def main() -> None:
    """Run `ask` when no explicit subcommand was given."""
    if len(sys.argv) > 1 and sys.argv[1] not in {"ask", "init", "-h", "--help"}:
        app(args=["ask", *sys.argv[1:]])
        return
    app()
