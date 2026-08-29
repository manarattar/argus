import {
  Badge,
  Callout,
  Card,
  CardHeader,
  DefinitionRow,
  EmptyState,
  Mono,
  PageHeader,
} from '@/components/ui/primitives';
import { getArchitecture, getRuntime } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Settings' };

/**
 * Settings is read-only by design.
 *
 * Everything configurable lives in `.env`, which means the running
 * configuration is reproducible and reviewable. A UI that let a user change the
 * model backend at runtime would make "which configuration produced this
 * result?" unanswerable — exactly the question the Evaluation Lab depends on.
 */
export default async function SettingsPage() {
  const [runtime, architecture] = await Promise.all([getRuntime(), getArchitecture()]);

  if (!runtime) {
    return (
      <>
        <PageHeader eyebrow="Settings" title="Runtime configuration" />
        <EmptyState title="The API is not reachable" description="Start the backend and reload." />
      </>
    );
  }

  const demo = runtime.mode === 'demo';

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Runtime configuration"
        description="Read-only. Configuration lives in .env so that any result can be attributed to the exact setup that produced it."
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader
              title="Model backend"
              description={runtime.explanation}
              actions={
                <Badge tone={demo ? 'warn' : 'ok'}>{demo ? 'Demo mode' : 'Live inference'}</Badge>
              }
            />
            <dl className="mt-3">
              <DefinitionRow term="Mode">{runtime.headline}</DefinitionRow>
              <DefinitionRow term="Backend">
                <Mono>{runtime.backend}</Mono>
              </DefinitionRow>
              <DefinitionRow term="Model">
                <Mono>{runtime.model}</Mono>
              </DefinitionRow>
              {runtime.count !== undefined ? (
                <DefinitionRow term="Recordings available">{runtime.count}</DefinitionRow>
              ) : null}
            </dl>
          </Card>

          <Card>
            <CardHeader
              title="Retrieval"
              description="Which vectoriser is behind the search results, and what that means for them."
            />
            <dl className="mt-3">
              <DefinitionRow term="Provider">
                <Mono>{runtime.embedding.name}</Mono>
              </DefinitionRow>
              <DefinitionRow term="Kind">
                {runtime.embedding.semantic ? 'Semantic embeddings' : 'Lexical vectoriser'}
              </DefinitionRow>
              <DefinitionRow term="Dimensions">{runtime.embedding.dimensions}</DefinitionRow>
              <DefinitionRow term="Search strategy">
                Hybrid BM25 + vector, fused with reciprocal rank fusion
              </DefinitionRow>
            </dl>
            {runtime.embedding.caveat ? (
              <div className="mt-4">
                <Callout tone="warn" title="Retrieval limitation">
                  {runtime.embedding.caveat}
                </Callout>
              </div>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="Environment" />
            <dl className="mt-3">
              <DefinitionRow term="Environment">{runtime.environment}</DefinitionRow>
              <DefinitionRow term="Database">{runtime.database}</DefinitionRow>
              {architecture ? (
                <DefinitionRow term="Prompt library">
                  <Mono>v{architecture.prompts.library_version}</Mono>
                </DefinitionRow>
              ) : null}
            </dl>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Switching to live inference"
              description="One line in .env changes the whole system's behaviour."
            />
            <ol className="mt-3 space-y-2.5 text-2xs leading-relaxed text-ink-muted">
              <li>
                <span className="font-semibold text-ink">1.</span> Copy{' '}
                <Mono>.env.example</Mono> to <Mono>.env</Mono>.
              </li>
              <li>
                <span className="font-semibold text-ink">2.</span> Set{' '}
                <Mono>OPENAI_API_KEY</Mono> or <Mono>ANTHROPIC_API_KEY</Mono>.
              </li>
              <li>
                <span className="font-semibold text-ink">3.</span> Restart the API. The registry
                resolves the backend at startup and reports it here.
              </li>
              <li>
                <span className="font-semibold text-ink">4.</span> Confirm with{' '}
                <Mono>python -m scripts.doctor</Mono>, which prints the resolved configuration
                without revealing any secret.
              </li>
            </ol>
            <p className="mt-3 border-t border-line pt-3 text-2xs leading-relaxed text-ink-subtle">
              Setting a key also switches retrieval from the local lexical vectoriser to real
              embeddings, so re-run <Mono>make seed</Mono> to rebuild the index with comparable
              vectors.
            </p>
          </Card>

          <Card>
            <CardHeader
              title="What Demo Mode does and does not replay"
              description="The distinction matters for reading any number in this application."
            />
            <div className="mt-3 space-y-2.5 text-2xs leading-relaxed">
              <p className="text-ink-muted">
                <span className="font-semibold text-ink">Replayed: </span>
                text generation only. Responses were captured from a real model against these
                exact prompts, and carry their original model name, token counts and latency.
              </p>
              <p className="text-ink-muted">
                <span className="font-semibold text-ink">Executed normally: </span>
                chunking, retrieval, grounding verification, schema validation, cross-reference
                integrity, the uncertainty model, scoring, escalation rules and the whole
                evaluation harness.
              </p>
              <p className="text-ink-muted">
                A replayed response that cites evidence which does not exist is rejected by the
                same controls that would reject it live.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Data handling" />
            <p className="mt-2.5 text-2xs leading-relaxed text-ink-muted">
              Every document in this deployment is synthetic and was written for the
              demonstration. No real counterparty data is present, and the application is not
              affiliated with or endorsed by any financial institution.
            </p>
            <p className="mt-2 text-2xs leading-relaxed text-ink-subtle">
              Authentication is deliberately absent from this prototype.{' '}
              <Mono>docs/architecture/security.md</Mono> records exactly what would need to
              change before this ran anywhere real.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
