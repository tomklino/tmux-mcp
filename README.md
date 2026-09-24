# Tmux Buddy

Tmux Buddy is an MCP server that aims to increase visiblity and the safety of the commands executed by AI agents.
It allows to share a tmux terminal between a human and an agent in such a way that the human has full visiblity
and finer control over the commands.

<img width="1080" height="540" alt="tmux-mcp-again" src="https://github.com/user-attachments/assets/c909f390-04e5-4569-9999-8578c40ef26c" />

## Features

### Safety Features

* **Send Command**: Send a command to the terminal without executing it. Uses
  [bracketed paste](https://en.wikipedia.org/wiki/Bracketed-paste) to make sure accidental execution can't occur.
* **Safety Verification**: Use `prompt_verify_string` to ensure commands are executed in the correct context.
  the prompt line must show the string the agent expects or the command won't be sent (e.g., specific directory or Kubernetes context)
* **Capture Output**: Read the last N lines of terminal output. The agent is instructed to always check the terminal current output
  before executing the first command.
* **Color Coded Terminals**: To prevent accidental confusion on the human side

### Speed-up Features

* **Execute Commands**: Run commands in a tmux session and wait for completion - detects completion and returns immediately
* **Interactive Detection**: Automatically detects when a terminal enters an interactive state (e.g., `vim`, `nano`, `less`) so the
  agent doesn't need to wait for a time-out
* **Command Monitoring**: Wait for asynchronous commands to finish and retrieve their output.
* **Send Interrupt/Exit keys**: Allows the agent to exit by itself from interactive programs or commands that hang for too long.

## Prerequisites

* Python 3.10+
* The **system `tmux` executable** on `PATH`.

`tmux` is not a Python package. Consequently, pip and pipx cannot install it as
a dependency of `tmux-mcp`; install it with the operating system's package
manager first.

## Installation

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install tmux pipx
pipx ensurepath
pipx install git+https://github.com/tomklino/tmux-mcp.git
tmux-cli doctor
```

### Fedora / RHEL

```bash
sudo dnf install tmux pipx
pipx ensurepath
pipx install git+https://github.com/tomklino/tmux-mcp.git
tmux-cli doctor
```

### Arch Linux

```bash
sudo pacman -S tmux python-pipx
pipx ensurepath
pipx install git+https://github.com/tomklino/tmux-mcp.git
tmux-cli doctor
```

### macOS

```bash
brew install tmux pipx
pipx ensurepath
pipx install git+https://github.com/tomklino/tmux-mcp.git
tmux-cli doctor
```

Restart the shell after `pipx ensurepath` if `tmux-cli` is not found.

### Windows

Native Windows is not supported because tmux requires a Unix-like environment.
Use [WSL][3], run the Ubuntu / Debian instructions above inside WSL, and run the
MCP client in (or configure it to invoke commands in) that same WSL environment.

### Why doesn't pipx install tmux?

pipx successfully installs this project's Python package and exposes
`tmux-cli` and `tmux-mcp-server`. It deliberately does not manage OS packages.
If `tmux-cli doctor` reports that tmux is missing, install tmux using one of the
commands above. `tmux-cli new` also performs this check and prints an actionable
message rather than a Python traceback.

### Client Configuration

To use the server with an MCP client, configure the installed
`tmux-mcp-server` executable. No source checkout or path to a Python script is
needed. Run `command -v tmux-mcp-server` if your client does not inherit the
shell's pipx `PATH`, and use that absolute executable path in its configuration.

It's recommended to copy or reference the `AGENTS.md` file contents to the
agent's instructions as it helps the agent use the safety guards in situations
where they are required.

#### Claude Code

You can add the MCP server to Claude Code using the CLI:

```bash
claude mcp add --scope user tmux tmux-mcp-server
```

Or add the following to your `~/.claude.json` within your project's `mcpServers` object:

```json
"tmux": {
  "type": "stdio",
  "command": "tmux-mcp-server",
  "args": [],
  "env": {}
}
```

#### OpenCode

Add the following to your OpenCode configuration file located at `~/.config/opencode/opencode.json` under the `"mcp"` key:

```json
"mcp": {
  "tmux": {
    "type": "local",
    "command": ["tmux-mcp-server"],
    "enabled": true
  }
}
```

#### Pi Agent

First, install the MCP adapter:

```bash
pi install npm:pi-mcp-adapter
```

Then, add the following to your `~/.pi/agent/mcp.json` or project-specific `.pi/mcp.json`:

```json
{
  "mcpServers": {
    "tmux": {
      "command": "tmux-mcp-server",
      "args": []
    }
  }
}
```

## Usage

### Permissions + in-tmux toggle (recommended)

When you share a tmux session with an AI agent, **permission modes** let you control *what the agent is allowed to do* in that session.

Create sessions with:

```bash
tmux-cli new <name>
```

The session will start by default on "deny", by won't let the agent any permissions.
cycle through the modes to allow the agent to work with the terminal.

You may change the default permission level new terminals start at in the permission
config file (default: $HOME/.config/tmux-mcp/permissions.json)

In the tmux session, the status bar shows the current mode:

- `MCP:DENY` — agent access is blocked for this session.
- `MCP:READ` — agent can *observe only* (e.g. read terminal output). No typing.
- `MCP:SEND` — agent can *type commands* into the prompt, but won’t execute them.
  Use this when you want to review/edit a command before running it yourself.
- `MCP:EXEC` — agent can type *and* execute commands.

To change modes from inside tmux, use **`CTRL + ]`** to cycle:

`DENY → READ → SEND → EXEC → DENY`

Environment override (optional): set `TMUX_MCP_PERMISSIONS_FILE` to use a custom permissions file location.

### CLI Utility

The installed `tmux-cli` utility manages sessions:

```bash
# Check that the non-Python dependency is available
tmux-cli doctor

# Create a new session with the custom prompt used by the MCP
tmux-cli new green
```

#### Recording Sessions

To record a new tmux session, include the `--record` flag.
Recordings are saved to `~/.tmux-session-recordings` with a filename format of
`<session_name>_YYYY-MM-DD_HH-MM-SS.cast`. [asciinema] must be installed on the
system to use this feature.

> [!TIP]
> Choose a color for the name of the terminal to color code the terminal status line


After creating the session, you can intract with it yourself or tell the
agent to interact with it as well. For example:

```
use the tmux session "green" to inspect the output of my last command
and explain why it's not working.
```

Or

```
use the tmux session "green" to check if there are any pods in a
crashloop. If there are any, describe them to find the reason.
```

Or

```
in the session "green" I typed in a `kubectl` command. Extend it
with custom columns to print out the name of the pod and the image
it runs.
```

## Tools Provided

| Tool | Description |
|------|-------------|
| `get_last_lines` | Get the last N lines from a tmux terminal session. |
| `send_command` | Send a command string without executing it |
| `send_interrupt` | Send CTRL+C to the terminal. |
| `execute_command` | Execute a command and wait for completion/prompt. |
| `wait_for_completion` | Wait for a previously sent command to finish. |
| `get_last_command_output` | Extract the last command and its output from the terminal. |


[asciinema]: https://docs.asciinema.org/getting-started
[1]: https://github.com/tmux/tmux/wiki/installing
[2]: https://pipx.pypa.io/stable/how-to/install-pipx.html
[3]: https://learn.microsoft.com/windows/wsl/install
