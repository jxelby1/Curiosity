export default function Loading() {
  return (
    <main className="mx-auto flex min-h-[72vh] max-w-4xl items-center p-6 md:p-10">
      <section className="panel w-full p-6 md:p-8">
        <div className="skeleton mb-3 h-6 w-36" />
        <div className="skeleton mb-2 h-10 w-80" />
        <div className="skeleton mb-6 h-4 w-full max-w-xl" />
        <div className="skeleton mb-4 h-2.5 w-full" />
        <div className="space-y-2">
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-10 w-full" />
        </div>
      </section>
    </main>
  );
}
