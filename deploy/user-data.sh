#!/bin/bash
# First-boot setup for the WOW voice-agent host (Amazon Linux 2023).
set -euxo pipefail

dnf install -y docker git
systemctl enable --now docker

# docker compose v2 plugin
DOCKER_CONFIG=/usr/local/lib/docker
mkdir -p "$DOCKER_CONFIG/cli-plugins"
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"

mkdir -p /opt
