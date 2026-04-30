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
* `tmux` installed on the system.

## Installation

1. Clone this repository:

   ```bash
   git clone git@github.com:tomklino/tmux-mcp.git
   cd tmux-mcp
   ```

2. Install dependencies (it uses `mcp` library):

   ```bash
   pip install mcp
   ```

### Client Configuration

To use the server with an MCP client, add it to your configuration. Make sure to provide the absolute path to the `tmux_mcp.py` script.

It's recommended to copy or reference the `AGENTS.md` file contents to the
agent's instructions as it helps the agent use the safety guards in situations
where they are required.

#### Claude Code

You can add the MCP server to Claude Code using the CLI:

```bash
claude mcp add tmux python3 /absolute/path/to/tmux-mcp/tmux_mcp.py
```

Or add the following to your `~/.claude.json` within your project's `mcpServers` object:

```json
"tmux": {
  "type": "stdio",
  "command": "python3",
  "args": ["/absolute/path/to/tmux-mcp/tmux_mcp.py"],
  "env": {}
}
```

#### OpenCode

Add the following to your OpenCode configuration file located at `~/.config/opencode/opencode.json` under the `"mcp"` key:

```json
"mcp": {
  "tmux": {
    "type": "local",
    "command": ["python3", "/absolute/path/to/tmux-mcp/tmux_mcp.py"],
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
      "command": "python3",
      "args": ["/absolute/path/to/tmux-mcp/tmux_mcp.py"]
    }
  }
}
```

## Usage

### CLI Utility

The project includes a CLI utility `tmux_cli.py` for managing sessions:

```bash
# Create a new session with the custom prompt used by the MCP
./tmux_cli.py new green
```

[!TIP] Choose a color for the name of the terminal to color code the terminal status line


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

