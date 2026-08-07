FROM tmux-mcp-sandbox-base

ENV PI_HOME=/root/.pi

RUN npm install -g @earendil-works/pi-coding-agent pi-mcp-adapter

COPY docker/pi-mcp.json /tmp/pi-mcp.json

RUN mkdir -p /root/.pi/agent /root/.config/tmux-mcp \
    && cp /tmp/pi-mcp.json /root/.pi/agent/mcp.json \
    && printf 'promptSetupPiMcp: false\n' > /root/.config/tmux-mcp/config.yaml

CMD ["sleep", "infinity"]
