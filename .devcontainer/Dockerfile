ARG VARIANT=3.12-bookworm
FROM mcr.microsoft.com/devcontainers/python:1-${VARIANT}

COPY .devcontainer/certs/ /tmp/devcontainer-certs/

# Keep image lean and avoid unnecessary packages by default.
RUN rm -f /etc/apt/sources.list.d/yarn.list && apt-get update && apt-get install -y --no-install-recommends ca-certificates gh

RUN set -eux; mkdir -p /usr/local/share/ca-certificates/custom; find /usr/local/share/ca-certificates/custom -type f -name '*.crt' -delete; found=0; for cert_file in /tmp/devcontainer-certs/*.crt /tmp/devcontainer-certs/*.pem; do [ -f "$cert_file" ] || continue; found=1; cert_name="$(basename "$cert_file")"; cert_stem="${cert_name%.*}"; cp "$cert_file" "/usr/local/share/ca-certificates/custom/${cert_stem}.crt"; done; if [ "$found" -eq 1 ]; then update-ca-certificates; fi; rm -rf /tmp/devcontainer-certs

RUN rm -rf /var/lib/apt/lists/*

USER vscode
