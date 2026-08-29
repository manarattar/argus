# Security

Two parts: what this prototype does, and what would have to change before it ran
anywhere real. The second part is longer, which is the honest ratio.

---

## Part 1 — Implemented

### Secrets

No credentials in the repository. `.env` is git-ignored; `.env.example` carries
placeholders. `scripts/doctor.py` reports whether a key is configured and its
length, never its value. Nothing logs a key or a prompt containing one.

### Input handling

- Request bodies bounded by `MAX_UPLOAD_BYTES` (5 MB default), rejected with 413
  before parsing.
- Every payload validated by a Pydantic model; unknown fields rejected.
- Question length, comment length and rationale length bounded at the schema, so
  a UI bug cannot bypass them.
- Upload suffixes constrained by configuration.
- Enum-typed fields reject unknown values with 422.

### Database

SQLAlchemy ORM throughout with parameterised queries. No string-built SQL. IDs
are opaque hex, not sequential integers.

### HTTP

- CORS restricted to configured origins; credentials disabled; methods limited.
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Cross-Origin-Opener-Policy`, `Permissions-Policy` set on every response.
- Every response carries a request id, echoed from `X-Request-ID` where supplied.

### Error handling

Unhandled exceptions return an opaque message plus the request id. Stack traces
and internal messages go to the log, never to the client. Domain errors return
specific, safe messages — a refused approval explains *why*, because that is
useful and discloses nothing.

### Untrusted content

Document text is delimited and labelled as data in every prompt. Attempts to
close the boundary tag early are escaped. The report renderer handles a fixed
Markdown subset and cannot render raw HTML from the corpus.

### Supply chain

All Python and Node dependencies pinned to exact versions. Containers run as
non-root with multi-stage builds.

---

## Part 2 — Required before production

Ordered by how much would have to change.

### Authentication and authorisation — **absent**

There is none. Every request is anonymous and the actor is a string in the
payload.

Required: SSO integration; per-request identity replacing `actor` strings;
role-based access (analyst, reviewer, product owner, engineer); enforcement that
a reviewer cannot approve their own assessment; case-level access control.

The application is structured for this — every service function already takes an
`actor` — but it is trusted input today.

### Tenancy — **absent**

No tenant boundary. Every case is visible to everyone. Required: tenant on every
table, enforced at the query layer, ideally with row-level security.

### Encryption

At rest: currently unencrypted SQLite. Required: encrypted volumes or
column-level encryption for case content.

In transit: currently HTTP locally. Required: TLS everywhere, including to the
model provider, with certificate pinning where policy demands.

### Secret management

Currently `.env`. Required: a managed secret store with rotation, short-lived
credentials, and no secret on disk in the container.

### Data classification and PII

Currently: all data synthetic, no classification step.

Required before any real document is processed:
- classification before submission to any external model;
- PII detection and redaction;
- provider agreements with no-training and no-retention guarantees;
- a self-hosted inference option for the highest classification;
- egress control so document content cannot reach an unapproved endpoint.

### Retention

Currently unbounded. Required: retention policy for case documents, prompts,
recordings and audit entries; deletion workflow honouring legal hold; documented
lawful basis.

### Audit immutability

Currently enforced by having written no update or delete code. Adequate for a
prototype, insufficient for production.

Required: database-level enforcement — revoked UPDATE/DELETE grants on the audit
table, append-only storage, or hash chaining. Application-level discipline is not
a control against a compromised application.

### Rate limiting

Currently none on model-backed endpoints. Required: per-user and per-tenant
limits on investigation, ask and challenge, since each triggers billable
inference. `slowapi` is already a dependency for this purpose.

### Recordings

`data/recordings/` contains model responses over synthetic documents and is safe
to commit here. In production, recordings would contain real case content and
must be treated as case data — encrypted, access-controlled, retention-limited —
or disabled entirely.

### Monitoring

Currently application logs and in-app metrics. Required: centralised logging,
alerting on failure and cost anomalies, and audit-trail integrity monitoring.

---

## Threat notes

**Prompt injection** is treated as a first-class threat rather than a curiosity;
see MR-3 in the model risk assessment. The relevant property is that a successful
injection against the generation step still cannot create grounded evidence,
resolve a fabricated citation, or move the computed rating.

**Model output as attack vector.** Output is never executed, never used to build
SQL, and never rendered as raw HTML. The report renderer handles a fixed
Markdown subset by design.

**Cost as an attack surface.** Without rate limiting, an authenticated user could
drive spend through repeated investigations. Noted above as required work.

---

## Summary

| Area | Prototype | Production gap |
|---|---|---|
| Secrets in repo | None | Managed store, rotation |
| Input validation | Complete | — |
| SQL injection | Not applicable | — |
| Security headers | Set | CSP for the frontend |
| Error disclosure | Safe | — |
| Authentication | **Absent** | SSO, RBAC, segregation of duties |
| Tenancy | **Absent** | Tenant isolation |
| Encryption | Local only | At rest and in transit |
| PII handling | Synthetic data only | Classification, redaction, egress control |
| Retention | **Unbounded** | Policy and deletion workflow |
| Audit immutability | Code-enforced | Database-enforced |
| Rate limiting | **Absent** | Per-user and per-tenant |
