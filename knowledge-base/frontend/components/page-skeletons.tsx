export function TopicOverviewSkeleton() {
  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <div className="mb-8 space-y-3">
        <div className="skeleton h-4 w-48" />
        <div className="skeleton h-10 w-80" />
        <div className="skeleton h-4 w-full max-w-3xl" />
      </div>
      <section className="mb-6 grid gap-3 md:grid-cols-3">
        <div className="panel p-4"><div className="skeleton h-10 w-20" /></div>
        <div className="panel p-4"><div className="skeleton h-10 w-20" /></div>
        <div className="panel p-4"><div className="skeleton h-10 w-20" /></div>
      </section>
      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="panel space-y-3 p-5 md:p-6">
          <div className="skeleton h-6 w-32" />
          <div className="skeleton h-16 w-full" />
          <div className="skeleton h-16 w-full" />
          <div className="skeleton h-16 w-full" />
        </article>
        <article className="space-y-4">
          <div className="panel space-y-3 p-5">
            <div className="skeleton h-5 w-36" />
            <div className="skeleton h-14 w-full" />
            <div className="skeleton h-14 w-full" />
          </div>
          <div className="panel space-y-3 p-5">
            <div className="skeleton h-5 w-32" />
            <div className="skeleton h-12 w-full" />
          </div>
        </article>
      </section>
    </main>
  );
}

export function SkillWorkspaceSkeleton() {
  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <div className="mb-8 space-y-3">
        <div className="skeleton h-4 w-56" />
        <div className="skeleton h-10 w-72" />
      </div>
      <section className="grid gap-6 lg:grid-cols-[0.95fr_2fr]">
        <aside className="panel space-y-2 p-4">
          <div className="skeleton h-5 w-24" />
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
        </aside>
        <section className="panel p-5 md:p-6">
          <div className="mb-5 space-y-3 border-b border-black/10 pb-5">
            <div className="skeleton h-8 w-72" />
            <div className="skeleton h-4 w-full max-w-2xl" />
            <div className="flex gap-2">
              <div className="skeleton h-8 w-20" />
              <div className="skeleton h-8 w-20" />
              <div className="skeleton h-8 w-20" />
            </div>
          </div>
          <div className="space-y-3">
            <div className="skeleton h-20 w-full" />
            <div className="skeleton h-20 w-full" />
            <div className="skeleton h-20 w-full" />
          </div>
        </section>
      </section>
    </main>
  );
}

export function ChatWorkspaceSkeleton() {
  return (
    <main className="mx-auto max-w-6xl p-6 md:p-10">
      <div className="mb-8 space-y-3">
        <div className="skeleton h-4 w-56" />
        <div className="skeleton h-10 w-72" />
      </div>
      <section className="panel grid min-h-[70vh] gap-0 overflow-hidden lg:grid-cols-[0.85fr_2fr]">
        <aside className="border-b border-black/10 bg-white p-4 lg:border-b-0 lg:border-r">
          <div className="skeleton h-5 w-32" />
          <div className="mt-3 space-y-2">
            <div className="skeleton h-14 w-full" />
            <div className="skeleton h-14 w-full" />
            <div className="skeleton h-14 w-full" />
          </div>
        </aside>
        <article className="p-4 md:p-6">
          <div className="skeleton mb-3 h-14 w-full" />
          <div className="space-y-3 rounded-xl border border-black/10 bg-white p-4">
            <div className="skeleton h-14 w-2/3" />
            <div className="skeleton h-16 w-4/5" />
            <div className="skeleton h-14 w-1/2" />
          </div>
        </article>
      </section>
    </main>
  );
}

export function NotesWorkspaceSkeleton() {
  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <div className="mb-8 space-y-3">
        <div className="skeleton h-4 w-56" />
        <div className="skeleton h-10 w-72" />
      </div>
      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.25fr_0.95fr]">
        <article className="panel space-y-3 p-5">
          <div className="skeleton h-6 w-28" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
        </article>
        <article className="panel space-y-3 p-5">
          <div className="skeleton h-6 w-36" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-44 w-full" />
        </article>
        <article className="panel space-y-3 p-5">
          <div className="skeleton h-6 w-36" />
          <div className="skeleton h-12 w-full" />
          <div className="skeleton h-12 w-full" />
          <div className="skeleton h-12 w-full" />
        </article>
      </section>
    </main>
  );
}

export function TopicsDashboardSkeleton() {
  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <header className="mb-10 space-y-3">
        <div className="skeleton h-6 w-40" />
        <div className="skeleton h-10 w-64" />
        <div className="skeleton h-4 w-full max-w-2xl" />
      </header>
      <section className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
        <article className="panel space-y-3 p-6">
          <div className="skeleton h-6 w-40" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-24 w-full" />
          <div className="skeleton h-20 w-full" />
        </article>
        <article className="panel space-y-3 p-6">
          <div className="skeleton h-6 w-28" />
          <div className="skeleton h-16 w-full" />
          <div className="skeleton h-16 w-full" />
          <div className="skeleton h-16 w-full" />
        </article>
      </section>
    </main>
  );
}
