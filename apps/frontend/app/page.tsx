import Link from "next/link";

const softwareApplicationJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "OpsDeck",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  url: "https://www.opsdeck.in",
  description:
    "OpsDeck is a continuity intelligence layer for industrial operations that helps teams detect supplier disruption, inventory exposure, production continuity risk, and operational risk before disruption impacts production.",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
    availability: "https://schema.org/InStock",
  },
  publisher: {
    "@type": "Organization",
    name: "OpsDeck",
    url: "https://www.opsdeck.in",
  },
};

const organizationJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "OpsDeck",
  url: "https://www.opsdeck.in",
  description:
    "OpsDeck provides continuity intelligence for industrial operations.",
};

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(softwareApplicationJsonLd),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(organizationJsonLd),
        }}
      />

      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-6 py-16 sm:px-8">
        <div className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-200">
            OpsDeck
          </p>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-6xl">
            Continuity Intelligence for Industrial Operations
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            OpsDeck helps industrial teams understand whether operations can continue
            without disruption by connecting supplier disruption signals, inventory
            exposure, inbound dependency changes, production continuity pressure, and
            operational risk into one trust-aware view.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950"
            >
              Sign in
            </Link>
            <a
              href="mailto:hello@opsdeck.in"
              className="rounded-xl border border-white/20 px-5 py-3 text-sm font-semibold text-white"
            >
              Contact OpsDeck
            </a>
          </div>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {[
            {
              title: "Detect degradation",
              body: "Identify continuity exposure as stock cover, inbound movement, or source freshness starts to weaken.",
            },
            {
              title: "Explain causality",
              body: "Show why an exposure formed using deterministic operational signals instead of dashboard noise.",
            },
            {
              title: "Trust the signal",
              body: "Surface confidence, freshness, and visibility degradation before teams depend on stale data.",
            },
          ].map((item) => (
            <article
              key={item.title}
              className="rounded-2xl bg-white/8 p-5 ring-1 ring-white/10"
            >
              <h2 className="text-base font-semibold">{item.title}</h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
