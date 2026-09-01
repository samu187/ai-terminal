# ai-terminal

`ai` is a read-only Codex terminal assistant. It returns JSON with two fields:
`message` for a short answer and `command` for an optional single-line Zsh
command. It never runs that command.

## Install

Codex must already be installed and authenticated.

```sh
uv tool install .
```

## Configure Zsh autofill

Run this after installation:

```sh
ai init
```

It checks whether `~/.zshrc` has the optional autofill setup. If it does not,
it prints clear instructions and the exact text to add. `ai` never changes
`.zshrc` itself.

The Zsh setup reads the JSON returned by `ai`, prints `message`, and places
`command` at your prompt. You inspect the command and press Enter yourself.

## Use

```sh
ai ask what is the difference between TCP and UDP
ai ask how do I see uncommitted Git edits
```

`ask` is optional, so this is identical:

```sh
ai how do I see uncommitted Git edits
```

Before Zsh autofill is configured, `ai ask` prints the same setup instructions
as `ai init` instead of making a Codex request.

`ai` uses `gpt-5.6-luna`, an ephemeral session, and Codex's `read-only`
sandbox. Its prompt prohibits local terminal, filesystem, Git, and environment
tools; it allows web search only when fresh external information is needed.
