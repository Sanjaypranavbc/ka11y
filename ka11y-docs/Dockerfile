# syntax=docker/dockerfile:1.7
# Mintlify CLI runner. The actual docs directory is bind-mounted at runtime
# from docker-compose (./ka11y-docs:/docs), so we do not COPY the docs here —
# that keeps the image small and avoids rebuilds when docs change.
FROM node:24-slim

WORKDIR /docs

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/root/.npm \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    npm install -g @mintlify/cli@4.0.1049

EXPOSE 3000

CMD ["mintlify", "dev", "--no-open"]
