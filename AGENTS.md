## Tmux MCP

When interacting with tmux sessions:
* "send" a command = use `mcp__tmux__send_command` (sends a string to the
  terminal but does not execute it until the user hits enter)
* "execute" or "run" a command = use `mcp__tmux__execute_command` (waits
  for completion and returns output)

### SAFETY: Prompt Verification

DO NOT EXECUTE ANY COMMANDS USING TMUX WITHOUT FIRST VERIFYING WHAT THE
`prompt_verify_string` SHOULD BE!

To check what the `prompt_verify_string` should be
1. read the last few lines from the terminal
2. verify the prompt line matches what the user requested
3. set the `prompt_verify_string` of subsequent commands to the relavent
  part of the current prompt based on the user's request

ALWAYS SET A `prompt_verify_string` when executing a command in a tmux session

Use `prompt_verify_string` to verify the terminal state before executing
commands:

* **kubectl context**: The prompt includes the current kubectl context.
  Before running kubectl commands, use `prompt_verify_string` with the
  expected context name (e.g., `"prod10"`) to ensure you're targeting
  the correct cluster
* **Safety first**: When executing `kubectl`, `helm` or any other
  command using a kubernetes context, make sure to use the
  `prompt_verify_string` with the expected context. If the user did not
  provide a context, remind them.
* Before executing the first command for a given context, check the full
  context string using the `get_last_lines` tool, make sure it matches
  what the user requested, and use the full line in the `prompt_verify_string`
  for future command executions
* If verification fails, the tool returns `"prompt_mismatch"` instead
  of executing

### Extending commands

When asked to extend an already typed command in tmux, send only the remainder,
not the full command. This is because the command text is already in the
terminal input buffer and sending the full command duplicates it and causes
errors.

How to apply: Before sending, check `get_last_lines` to see what is already
typed on the prompt line, then send only the delta.
