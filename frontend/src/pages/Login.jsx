/**
 * src/pages/Login.jsx
 * Login + register form.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Login() {
  const { login, register, loading, error } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('admin@trading.dev');
  const [password, setPassword] = useState('admin123');
  const [fullName, setFullName] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register({ email, full_name: fullName || email.split('@')[0], password });
      }
      navigate('/');
    } catch {
      /* error already in store */
    }
  };

  return (
    <div className="min-h-screen bg-ink-900 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">📈</div>
          <h1 className="text-2xl font-bold text-ink-900">Algo Trading System</h1>
          <p className="text-sm text-ink-200 mt-1">
            Fitschen · DhanHQ · Indian Markets
          </p>
        </div>

        <div className="flex border border-ink-200 rounded-lg overflow-hidden mb-6 text-sm font-medium">
          <button
            type="button"
            onClick={() => setMode('login')}
            className={`flex-1 py-2 ${mode === 'login' ? 'bg-ink-900 text-white' : 'bg-white text-ink-700'}`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode('register')}
            className={`flex-1 py-2 ${mode === 'register' ? 'bg-ink-900 text-white' : 'bg-white text-ink-700'}`}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Trader Name"
                className="w-full px-3 py-2 border border-ink-200 rounded-lg focus:ring-2 focus:ring-bull-500 focus:border-bull-500 outline-none"
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 border border-ink-200 rounded-lg focus:ring-2 focus:ring-bull-500 focus:border-bull-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-ink-200 rounded-lg focus:ring-2 focus:ring-bull-500 focus:border-bull-500 outline-none"
            />
          </div>

          {error && (
            <div className="text-sm text-bear-700 bg-bear-50 border border-bear-100 rounded-lg p-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-bull-600 hover:bg-bull-700 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-50"
          >
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <p className="text-xs text-ink-200 mt-4 text-center">
          Default admin: <code className="font-mono">admin@trading.dev / admin123</code>
        </p>
      </div>
    </div>
  );
}
