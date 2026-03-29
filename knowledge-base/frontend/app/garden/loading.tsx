export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <div className="mb-8 space-y-3">
        <div className="skeleton h-6 w-40" />
        <div className="skeleton h-10 w-72" />
        <div className="skeleton h-4 w-full max-w-2xl" />
      </div>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="panel p-4">
            <div className="skeleton h-5 w-40" />
            <div className="skeleton mx-auto mt-3 h-28 w-28" />
            <div className="skeleton mt-3 h-4 w-24" />
          </div>
        ))}
      </section>
    </main>
  );
}
