/**
 * src/components/Layout.jsx
 * App shell: top nav, user menu, page outlet.
 */
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { LayoutDashboard, FlaskConical, Radio, LogOut, Sliders, Grid3x3, BookOpen } from 'lucide-react';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItem = (to, label, Icon) => (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? 'bg-bull-700 text-white'
            : 'text-ink-100 hover:bg-ink-800 hover:text-white'
        }`
      }
    >
      <Icon size={16} />
      {label}
    </NavLink>
  );

  return (
    <div className="min-h-screen bg-ink-50 text-ink-900">
      <header className="bg-ink-900 text-white px-6 py-3 flex items-center justify-between shadow-md">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl font-bold tracking-tight">📈</span>
            <div className="leading-tight">
              <div className="font-bold text-base">Algo Trading System</div>
              <div className="text-[10px] text-ink-200 uppercase tracking-widest">
                Fitschen · DhanHQ · India
              </div>
            </div>
          </Link>
          <nav className="flex gap-2">
            {navItem('/', 'Dashboard', LayoutDashboard)}
            {navItem('/backtest', 'Backtest', FlaskConical)}
            {navItem('/tuning', 'Tuning', Sliders)}
            {navItem('/sweep', 'Sweep', Grid3x3)}
            {navItem('/journal', 'Journal', BookOpen)}
            {navItem('/live', 'Live', Radio)}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs">
            <div className="text-ink-200">Signed in</div>
            <div className="font-semibold">{user?.email || 'guest'}</div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 text-sm bg-bear-600 hover:bg-bear-700 text-white px-3 py-1.5 rounded-lg transition"
          >
            <LogOut size={14} /> Logout
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <Outlet />
      </main>

      <footer className="text-center text-xs text-ink-200 py-6">
        Algorithmic Trading System · NSE / NFO / MCX · For research use only
      </footer>
    </div>
  );
}
