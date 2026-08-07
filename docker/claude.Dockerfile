FROM tmux-mcp-sandbox-base

RUN npm install -g @anthropic-ai/claude-code

RUN cat > /root/.claude.json <<'JSON'
{
  "mcpServers": {
    "tmux": {
      "type": "stdio",
      "command": "tmux-mcp-server",
      "args": [],
      "env": {}
    }
  }
}
JSON

CMD ["sleep", "infinity"]
