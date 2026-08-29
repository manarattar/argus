import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  Mono,
  PageHeader,
  SectionLabel,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { getArchitecture } from '@/lib/api';
import { titleCase } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Architecture' };

/**
 * The Architecture page is served from the running system rather than written
 * as static copy: capabilities, domains, prompt versions and controls are all
 * read from the modules that define them, so this page cannot drift out of step
 * with the code it describes.
 */
export default async function ArchitecturePage() {
  const data = await getArchitecture();

  if (!data) {
    return (
      <>
        <PageHeader eyebrow="Architecture" title="How ARGUS is built" />
        <EmptyState title="The API is not reachable" description="Start the backend and reload." />
      </>
    );
  }

  const implemented = data.domains.filter((d) => d.implemented);
  const design = data.domains.filter((d) => !d.implemented);

  return (
    <>
      <PageHeader
        eyebrow="Architecture"
        title="How ARGUS is built"
        description="Read from the running system, not written by hand. Every capability, domain, prompt version and control below is reported by the code that implements it."
      />

      <Card className="mb-5">
        <CardHeader
          title="Request path"
          description="A single investigation, from the analyst's click to the stored assessment."
        />
        <div className="mt-5 space-y-2">
          {data.layers.map((layer, index) => (
            <div key={layer.key} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line-strong bg-raised text-2xs font-semibold text-ink-muted">
                  {index + 1}
                </span>
                {index < data.layers.length - 1 ? (
                  <span className="my-0.5 w-px flex-1 bg-line" />
                ) : null}
              </div>
              <div className="min-w-0 flex-1 pb-3">
                <p className="text-xs font-semibold text-ink">{layer.name}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{layer.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Reusable capabilities"
            description="Domain-agnostic. None of these contains counterparty-review logic."
          />
          <div className="mt-4">
            <Table>
              <thead>
                <tr>
                  <Th>Capability</Th>
                  <Th>Prompt</Th>
                  <Th>Scope</Th>
                </tr>
              </thead>
              <tbody>
                {data.capabilities.map((capability) => (
                  <tr key={capability.key}>
                    <Td className="font-medium">{capability.name}</Td>
                    <Td>
                      {capability.prompt ? (
                        <Mono>{capability.prompt}</Mono>
                      ) : (
                        <span className="text-2xs text-ink-subtle">no model call</span>
                      )}
                    </Td>
                    <Td>
                      <Badge tone="muted">reusable</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          <p className="mt-3 text-2xs leading-relaxed text-ink-subtle">
            Scoring runs no model at all: it consolidates the agents&apos; ordinal judgements
            into a rating using arithmetic a risk committee could audit on paper.
          </p>
        </Card>

        <Card>
          <CardHeader
            title="Controls"
            description="What the system does not trust the model to get right on its own."
          />
          <ul className="mt-4 space-y-3">
            {data.controls.map((control) => (
              <li key={control.name} className="border-b border-line pb-3 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-ink">{control.name}</span>
                  <Badge
                    tone={
                      control.kind === 'deterministic'
                        ? 'ok'
                        : control.kind === 'control'
                          ? 'accent'
                          : 'warn'
                    }
                  >
                    {control.kind}
                  </Badge>
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-muted">{control.detail}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Platform vs domain"
          description="The claim that ARGUS is a platform is only credible if the seam is visible. It is: one domain is built, three are scoped and labelled as such."
        />

        <div className="mt-5">
          <SectionLabel>Implemented</SectionLabel>
          <div className="grid gap-3 md:grid-cols-2">
            {implemented.map((domain) => (
              <div key={domain.key} className="rounded border border-low/30 bg-low/5 px-4 py-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-ink">{domain.name}</span>
                  <Badge tone="ok">built and running</Badge>
                </div>
                <p className="mt-1.5 text-2xs leading-relaxed text-ink-muted">
                  {domain.description}
                </p>
                <div className="mt-2.5 flex flex-wrap gap-1">
                  {domain.risk_categories.map((category) => (
                    <span
                      key={category}
                      className="rounded bg-raised px-1.5 py-0.5 text-2xs text-ink-muted"
                    >
                      {titleCase(category)}
                    </span>
                  ))}
                </div>
                <p className="mt-2.5 text-2xs text-ink-subtle">
                  {domain.expected_evidence.length} expected evidence categories ·{' '}
                  {domain.escalation_rules.length} escalation rules ·{' '}
                  {domain.policy_library.length} policy documents
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6">
          <SectionLabel>Design-stage extensions</SectionLabel>
          <p className="mb-3 text-2xs leading-relaxed text-ink-muted">
            These are scoped, not built. They appear here to show where the seam is — a new
            review type is a configuration plus a policy library, not a fork of the pipeline —
            and they are labelled so nobody mistakes them for finished functionality.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            {design.map((domain) => (
              <div
                key={domain.key}
                className="rounded border border-dashed border-line px-4 py-3.5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-ink-muted">{domain.name}</span>
                  <Badge tone="muted">design only</Badge>
                </div>
                <p className="mt-1.5 text-2xs leading-relaxed text-ink-subtle">
                  {domain.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Prompt library"
            description={`Version ${data.prompts.library_version}. Every prompt is versioned and its reference is recorded on each step, so an evaluation result can be attributed to an exact instruction set.`}
          />
          <div className="mt-4">
            <Table>
              <thead>
                <tr>
                  <Th>Prompt</Th>
                  <Th>Version</Th>
                </tr>
              </thead>
              <tbody>
                {data.prompts.prompts.map((prompt) => (
                  <tr key={prompt.id}>
                    <Td>
                      <Mono>{prompt.id}</Mono>
                    </Td>
                    <Td className="tabular text-ink-muted">{prompt.version}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Current runtime"
            description="What is actually executing behind this deployment."
          />
          <dl className="mt-4 space-y-2.5 text-xs">
            <Row label="Mode" value={data.runtime.mode === 'demo' ? 'Demo (replayed)' : 'Live'} />
            <Row label="Model" value={data.runtime.model} />
            <Row label="Backend" value={data.runtime.backend} />
            <Row label="Embeddings" value={data.runtime.embedding.description} />
            <Row label="Database" value={data.runtime.database} />
            <Row label="Steps executed" value={String(data.operations.steps)} />
            <Row label="Investigations" value={String(data.operations.investigations)} />
          </dl>
          {data.runtime.embedding.caveat ? (
            <p className="mt-3 rounded border border-moderate/30 bg-moderate/5 px-3 py-2 text-2xs leading-relaxed text-ink-muted">
              {data.runtime.embedding.caveat}
            </p>
          ) : null}
        </Card>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line pb-2 last:border-0 last:pb-0">
      <dt className="shrink-0 text-ink-muted">{label}</dt>
      <dd className="truncate text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
