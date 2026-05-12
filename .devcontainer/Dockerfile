ARG VARIANT=3.12-bookworm
FROM mcr.microsoft.com/devcontainers/python:1-${VARIANT}

# Keep image lean and avoid unnecessary packages by default.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gh \
    && rm -rf /var/lib/apt/lists/*

USER vscode
