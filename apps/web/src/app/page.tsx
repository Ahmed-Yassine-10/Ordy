import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6">
      <div>
        <p className="text-sm font-medium uppercase tracking-widest text-ordy-accent">Ordy</p>
        <h1 className="mt-2 text-4xl font-bold sm:text-5xl">
          The AI waiter that understands, talks, and takes action.
        </h1>
        <p className="mt-4 max-w-xl text-zinc-500 dark:text-zinc-400">
          Connect your website, menu, or POS. Ordy learns your restaurant and holds real
          voice conversations — ordering, reservations, and support — in English, French,
          and Tunisian Derja.
        </p>
      </div>
      <div className="flex gap-3">
        <Link
          href="/login"
          className="rounded-lg bg-ordy-accent px-5 py-2.5 font-medium text-white hover:opacity-90"
        >
          Sign in
        </Link>
        <a
          href="https://github.com/Ahmed-Yassine-10/Ordy"
          className="rounded-lg border border-zinc-300 px-5 py-2.5 font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          Documentation
        </a>
      </div>
      <p className="text-xs text-zinc-400">
        Phase 2 — dashboard foundation. Architecture: <code>/docs</code>.
      </p>
    </main>
  );
}
