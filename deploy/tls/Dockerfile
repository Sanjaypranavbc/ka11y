# Caddy with the rate-limit module. Build once:
#   docker compose -f docker-compose.yml -f docker-compose.tls.yml build edge
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
