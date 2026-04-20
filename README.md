# Tmux MCP

Tmux MCP is a Model Context Protocol (MCP) server that provides tools for interacting with `tmux` terminal sessions. It allows an AI agent to read terminal output, execute commands, and monitor the state of a terminal session in a safe and controlled manner.

## Features

- **Execute Commands**: Run commands in a tmux session and wait for completion.
- **Capture Output**: Read the last N lines of terminal output.
- **Safety Verification**: Use `prompt_verify_string` to ensure commands are executed in the correct context (e.g., specific directory or Kubernetes context).
- **Interactive Detection**: Automatically detects when a terminal enters an interactive state (e.g., `vim`, `nano`, `less`).
- **Command Monitoring**: Wait for asynchronous commands to finish and retrieve their output.
- **Send and Interrupt**: Send strings to the terminal without execution (for user review) or send interrupts (Ctrl+C).

## Prerequisites

- Python 3.10+
- `tmux` installed on the system.

## Installation

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd tmux-mcp
   ```

2. Install dependencies (it uses `mcp` library):
   ```bash
   pip install mcp
   ```

## Usage

### Starting the MCP Server

You can run the MCP server directly:

```bash
python3 tmux_mcp.py
```

To use it with an MCP client (like Claude Desktop or another agent harness), add it to your configuration.

### CLI Utility

The project includes a CLI utility `tmux_cli.py` for managing sessions:

```bash
# Create a new session with the custom prompt used by the MCP
./tmux_cli.py new my-session
```

## Tools Provided

| Tool | Description |
|------|-------------|
| `get_last_lines` | Get the last N lines from a tmux terminal session. |
| `send_command` | Send a command string without executing it (no newline). |
| `send_interrupt` | Send CTRL+C to the terminal. |
| `execute_command` | Execute a command and wait for completion/prompt. |
| `wait_for_completion` | Wait for a previously sent command to finish. |
| `get_last_command_output` | Extract the last command and its output from the terminal. |

## Safety: Prompt Verification

The `prompt_verify_string` argument in `execute_command` and `send_command` is a critical safety feature. Before executing a command, the server checks if the current terminal prompt contains the specified string.

Example:
If you want to ensure you are in a specific directory or Kubernetes context:
```python
# Only executes if the prompt indicates we are in the 'prod' context
execute_command(session_name="work", command="ls", prompt_verify_string="prod-cluster")
```

## Internal Implementation

The server uses a specialized prompt (`__>`) to reliably detect when a command has finished executing and to separate command input from output. This is automatically set up when using `tmux_cli.py new` or when `tmux_lib.create_tmux_session` is called.
