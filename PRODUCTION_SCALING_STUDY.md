# Production, scaling and networking: study list for ka11y

Companion to `SQS_WORKER_CONCEPTS.md`. That file explains the implementation; this one
is a preparation list for running it in production on AWS.

Each item has two parts:

- **What to learn and why it matters here.**
- **[Prior connectivity concepts]** in brackets: the networking / connectivity ideas
  you should already understand before this item makes sense. Learn those first.

Stack being prepared for: Next.js UI + FastAPI API behind Caddy on EC2, SQS worker
running Chromium audits, S3 as the run store, LocalStack locally.

---

## 0. Connectivity foundations (learn these before anything below)

These are the bracketed prerequisites. Each appears as a dependency of items further
down, so get comfortable with them first.

| # | Concept | One-line meaning |
|---|---|---|
| N1 | **IP addressing, CIDR, subnets** | How address ranges are carved up; what `10.0.1.0/24` means |
| N2 | **Public vs private IP, NAT** | Private ranges cannot be reached from the internet; NAT rewrites source addresses so they can reach out |
| N3 | **Routing, route tables, default route** | How a packet decides where to go next; `0.0.0.0/0` |
| N4 | **DNS** | Name → IP; record types A / AAAA / CNAME / ALIAS; TTL |
| N5 | **TCP vs UDP, ports, connections** | Three-way handshake, ephemeral ports, what "port 443 open" means |
| N6 | **Stateful vs stateless filtering** | Whether return traffic is auto-allowed (firewall) or must be listed explicitly (ACL) |
| N7 | **TLS / HTTPS** | Handshake, certificates, chain of trust, SNI, termination point |
| N8 | **HTTP semantics** | Request/response, keep-alive, chunked transfer, headers, status codes, idle timeouts |
| N9 | **Proxies and load balancers** | L4 vs L7, reverse proxy, X-Forwarded-For, health checks, sticky sessions |
| N10 | **Long-lived connections** | WebSockets, Server-Sent Events, long polling; why proxies time them out |
| N11 | **Latency, bandwidth, throughput** | Round-trip time vs bytes per second; why cross-AZ and cross-region cost time and money |
| N12 | **Egress vs ingress** | Direction of traffic relative to your network; cloud bills egress |
| N13 | **Endpoints and service URLs** | A service is reachable at a URL; the same code can target different endpoints (AWS vs LocalStack) |
| N14 | **Timeouts and retries on the wire** | Connect timeout vs read timeout; retry storms |
| N15 | **Signals and process lifecycle** | SIGTERM / SIGKILL, grace periods; how an orchestrator stops a container |

---

## A. Queue and worker operations

1. **Queue depth as a scaling signal.** `ApproximateNumberOfMessages` (waiting) vs
   `ApproximateNumberOfMessagesNotVisible` (in flight). Target-tracking autoscaling on
   backlog per worker. This decides how many workers to run.
   [N13 endpoints, N14 timeouts and retries, N11 latency]
2. **Visibility timeout sizing.** Must exceed the longest unit of work or be
   heartbeated. Know the 12-hour maximum and what a late heartbeat causes.
   [N14 timeouts, N5 TCP connections, N11 latency]
3. **DLQ operations.** Alarms on DLQ depth, inspecting a dead letter, redriving
   messages back to the source queue after a fix.
   [N13 endpoints, N14 retries]
4. **Idempotency under retries.** Side effects that are unsafe to repeat (emails,
   billing, third-party calls). Audits are safe; anything added later must be checked.
   [N14 retries, N8 HTTP semantics (idempotent methods)]
5. **Standard vs FIFO queues.** When ordering or deduplication would justify FIFO's
   per-group throughput limit. Today: no.
   [N11 throughput]
6. **Message size limit (256 KB)** and the Extended Client pattern. Theoretical here
   because the message is a pointer.
   [N11 bandwidth, N13 endpoints]
7. **Graceful shutdown in orchestrators.** SIGTERM → grace → SIGKILL. ECS
   `stopTimeout` is capped at 120 s on Fargate; Kubernetes uses
   `terminationGracePeriodSeconds`. A 15-minute drain works in compose, not on Fargate.
   [N15 signals, N9 load balancer deregistration delay, N10 long-lived connections]
8. **Worker right-sizing.** CPU and memory per Chromium, `/dev/shm`,
   `--disable-dev-shm-usage`, how `WORKER_MAX_CONCURRENCY` maps to container size.
   [N11 bandwidth per crawl, N12 egress volume]

## B. Object storage at scale

9. **S3 consistency model.** Strong read-after-write, but no atomic
   compare-and-swap. Two writers to `state.json` is last-writer-wins.
   [N11 latency, N14 retries]
10. **Conditional writes** (`If-None-Match`, `If-Match` on PutObject). The tool for
    turning `state.json` into a safe lock if ever needed.
    [N8 HTTP semantics (ETag, conditional headers)]
11. **Listing cost and pagination.** `ListObjectsV2` is 1000 keys per call; scanning
    thousands of keys for history will not scale. Know when to add an index
    (DynamoDB or re-enabled PostgreSQL).
    [N11 latency, N14 timeouts]
12. **Lifecycle rules.** Expire old screenshots and reports; move to Infrequent Access.
    [none beyond N13]
13. **Presigned URLs.** Serve screenshots and PDFs straight from S3 instead of
    proxying through the API.
    [N7 TLS, N8 HTTP, N4 DNS (bucket hostnames), N12 egress]
14. **Bucket policy, Block Public Access, SSE-S3 / SSE-KMS.** What the Kao security
    sheet will ask for.
    [N2 public vs private, N7 TLS, N13 endpoints]

## C. Compute and deployment

15. **ECS on EC2 vs Fargate vs EC2 + compose** for a Chromium-heavy worker. Fargate
    has limited `/dev/shm`, no GPU, 120 s stop.
    [N15 signals, N1 subnets (task networking), N2 NAT (private tasks)]
16. **IAM task roles / instance profiles.** Least privilege: API gets
    `sqs:SendMessage` + `s3:PutObject`; worker gets receive/delete/change-visibility +
    S3 on its prefix. No access keys in `.env`.
    [N13 endpoints, N7 TLS (SigV4 over HTTPS)]
17. **Rolling vs blue/green deploys** and how each interacts with in-flight audits.
    [N9 load balancers, N4 DNS, N15 signals]
18. **Liveness vs readiness checks.** `/health` must not depend on SQS or the load
    balancer will eject every replica at once.
    [N9 health checks, N8 HTTP status codes, N14 timeouts]
19. **Secrets management.** SSM Parameter Store / Secrets Manager instead of `.env`
    on the host (the missing `KA11Y_SESSION_SECRET` incident).
    [N13 endpoints, N7 TLS]
20. **Immutable images.** Build once, promote the same digest through staging and
    prod.
    [none beyond N13 (registry endpoint)]

## D. Networking (production topology)

21. **VPC fundamentals.** Public vs private subnets, route tables, Internet Gateway vs
    NAT Gateway. Workers belong in private subnets yet must crawl the public web, so
    NAT Gateway and its per-GB cost are unavoidable unless you accept public workers.
    [N1 CIDR, N2 NAT, N3 routing, N12 egress]
22. **VPC endpoints** (Gateway endpoint for S3, Interface / PrivateLink for SQS).
    Keeps S3 and SQS traffic off the NAT and inside the VPC.
    [N3 routing, N4 DNS (private hosted zones), N13 endpoints, N12 egress]
23. **Security groups vs NACLs.** Stateful vs stateless; "allow 443 from the ALB
    security group only".
    [N6 stateful vs stateless, N5 ports, N1 CIDR]
24. **ALB vs NLB.** L7 path routing, SSE support, idle timeout. SSE streams drop
    unless the ALB idle timeout is raised above 60 s.
    [N9 load balancers, N10 long-lived connections, N8 keep-alive, N5 TCP]
25. **Sticky sessions.** Why the old in-memory `_jobs` design needed them and why the
    S3-backed design does not. Still relevant for the auth cookie if PostgreSQL returns.
    [N9 sticky sessions, N8 cookies]
26. **TLS termination.** At Caddy today, at the ALB with ACM certificates later.
    HSTS, renewal, TLS 1.2 minimum, end-to-end vs edge termination.
    [N7 TLS, N9 reverse proxy, N4 DNS validation]
27. **DNS with Route 53.** ALIAS to an ALB, TTLs during cutover, health-checked
    failover.
    [N4 DNS, N9 health checks]
28. **Timeout ordering.** Client → CloudFront/ALB → Caddy → uvicorn timeouts must be
    nested so the outer layer never cuts a request the inner one is still serving.
    [N14 timeouts, N8 idle timeouts, N10 long-lived connections]
29. **Egress control for the crawler.** The worker fetches arbitrary customer URLs:
    SSRF against the instance metadata address (`169.254.169.254`), IMDSv2, egress
    allow/deny lists, DNS rebinding.
    [N2 private ranges, N12 egress, N4 DNS, N3 routing]
30. **Rate limiting and connection caps.** WAF and ALB at the edge; the existing
    `KA11Y_*` caps in the app.
    [N5 connections, N8 HTTP 429, N9 X-Forwarded-For (real client IP)]
31. **CDN.** CloudFront in front of the Next.js UI and S3-served reports; cache keys,
    origin access control.
    [N4 DNS, N7 TLS, N8 cache headers, N11 latency]
32. **Stable outbound IP.** Elastic IP on the NAT Gateway so customers can allowlist
    the crawler.
    [N2 NAT, N12 egress]

## E. Observability

33. **Structured logging with correlation ids.** `job_id` on every line across API and
    worker; CloudWatch Logs Insights.
    [N13 endpoints (log shipping)]
34. **Metrics that matter.** Age of oldest message, worker slot utilisation, audit
    duration p50/p95, failure rate by `error_stage`, DLQ depth.
    [N11 latency vs throughput]
35. **Alarms.** DLQ > 0, oldest message age > N minutes, worker count 0, 5xx rate.
    [N8 status codes, N9 health checks]
36. **Distributed tracing.** OpenTelemetry spans from submit → worker → S3 write;
    the admin console Tracing tab consumes them.
    [N8 headers (trace propagation), N11 latency]

## F. Reliability patterns

37. **Timeouts, retries, exponential backoff with jitter.** boto3 retry modes
    (`standard`, `adaptive`); why unbounded retries amplify an outage.
    [N14 timeouts and retries, N5 TCP connect vs read]
38. **Circuit breaker.** Stop calling a failing dependency (Gemini, SQS) for a
    cooling-off period.
    [N14 retries, N13 endpoints]
39. **Bulkheads.** Isolating the crawler pool from the API; this migration already
    does it at the process level.
    [N9 (separate target groups), N1 (separate subnets)]
40. **Chaos basics.** Kill a worker mid-audit, block S3 (security group), fill the
    DLQ, and confirm the behaviour matches the concepts document.
    [N6 security groups, N15 signals, N14 timeouts]

## G. Cost

41. **Pricing shapes.** SQS per million requests (long polling cuts this), S3
    PUT/GET/LIST and storage tiers, NAT Gateway per GB, EC2 vs Fargate per vCPU-hour.
    [N12 egress, N11 bandwidth]
42. **Spot instances for workers.** Cheap, but must tolerate a 2-minute interruption
    notice; pairs naturally with at-least-once delivery.
    [N15 signals, N14 retries]

---

## Suggested order

1. Section 0 (N1–N15) until each line is obvious.
2. A1–A4 and D21–D25: they decide the production topology.
3. C15–C16 and B9–B11: they decide what can go wrong with data.
4. D26–D32, then E and F.
5. G last.
