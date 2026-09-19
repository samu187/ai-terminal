# ai-terminal

**English in. Terminal command ready. Press Enter to run.**

`ai` translates plain English into terminal commands and prefills your Zsh prompt.
Review or edit the suggested command, then press **Enter** to confirm and run it.
Ask a technical question and get a short answer instead. Routine command requests
come without an explanation.

![ai-terminal demo](docs/demo.gif)

![ai-terminal demo](docs/demo2.gif)

Each question makes one non-streaming OpenAI API request using
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
which keeps costs very low for short queries and command responses.
No agent loop, tool access, or automatic command execution.

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and an OpenAI API key.
Autofill also requires Zsh and `python3` on your PATH.

From the cloned repository:

```sh
uv tool install .
```

Export your key in the shell where you use `ai`:

```sh
export OPENAI_API_KEY="your-api-key"
```

For persistence, set it in your private shell configuration or load it through
your secret manager. The installed CLI inherits this environment variable.

To enable prompt autofill:

```sh
ai init
```

Copy the printed function into `~/.zshrc`

```sh
ai show uncommitted git changes
ai ask what is the difference between TCP and UDP
```

`ask` is optional. Suggested commands are placed at your prompt; review them
before pressing Enter. Without the shell function, the CLI prints JSON with
`message` and `command` fields. Any answer text is also printed to stderr.

Requests are billed to your OpenAI API account at GPT-5.4 mini rates. Only your question
is sent as user input; the CLI does not read your project or shell history.


## Project Structure

```text
src/ai_terminal/
├── __init__.py
└── cli.py          # CLI, API request, response validation, and Zsh setup
docs/
└── demo.gif        # Terminal walkthrough (add your recording here)
pyproject.toml      # Package metadata and dependencies
uv.lock            # Locked dependency versions
```
