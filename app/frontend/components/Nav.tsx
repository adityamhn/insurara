import Link from "next/link";

export function Nav() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-slate-900">
          <span className="inline-block h-5 w-5 rounded bg-blue-600" aria-hidden />
          Claims Processing
        </Link>
        <nav className="flex items-center gap-5 text-sm">
          <Link href="/" className="text-slate-600 hover:text-slate-900">
            Claims
          </Link>
          <Link href="/policies" className="text-slate-600 hover:text-slate-900">
            Policies
          </Link>
          <Link
            href="/claims/new"
            className="rounded-md bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700"
          >
            New claim
          </Link>
        </nav>
      </div>
    </header>
  );
}
