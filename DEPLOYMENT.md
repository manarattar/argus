# Deploying ARGUS

**Live at `argus.manarattar.com`.**

## Where this runs

The same Contabo VPS as every other manarattar.com app. No Vercel, Render or
other PaaS is involved.

| | |
|---|---|
| Server | `194.163.176.183` — `ssh ubuntu@194.163.176.183` (key only) |
| Stack | `/srv/stack/docker-compose.yml` + `/srv/stack/Caddyfile` |
| App source | `/srv/apps/argus` |
| Containers | `argus` (API) and `argus-web` (Next.js) |
| Data | `argus_data` volume, mounted at `/app/data` |
| TLS | Caddy, automatic Let's Encrypt |

## How it differs from the other apps

The other apps ship a static SPA that Caddy serves from `/srv/www/<name>`, with
`/api/*` proxied to a single backend container. ARGUS cannot do that: the
frontend is Next.js with Server Components, so it needs a running Node process
rather than a directory of files.

So ARGUS is **two containers**, and Caddy splits the host between them:

```
argus.manarattar.com
  ├── /api/*  ->  argus:8000        (FastAPI)
  └── /*      ->  argus-web:3000    (Next.js)
```

The API is not published to the internet on its own hostname. It is reachable
only on the internal Docker network and through that `/api/*` route.

## Demo Mode, deliberately

The deployment runs with **no model API key**. `MODEL_BACKEND=replay` serves the
recorded responses in `data/recordings`, and `EMBEDDING_PROVIDER=local` uses the
lexical vectoriser.

That is a security decision, not a cost-saving one. There is no authentication
in front of this. With a live key, any visitor could trigger inference on the
account paying for it, and the rate limiter bounds one address rather than a
determined caller. Demo Mode removes the surface instead of trying to police it.

Everything except text generation still executes: chunking, retrieval, grounding
verification, schema validation, citation integrity, scoring, escalation and the
full 53-case evaluation suite.

## SQLite rather than the shared Postgres

The other backends each get a database on the shared `postgres` container. ARGUS
uses SQLite in the `argus_data` volume instead, because the container reseeds
itself on boot when the database is empty, so nothing here needs to survive a
rebuild. It is a demonstration, not a system of record. Using the shared
Postgres would mean managing a database and credentials for state that is
regenerated in seconds anyway.

The code supports Postgres unchanged — set `DATABASE_URL` and it uses it.

## Deploying a change

```bash
cd /path/to/argus
tar czf - --exclude=.git --exclude=.venv --exclude=node_modules \
          --exclude=.next --exclude=data/argus.db --exclude=.env \
          --exclude=__pycache__ . \
  | ssh ubuntu@194.163.176.183 'rm -rf /srv/apps/argus && mkdir -p /srv/apps/argus && tar xzf - -C /srv/apps/argus'
ssh ubuntu@194.163.176.183 'cd /srv/stack && sudo docker compose up -d --build argus argus-web'
```

Rebuilding takes a few minutes because the Next.js build runs in the image.

## Things that will catch you out

- **The frontend resolves the API at runtime, not at build time.** An earlier
  version read `NEXT_PUBLIC_API_BASE_URL`, which Next inlines into the client
  bundle during the build, so the backend address was frozen into the image. A
  `next.config` rewrite has the same problem — Next resolves rewrites at build
  time and writes them into `routes-manifest.json`. It is now a Route Handler at
  `app/api/[...path]`, which reads `API_BASE_URL` per request. In this
  deployment Caddy intercepts `/api/*` before Next sees it, so that handler only
  matters locally — but it is what lets the image be built without knowing where
  the API lives.
- **The container seeds itself on boot** if the database has no cases, and skips
  seeding when it does. Delete the `argus_data` volume to force a fresh demo.
- **Migrations run before the server starts.** A schema change needs a revision
  (`make revision m="..."`), or `alembic check` fails the build.
- **Recordings are prompt-fingerprinted.** Changing any prompt invalidates them
  and Demo Mode will report missing recordings rather than inventing output.
  Re-record with a key set: `make record`.
- **Demo Mode needs recordings made on the keyless path.** Fixtures captured
  with semantic embeddings do not match what the lexical vectoriser retrieves,
  so the prompt differs and the cache misses. Record with
  `EMBEDDING_PROVIDER=local`.

## Rolling back

Rebuild from the previous commit and redeploy. There is no separate state to
restore: the demonstration data is regenerated on boot.
