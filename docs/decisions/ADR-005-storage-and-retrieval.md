# ADR-005 — SQLite by default, PostgreSQL with pgvector for deployment

**Status** Accepted · **Date** 2026-08 · **Decides** storage and retrieval

## Context

Two requirements that pull in opposite directions.

A reviewer cloning this repository should have a working application in one
command, with no container runtime, no database server and no account. First-run
friction is the single biggest reason a portfolio project goes unexamined.

A deployed system needs a real database: concurrent writers, migrations, and
vector search that does not load every embedding into process memory.

## Decision

**SQLAlchemy 2 against both**, with `DATABASE_URL` the only difference.
SQLite is the default; `docker compose` sets PostgreSQL with pgvector. No
application code branches on the backend.

**Retrieval is hybrid**: BM25 plus vector similarity, fused with Reciprocal Rank
Fusion. The two have complementary failure modes — BM25 finds "62%" and
"CRF 4.2" reliably and fails on paraphrase; vectors bridge phrasing and return
topically adjacent but useless text. RRF combines *rankings*, so it needs no
per-corpus normalisation constant to tune.

**Embeddings are provider-abstracted.** With credentials, `text-embedding-3-small`.
Without, a local hashed lexical vectoriser that needs no network and no account.

**The index is in-memory per case.** A case is a few hundred chunks. Vectors are
computed once at ingest and reused, so building an index involves no model call.

## The honest part about the fallback

The local vectoriser is **not** a semantic model and is never described as one.
It hashes word unigrams, bigrams and character 4-grams into a fixed-width space
with sub-linear term weighting. That gives real lexical matching with some
tolerance for inflection — genuinely useful on a corpus this size, and measurably
so: retrieval evaluation passes 12/12 with it.

It does not know that "gearing" and "leverage" are related. That limitation is
stated in the Settings page, in the sidebar, and in every evaluation run's
recorded context. Presenting a lexical vectoriser as semantic search would be a
small lie that undermines everything else the project claims about honesty.

## Alternatives considered

**PostgreSQL only.** Cleaner architecturally; requires Docker before anything
works. Rejected on first-run experience.

**A dedicated vector database.** Justified at millions of vectors. Here it would
add a service, a client and an operational dependency to search a few hundred
chunks.

**Vector search only.** Simpler, and worse. Risk documents are full of exact
tokens — figures, clause references, entity names — where keyword matching is
strictly better.

**Requiring an embedding API key.** Would make retrieval semantic everywhere and
make the project unusable without an account. Rejected.

## Consequences

**Positive.** `make seed && make dev` works on a clean machine. Identical code
paths across backends. Retrieval quality is measured rather than assumed, and the
active provider is always visible.

**Negative.** An in-memory index does not scale past this shape of workload;
production would move vector search into pgvector, which is why the storage
column already exists. Two embedding providers mean two possible index states,
so chunks embedded by a different model are re-embedded in memory rather than
silently mixed.
