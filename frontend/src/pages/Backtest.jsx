/**
 * src/pages/Backtest.jsx
 * Form to launch a backtest + live status + results.
 * Supports BOTH single-instrument and portfolio (multi-instrument) modes.
 */
import { useEffect, useState } from 'react';
import {
  useStrategies, useStartBacktest, useStartPortfolioBacktest,
  useBacktestStatus, useBacktestResults,
} from '../hooks/useQueries';
import EquityCurveChart from '../components/EquityCurveChart';
import StatCard from '../components/StatCard';
import TradeTable from '../components/TradeTable';

const DEFAULT_SYMBOLS = {
  stock_counter_trend: { symbol: 'RELIANCE', security_id: '2885', segment: 'NSE_EQ' },
  mcx_trend_following: { symbol: 'GOLD',     security_id: '466583', segment: 'MCX' },
  index_bar_scoring:   { symbol: 'NIFTY 50', security_id: '13',    segment: 'NSE_FNO' },
};

// Preset portfolio baskets for quick testing
const PORTFOLIO_PRESETS = {
  'NIFTY_LARGE_CAP': [
    { symbol: 'RELIANCE',  security_id: '2885',  segment: 'NSE_EQ' },
    { symbol: 'TATAMOTORS',security_id: '3456',  segment: 'NSE_EQ' },
    { symbol: 'HDFCBANK',  security_id: '1333',  segment: 'NSE_EQ' },
    { symbol: 'INFY',      security_id: '1594',  segment: 'NSE_EQ' },
    { symbol: 'TCS',       security_id: '11536', segment: 'NSE_EQ' },
  ],
};

export default function Backtest() {
  const { data: strategies } = useStrategies();
  const startBacktest = useStartBacktest();
  const startPortfolio = useStartPortfolioBacktest();
  const [taskId, setTaskId] = useState(null);
  const { data: status } = useBacktestStatus(taskId);
  const { data: recentResults } = useBacktestResults(10);

  const [mode, setMode] = useState('single'); // 'single' | 'portfolio'
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
  // Portfolio instruments list
  const [instruments, setInstruments] = useState([
    { security_id: '2885', symbol: 'RELIANCE', segment: 'NSE_EQ', instrument_type: '' },
    { security_id: '3456', symbol: 'TATAMOTORS', segment: 'NSE_EQ', instrument_type: '' },
  ]);

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

  const handleSingleSubmit = async (e) => {
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

  const handlePortfolioSubmit = async (e) => {
    e.preventDefault();
    let params = {};
    try { params = JSON.parse(form.parameters || '{}'); } catch { /* ignore */ }
    const payload = {
      strategy_id: Number(form.strategy_id),
      instruments: instruments
        .filter((i) => i.security_id && i.symbol)
        .map((i) => ({
          security_id: i.security_id,
          symbol: i.symbol,
          segment: i.segment || 'NSE_EQ',
          instrument_type: i.instrument_type || null,
        })),
      start_date: new Date(form.start_date || Date.now() - 365 * 86400000).toISOString(),
      end_date: new Date(form.end_date || Date.now()).toISOString(),
      initial_capital: Number(form.initial_capital),
      parameters: params,
    };
    if (payload.instruments.length < 2) {
      alert('Portfolio backtest requires at least 2 instruments');
      return;
    }
    const res = await startPortfolio.mutateAsync(payload);
    setTaskId(res.task_id);
  };

  // Instrument list helpers
  const addInstrument = () => {
    setInstruments([...instruments, { security_id: '', symbol: '', segment: 'NSE_EQ', instrument_type: '' }]);
  };
  const removeInstrument = (idx) => {
    setInstruments(instruments.filter((_, i) => i !== idx));
  };
  const updateInstrument = (idx, field, value) => {
    setInstruments(instruments.map((inst, i) => i === idx ? { ...inst, [field]: value } : inst));
  };
  const loadPreset = (presetKey) => {
    const preset = PORTFOLIO_PRESETS[presetKey];
    if (preset) setInstruments(preset.map((p) => ({ ...p, instrument_type: '' })));
  };

  const isRunning = status?.status === 'pending' || status?.status === 'running';
  const isPortfolioResult = status?.is_portfolio === true;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Backtest</h1>
        <p className="text-sm text-ink-200">
          Run a Fitschen strategy over historical data · GtP &gt; 1.5 = tradeable ·
          Portfolio mode runs across N instruments with equal capital split
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2 bg-white rounded-lg border border-ink-200 p-1 w-fit">
        <button
          onClick={() => setMode('single')}
          className={`px-4 py-2 rounded-md text-sm font-semibold transition ${
            mode === 'single' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-ink-50'
          }`}
        >
          Single Instrument
        </button>
        <button
          onClick={() => setMode('portfolio')}
          className={`px-4 py-2 rounded-md text-sm font-semibold transition ${
            mode === 'portfolio' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-ink-50'
          }`}
        >
          📊 Portfolio (N instruments)
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form */}
        <form
          onSubmit={mode === 'single' ? handleSingleSubmit : handlePortfolioSubmit}
          className="lg:col-span-1 bg-white rounded-xl border border-ink-200 p-5 space-y-4"
        >
          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Strategy</label>
            <select
              value={form.strategy_id}
              onChange={(e) => onStrategyChange(e.target.value)}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
            >
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {mode === 'single' ? (
            <>
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
                    type="text" value={form.symbol}
                    onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                    className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink-700 mb-1">Security ID (DhanHQ)</label>
                <input
                  type="text" value={form.security_id}
                  onChange={(e) => setForm({ ...form, security_id: e.target.value })}
                  className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm font-mono"
                />
              </div>
            </>
          ) : (
            /* Portfolio instrument list */
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-ink-700">
                  Instruments ({instruments.length})
                </label>
                <div className="flex gap-2">
                  <select
                    onChange={(e) => { if (e.target.value) loadPreset(e.target.value); e.target.value = ''; }}
                    className="text-xs border border-ink-200 rounded px-2 py-1"
                    defaultValue=""
                  >
                    <option value="" disabled>Load preset…</option>
                    <option value="NIFTY_LARGE_CAP">NIFTY Large Cap (5)</option>
                  </select>
                  <button
                    type="button" onClick={addInstrument}
                    className="text-xs bg-bull-600 text-white px-2 py-1 rounded hover:bg-bull-700"
                  >
                    + Add
                  </button>
                </div>
              </div>
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {instruments.map((inst, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-1 items-center">
                    <input
                      type="text" placeholder="Symbol" value={inst.symbol}
                      onChange={(e) => updateInstrument(idx, 'symbol', e.target.value)}
                      className="col-span-4 px-2 py-1 border border-ink-200 rounded text-xs"
                    />
                    <input
                      type="text" placeholder="Sec ID" value={inst.security_id}
                      onChange={(e) => updateInstrument(idx, 'security_id', e.target.value)}
                      className="col-span-3 px-2 py-1 border border-ink-200 rounded text-xs font-mono"
                    />
                    <select
                      value={inst.segment}
                      onChange={(e) => updateInstrument(idx, 'segment', e.target.value)}
                      className="col-span-4 px-1 py-1 border border-ink-200 rounded text-xs"
                    >
                      <option value="NSE_EQ">NSE_EQ</option>
                      <option value="NSE_FNO">NSE_FNO</option>
                      <option value="MCX">MCX</option>
                    </select>
                    <button
                      type="button" onClick={() => removeInstrument(idx)}
                      className="col-span-1 text-bear-600 hover:text-bear-700 text-xs"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-ink-200">
                Each instrument gets ₹{Math.round(Number(form.initial_capital || 0) / Math.max(instruments.length, 1)).toLocaleString('en-IN')} ({Math.round(100 / Math.max(instruments.length, 1))}% of capital)
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">Start Date</label>
              <input
                type="date" value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink-700 mb-1">End Date</label>
              <input
                type="date" value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Initial Capital (₹)</label>
            <input
              type="number" value={form.initial_capital}
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
            disabled={startBacktest.isPending || startPortfolio.isPending}
            className="w-full bg-ink-900 hover:bg-ink-800 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-50"
          >
            {mode === 'portfolio'
              ? (startPortfolio.isPending ? 'Dispatching…' : `▶ Run Portfolio Backtest (${instruments.filter(i=>i.security_id&&i.symbol).length} instruments)`)
              : (startBacktest.isPending ? 'Dispatching…' : '▶ Run Backtest')}
          </button>
        </form>

        {/* Status / Result */}
        <div className="lg:col-span-2 space-y-6">
          {!taskId && (
            <div className="bg-white rounded-xl border border-dashed border-ink-200 p-10 text-center text-ink-200">
              Submit the form to start a {mode === 'portfolio' ? 'portfolio ' : ''}backtest. Results will appear here.
            </div>
          )}

          {taskId && (
            <div className="bg-white rounded-xl border border-ink-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-bold">
                  Task Status
                  {isPortfolioResult && (
                    <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-ink-900 text-white">PORTFOLIO</span>
                  )}
                </h2>
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
              {/* Aggregated stat cards */}
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

              {/* Portfolio breakdown table */}
              {isPortfolioResult && status.portfolio_breakdown && (
                <div>
                  <h3 className="font-bold mb-3">📊 Per-Instrument Breakdown</h3>
                  <div className="overflow-x-auto bg-white rounded-lg border border-ink-200">
                    <table className="min-w-full text-sm">
                      <thead className="bg-ink-50 text-ink-700 uppercase text-xs">
                        <tr>
                          <th className="px-3 py-2 text-left">Symbol</th>
                          <th className="px-3 py-2 text-left">Segment</th>
                          <th className="px-3 py-2 text-right">Trades</th>
                          <th className="px-3 py-2 text-right">Net PnL</th>
                          <th className="px-3 py-2 text-right">PnL %</th>
                          <th className="px-3 py-2 text-right">Win Rate</th>
                          <th className="px-3 py-2 text-right">Max DD %</th>
                          <th className="px-3 py-2 text-right">GtP</th>
                          <th className="px-3 py-2 text-left">Tradeable</th>
                          <th className="px-3 py-2 text-left">Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {status.portfolio_breakdown.map((item, i) => (
                          <tr key={i} className="border-t border-ink-100">
                            <td className="px-3 py-2 font-medium">{item.symbol}</td>
                            <td className="px-3 py-2 text-xs">{item.segment}</td>
                            <td className="px-3 py-2 text-right font-mono">{item.trades}</td>
                            <td className={`px-3 py-2 text-right font-mono ${Number(item.net_profit) >= 0 ? 'text-bull-700' : 'text-bear-700'}`}>
                              ₹{Number(item.net_profit || 0).toLocaleString('en-IN')}
                            </td>
                            <td className={`px-3 py-2 text-right ${Number(item.net_profit_pct) >= 0 ? 'text-bull-700' : 'text-bear-700'}`}>
                              {Number(item.net_profit_pct || 0).toFixed(2)}%
                            </td>
                            <td className="px-3 py-2 text-right">{Number(item.win_rate || 0).toFixed(1)}%</td>
                            <td className="px-3 py-2 text-right text-bear-600">{Number(item.max_drawdown_pct || 0).toFixed(2)}%</td>
                            <td className="px-3 py-2 text-right font-mono">{Number(item.gtp_ratio || 0).toFixed(2)}</td>
                            <td className="px-3 py-2">
                              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                item.is_tradeable ? 'bg-bull-100 text-bull-700' : 'bg-ink-100 text-ink-700'
                              }`}>
                                {item.is_tradeable ? 'YES' : 'NO'}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-xs text-bear-600">{item.error || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Combined equity curve */}
              <div className="bg-white rounded-xl border border-ink-200 p-5">
                <h3 className="font-bold mb-3">
                  {isPortfolioResult ? 'Combined Portfolio Equity Curve' : 'Equity Curve'}
                </h3>
                <EquityCurveChart
                  data={status.equity_curve_json || []}
                  initialCapital={Number(status.initial_capital || 1_000_000)}
                  showDrawdown
                  height={320}
                />
              </div>

              {/* All trades */}
              <div>
                <h3 className="font-bold mb-3">
                  {isPortfolioResult ? `All Trades (${status.trades_json?.length || 0})` : `Trades (${status.trades_json?.length || 0})`}
                </h3>
                <TradeTable trades={status.trades_json || []} mode="score" />
              </div>
            </>
          )}

          {isRunning && (
            <div className="bg-ink-50 rounded-xl border border-ink-200 p-6 text-center text-ink-700 text-sm animate-pulse">
              {isPortfolioResult ? 'Portfolio' : ''} Backtest running… polling every 2s
              {isPortfolioResult && (
                <div className="text-xs text-ink-200 mt-1">
                  (Portfolio backtests take longer — each instrument runs sequentially)
                </div>
              )}
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
                    <td className="px-3 py-2">
                      {r.strategy_id}
                      {r.is_portfolio && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-ink-900 text-white">PORT</span>
                      )}
                    </td>
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
