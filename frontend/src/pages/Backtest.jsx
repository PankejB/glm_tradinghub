/**
 * src/pages/Backtest.jsx
 * Form to launch a backtest + live status + results.
 */
import { useEffect, useState } from 'react';
import { useStrategies, useStartBacktest, useBacktestStatus, useBacktestResults } from '../hooks/useQueries';
import EquityCurveChart from '../components/EquityCurveChart';
import StatCard from '../components/StatCard';
import TradeTable from '../components/TradeTable';

const DEFAULT_SYMBOLS = {
  stock_counter_trend:   { symbol: 'RELIANCE',  security_id: '2885',  segment: 'NSE_EQ' },
  mcx_trend_following:   { symbol: 'GOLD',       security_id: '2236',  segment: 'MCX' },
  index_bar_scoring:     { symbol: 'NIFTY 50',   security_id: '13',    segment: 'NSE_FNO' },
};

export default function Backtest() {
  const { data: strategies } = useStrategies();
  const startBacktest = useStartBacktest();
  const [taskId, setTaskId] = useState(null);
  const { data: status } = useBacktestStatus(taskId);
  const { data: recentResults } = useBacktestResults(10);

  const [form, setForm] = useState({
    strategy_id: '',
    segment: 'NSE_EQ',
    security_id: '2885',
    symbol: 'RELIANCE',
    start_date: '',
    end_date: '',
    initial_capital: 1_000_000,
    parameters: '{}',
  });

  // When strategy changes, fill in defaults
  useEffect(() => {
    if (!strategies?.length) return;
    if (!form.strategy_id) setForm((f) => ({ ...f, strategy_id: strategies[0].id }));
  }, [strategies, form.strategy_id]);

  const onStrategyChange = (id) => {
    const strat = strategies?.find((s) => s.id === Number(id));
    const defaults = DEFAULT_SYMBOLS[strat?.strategy_type] || {};
    setForm((f) => ({
      ...f,
      strategy_id: id,
      segment: defaults.segment || f.segment,
      security_id: defaults.security_id || f.security_id,
      symbol: defaults.symbol || f.symbol,
      parameters: strat ? JSON.stringify(strat.parameters, null, 2) : '{}',
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    let params = {};
    try { params = JSON.parse(form.parameters || '{}'); } catch { /* ignore */ }
    const payload = {
      strategy_id: Number(form.strategy_id),
      segment: form.segment,
      security_id: form.security_id,
      symbol: form.symbol,
      start_date: new Date(form.start_date || Date.now() - 365 * 86400000).toISOString(),
      end_date: new Date(form.end_date || Date.now()).toISOString(),
      initial_capital: Number(form.initial_capital),
      parameters: params,
    };
    const res = await startBacktest.mutateAsync(payload);
    setTaskId(res.task_id);
  };

  const isRunning = status?.status === 'pending' || status?.status === 'running';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Backtest</h1>
        <p className="text-sm text-ink-200">Run a Fitschen strategy over historical data · GtP &gt; 1.5 = tradeable</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form */}
        <form onSubmit={handleSubmit} className="lg:col-span-1 bg-white rounded-xl border border-ink-200 p-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Strategy</label>
            <select
              value={form.strategy_id}
              onChange={(e) => onStrategyChange(e.target.value)}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
            >
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">Segment</label>
              <select
                value={form.segment}
                onChange={(e) => setForm({ ...form, segment: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              >
                <option value="NSE_EQ">NSE Equity</option>
                <option value="NSE_FNO">NSE F&amp;O</option>
                <option value="MCX">MCX</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">Symbol</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Security ID (DhanHQ)</label>
            <input
              type="text"
              value={form.security_id}
              onChange={(e) => setForm({ ...form, security_id: e.target.value })}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">Start Date</label>
              <input
                type="date"
                value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">End Date</label>
              <input
                type="date"
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Initial Capital (₹)</label>
            <input
              type="number"
              value={form.initial_capital}
              onChange={(e) => setForm({ ...form, initial_capital: e.target.value })}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Parameters (JSON override)</label>
            <textarea
              value={form.parameters}
              onChange={(e) => setForm({ ...form, parameters: e.target.value })}
              rows={6}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-xs font-mono"
            />
          </div>

          <button
            type="submit"
            disabled={startBacktest.isPending}
            className="w-full bg-ink-900 hover:bg-ink-800 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-50"
          >
            {startBacktest.isPending ? 'Dispatching…' : 'Run Backtest'}
          </button>
        </form>

        {/* Status / Result */}
        <div className="lg:col-span-2 space-y-6">
          {!taskId && (
            <div className="bg-white rounded-xl border border-dashed border-ink-200 p-10 text-center text-ink-200">
              Submit the form to start a backtest. Results will appear here.
            </div>
          )}

          {taskId && (
            <div className="bg-white rounded-xl border border-ink-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-bold">Task Status</h2>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                  status?.status === 'completed' ? 'bg-bull-100 text-bull-700' :
                  status?.status === 'failed' ? 'bg-bear-100 text-bear-700' :
                  'bg-ink-100 text-ink-700'
                }`}>
                  {status?.status?.toUpperCase() || 'UNKNOWN'}
                </span>
              </div>
              <div className="text-xs text-ink-200 font-mono break-all">Task ID: {taskId}</div>
              {status?.error_message && (
                <div className="mt-2 text-sm text-bear-700 bg-bear-50 p-3 rounded-lg">
                  {status.error_message}
                </div>
              )}
            </div>
          )}

          {status?.status === 'completed' && (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <StatCard label="Net Profit" value={`₹${Number(status.net_profit || 0).toLocaleString('en-IN')}`}
                  tone={Number(status.net_profit) >= 0 ? 'bull' : 'bear'} />
                <StatCard label="Net Profit %" value={`${Number(status.net_profit_pct || 0).toFixed(2)}%`}
                  tone={Number(status.net_profit_pct) >= 0 ? 'bull' : 'bear'} />
                <StatCard label="Total Trades" value={status.total_trades || 0} />
                <StatCard label="Win Rate" value={`${Number(status.win_rate || 0).toFixed(1)}%`} />
                <StatCard label="Max Drawdown" value={`${Number(status.max_drawdown_pct || 0).toFixed(2)}%`} tone="bear" />
                <StatCard label="Avg Annual Return" value={`${Number(status.avg_annual_return || 0).toFixed(2)}%`} tone="bull" />
                <StatCard label="GtP Ratio" value={Number(status.gtp_ratio || 0).toFixed(2)}
                  tone={status.gtp_ratio > 1.5 ? 'bull' : 'bear'} />
                <StatCard label="Tradeable" value={status.is_tradeable ? 'YES' : 'NO'}
                  tone={status.is_tradeable ? 'bull' : 'bear'} />
              </div>

              <div className="bg-white rounded-xl border border-ink-200 p-5">
                <h3 className="font-bold mb-3">Equity Curve</h3>
                <EquityCurveChart
                  data={status.equity_curve_json || []}
                  initialCapital={Number(status.initial_capital || 1_000_000)}
                  showDrawdown
                  height={320}
                />
              </div>

              <div>
                <h3 className="font-bold mb-3">Trades ({status.trades_json?.length || 0})</h3>
                <TradeTable trades={status.trades_json || []} mode="score" />
              </div>
            </>
          )}

          {isRunning && (
            <div className="bg-ink-50 rounded-xl border border-ink-200 p-6 text-center text-ink-700 text-sm animate-pulse">
              Backtest running… polling every 2s
            </div>
          )}
        </div>
      </div>

      {recentResults?.length > 0 && (
        <div>
          <h2 className="font-bold mb-3">Recent Backtests</h2>
          <div className="overflow-x-auto bg-white rounded-lg border border-ink-200">
            <table className="min-w-full text-sm">
              <thead className="bg-ink-50 text-ink-700 uppercase text-xs">
                <tr>
                  <th className="px-3 py-2 text-left">Strategy</th>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-right">PnL</th>
                  <th className="px-3 py-2 text-right">GtP</th>
                  <th className="px-3 py-2 text-left">Tradeable</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Completed</th>
                </tr>
              </thead>
              <tbody>
                {recentResults.map((r) => (
                  <tr key={r.id} className="border-t border-ink-100">
                    <td className="px-3 py-2">{r.strategy_id}</td>
                    <td className="px-3 py-2 font-medium">{r.symbol}</td>
                    <td className={`px-3 py-2 text-right font-mono ${Number(r.net_profit) >= 0 ? 'text-bull-700' : 'text-bear-700'}`}>
                      ₹{Number(r.net_profit || 0).toLocaleString('en-IN')}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{Number(r.gtp_ratio || 0).toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        r.is_tradeable ? 'bg-bull-100 text-bull-700' : 'bg-ink-100 text-ink-700'
                      }`}>
                        {r.is_tradeable ? 'YES' : 'NO'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs">{r.status}</td>
                    <td className="px-3 py-2 text-xs text-ink-600">
                      {r.completed_at ? new Date(r.completed_at).toLocaleString('en-IN') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
