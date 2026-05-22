import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Dashboard } from "./pages/Dashboard";
import { NewJob } from "./pages/NewJob";
import { JobDetail } from "./pages/JobDetail";
import { ProvidersPage } from "./pages/Providers";
import { CostLedgerPage } from "./pages/CostLedger";
import { CollabEditor } from "./pages/CollabEditor";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      // Sensible defaults: short freshness, single retry, no refetch on
      // window focus (gets noisy for long-running research jobs).
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App(): JSX.Element {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="min-h-screen flex flex-col">
          <NavBar />
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/jobs/new" element={<NewJob />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/providers" element={<ProvidersPage />} />
              <Route path="/cost" element={<CostLedgerPage />} />
              <Route path="/collab/:docId" element={<CollabEditor />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          <Footer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function NavBar(): JSX.Element {
  const linkClass = ({ isActive }: { isActive: boolean }): string =>
    `px-3 py-1 rounded ${
      isActive ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:text-gray-900"
    }`;

  return (
    <nav className="border-b border-gray-200 bg-white sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
        <Link to="/" className="font-bold text-brand-900 text-lg">
          Vedix
        </Link>
        <NavLink to="/jobs/new" className={linkClass}>
          New job
        </NavLink>
        <NavLink to="/providers" className={linkClass}>
          Providers
        </NavLink>
        <NavLink to="/cost" className={linkClass}>
          Cost
        </NavLink>
      </div>
    </nav>
  );
}

function Footer(): JSX.Element {
  return (
    <footer className="border-t border-gray-200 bg-white text-center text-xs text-gray-400 py-3">
      Vedix v3.0
    </footer>
  );
}

function NotFound(): JSX.Element {
  return (
    <div className="p-12 text-center">
      <h2 className="text-xl font-semibold mb-2">Not found</h2>
      <p className="text-gray-500">
        <Link to="/" className="underline">
          Back to dashboard
        </Link>
      </p>
    </div>
  );
}
