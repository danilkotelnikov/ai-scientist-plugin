/**
 * Vedix application shell. Initial stub; the full router + page wiring
 * lands in Task 6. We keep this minimal so the dev server boots after
 * Task 1.
 */

export default function App(): JSX.Element {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-brand-900">Vedix</h1>
        <p className="text-gray-500">Loading…</p>
      </div>
    </div>
  );
}
