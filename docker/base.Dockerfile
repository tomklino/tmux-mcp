FROM python:3.14-slim

ENV DEBIAN_FRONTEND=noninteractive \
    TERM=xterm-256color \
    VIRTUAL_ENV=/opt/tmux-mcp-venv \
    PATH=/opt/tmux-mcp-venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        gnupg \
        tmux \
        zsh && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/tmux-mcp
COPY pyproject.toml README.md ./
COPY tmux_mcp ./tmux_mcp

RUN python -m venv "$VIRTUAL_ENV" && \
    "$VIRTUAL_ENV/bin/pip" install --upgrade pip setuptools wheel && \
    "$VIRTUAL_ENV/bin/pip" install .

RUN mkdir -p /workspace /sandbox-state /root/.config/tmux-mcp /root/.local/share/tmux-mcp

CMD ["sleep", "infinity"]
