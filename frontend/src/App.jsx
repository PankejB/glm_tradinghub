/**
 * App.jsx — Root component (Step 1 placeholder).
 * Will be expanded with real routes & layout in Step 6.
 */
import { Routes, Route, Link } from 'react-router-dom';

export default function App() {
  return (
    <div className="min-h-screen bg-ink-50 text-ink-900">
      <header className="bg-ink-900 text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold tracking-tight">📈 Algo Trading System</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-bull-700 text-bull-50">
            Fitschen · DhanHQ
          </span>
        </div>
        <nav className="flex gap-4 text-sm">
          <Link to="/" className="hover:text-bull-400">Dashboard</Link>
          <Link to="/backtest" className="hover:text-bull-400">Backtest</Link>
          <Link to="/live" className="hover:text-bull-400">Live Trading</Link>
        </nav>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        <Routes>
          <Route path="/" element={<PlaceholderPage title="Dashboard" step={6} />} />
          <Route path="/backtest" element={<PlaceholderPage title="Backtest" step={6} />} />
          <Route path="/live" element={<PlaceholderPage title="Live Trading" step={6} />} />
        </Routes>
      </main>

      <footer className="text-center text-xs text-ink-200 py-6">
        Step 1 of 7 · Monorepo scaffold complete · Backend &amp; frontend will be wired in subsequent steps
      </footer>
    </div>
  );
}

function PlaceholderPage({ title, step }) {
  return (
    <div className="bg-white rounded-xl shadow p-10">
      <h1 className="text-3xl font-bold mb-2">{title}</h1>
      <p className="text-ink-700 mb-6">
        This page is reserved and will be implemented in <strong>Step {step}</strong>.
      </p>
      <div className="border border-dashed border-ink-200 rounded-lg p-6 bg-ink-50">
        <p className="font-mono text-sm text-ink-700">
          // TODO: implement {title} page with Recharts, React Query, and Tailwind UI
        </p>
      </div>
    </div>
  );
}
