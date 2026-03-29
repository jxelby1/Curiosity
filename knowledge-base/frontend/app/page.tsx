import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_20%_20%,rgba(47,108,255,0.12),transparent_42%),radial-gradient(circle_at_80%_10%,rgba(40,160,110,0.12),transparent_38%),linear-gradient(180deg,#f7f8f5_0%,#f3f5f1_60%,#edf1ef_100%)]">
      <div className="mx-auto w-full max-w-7xl px-6 pb-16 pt-10 md:px-10 md:pt-14">
        <header className="mb-14 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/65">Knowledge Base</p>
          <div className="flex items-center gap-2">
            <Link href="/login" className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
              Sign in
            </Link>
            <Link href="/signup" className="rounded-md bg-ink px-3 py-2 text-sm text-white">
              Create account
            </Link>
          </div>
        </header>

        <section className="grid items-center gap-10 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <p className="badge mb-4">Adaptive learning system</p>
            <h1 className="text-4xl font-semibold leading-[1.08] text-black md:text-5xl">
              Build a living learning tree, not a static course.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-black/70 md:text-lg">
              Start with a strong core path, branch into what you care about, and track meaningful progress through
              lessons, exercises, assessments, and your project journal.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="/login" className="rounded-lg bg-ink px-5 py-3 text-sm font-medium text-white">
                Continue to your workspace
              </Link>
              <Link href="/signup" className="rounded-lg border border-black/20 bg-white px-5 py-3 text-sm">
                Start free
              </Link>
            </div>
          </div>

          <article className="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-[0_18px_40px_-30px_rgba(10,20,30,0.4)] backdrop-blur-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/60">What feels different</h2>
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-black/10 bg-paper/80 p-3">
                <p className="text-sm font-semibold">Branching mastery map</p>
                <p className="mt-1 text-xs text-black/65">
                  A core trunk with optional side paths for curiosity, remediation, and specialization.
                </p>
              </div>
              <div className="rounded-lg border border-black/10 bg-paper/80 p-3">
                <p className="text-sm font-semibold">Fair assessment pipeline</p>
                <p className="mt-1 text-xs text-black/65">
                  Assessments are grounded in what has already been taught in lessons and examples.
                </p>
              </div>
              <div className="rounded-lg border border-black/10 bg-paper/80 p-3">
                <p className="text-sm font-semibold">Project journal + artifacts</p>
                <p className="mt-1 text-xs text-black/65">
                  Capture notes, completed exercises, uploaded proof, milestones, and progress history in one place.
                </p>
              </div>
            </div>
          </article>
        </section>

        <section className="mt-12 grid gap-4 md:grid-cols-3">
          <article className="rounded-xl border border-black/10 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.12em] text-black/55">Simple first start</p>
            <p className="mt-2 text-sm text-black/75">
              Start with just a topic and goal. Advanced controls are available when you want finer tuning.
            </p>
          </article>
          <article className="rounded-xl border border-black/10 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.12em] text-black/55">Guided momentum</p>
            <p className="mt-2 text-sm text-black/75">
              Always know your next step through focused actions, unlock anticipation, and milestone feedback.
            </p>
          </article>
          <article className="rounded-xl border border-black/10 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.12em] text-black/55">Garden progression</p>
            <p className="mt-2 text-sm text-black/75">
              Watch each topic tree evolve into a calm visual garden that reflects real progress.
            </p>
          </article>
        </section>
      </div>
    </main>
  );
}
