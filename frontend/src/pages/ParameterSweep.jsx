/**
 * src/pages/ParameterSweep.jsx
 * Run N backtests varying one or two parameters across a range.
 * Shows a results table with the best run highlighted.
 */
import { useEffect, useState } from 'react';
import {
  useStrategies, useStartSweep, useSweepStatus, useSweepResults,
} from '../hooks/useQueries';
import StatCard from '../components/StatCard';
import { Grid3x3, Play, Trophy } from 'lucide-react';

const DEFAULT_SYMBOLS = {
  stock_counter_trend: { symbol: 'RELIANCE', security_id: '2885', segment: 'NSE_EQ' },
  mcx_trend_following: { symbol: 'GOLD',     security_id: '466583', segment: 'MCX' },
  index_bar_scoring:   { symbol: 'NIFTY 50', security_id: '13',    segment: 'NSE_FNO' },
};

// Preset parameter values for quick sweeps
const SWEEP_PRESETS = {
  stddev_min_pct: { label: 'Min Volatility (StdDev %)', values: [0.005, 0.01, 0.015, 0.02, 0.025, 0.03] },
  profit_target: { label: 'Profit Target (₹)', values: [100, 200, 300, 500, 750, 1000] },
  time_exit_bars: { label: 'Time Exit (bars)', values: [3, 5, 8, 10, 12, 15] },
  stop_loss_stddev_mult: { label: 'SL StdDev Mult', values: [1.5, 2, 2.5, 3, 3.5, 4] },
  trailing_stop_atr_mult: { label: 'Trailing ATR Mult', values: [1, 1.5, 2, 2.5, 3, 4] },
  score_threshold: { label: 'Score Threshold', values: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0] },
  lookback_low: { label: 'Lookback Low', values: [3, 5, 8, 10, 12, 15] },
  lookback_high: { label: 'Lookback High', values: [10, 15, 20, 25, 30, 40] },
  sma_trend: { label: 'Trend SMA', values: [30, 50, 70, 100, 150, 200] },
};

export default function ParameterSweep() {
  const { data: strategies } = useStrategies();
  const startSweep = useStartSweep();
  const [taskId, setTaskId] = useState(null);
  const { data: status } = useSweepStatus(taskId);
  const { data: recentSweeps } = useSweepResults(10);

  const [form, setForm] = useState({
    strategy_id: '',
    segment: 'NSE_EQ',
    security_id: '2885',
    symbol: 'RELIANCE',
    start_date: '',
    end_date: '',
    initial_capital: 1_000_000,
  });

  // Sweep config
  const [sweepParam1, setSweepParam1] = useState('stddev_min_pct');
  const [sweepValues1, setSweepValues1] = useState('0.005, 0.01, 0.015, 0.02, 0.025, 0.03');
  const [sweepParam2, setSweepParam2] = useState('');  // optional 2nd param
  const [sweepValues2, setSweepValues2] = useState('');
  const [baseParams, setBaseParams] = useState('{}');

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
    }));
  };

  const parseValues = (str) => {
    return str.split(',').map((v) => {
      const n = parseFloat(v.trim());
      return isNaN(n) ? v.trim() : n;
    }).filter((v) => v !== '');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    let baseParamsObj = {};
    try { baseParamsObj = JSON.parse(baseParams || '{}'); } catch { /* ignore */ }

    const sweep_parameters = [{
      key: sweepParam1,
      values: parseValues(sweepValues1),
    }];
    if (sweepParam2 && sweepValues2) {
      sweep_parameters.push({
        key: sweepParam2,
        values: parseValues(sweepValues2),
      });
    }

    const payload = {
      strategy_id: Number(form.strategy_id),
      segment: form.segment,
      security_id: form.security_id,
      symbol: form.symbol,
      start_date: new Date(form.start_date || Date.now() - 365 * 86400000).toISOString(),
      end_date: new Date(form.end_date || Date.now()).toISOString(),
      initial_capital: Number(form.initial_capital),
      base_parameters: baseParamsObj,
      sweep_parameters,
    };
    const res = await startSweep.mutateAsync(payload);
    setTaskId(res.task_id);
  };

  const isRunning = status?.status === 'pending' || status?.status === 'running';
  const totalCombos = (parseValues(sweepValues1).length) * (sweepParam2 && sweepValues2 ? parseValues(sweepValues2).length : 1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Grid3x3 size={22} /> Parameter Sweep
        </h1>
        <p className="text-sm text-ink-200">
          Auto-run N backtests across parameter ranges · find the optimal configuration · GtP &gt; 1.5 = tradeable
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-ink-200 p-5 space-y-4">
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

          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-xs text-ink-200 mb-1">Segment</label>
              <select value={form.segment} onChange={(e) => setForm({ ...form, segment: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs">
                <option value="NSE_EQ">NSE_EQ</option>
                <option value="NSE_FNO">NSE_FNO</option>
                <option value="MCX">MCX</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-ink-200 mb-1">Symbol</label>
              <input type="text" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs" />
            </div>
            <div>
              <label className="block text-xs text-ink-200 mb-1">Sec ID</label>
              <input type="text" value={form.security_id} onChange={(e) => setForm({ ...form, security_id: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs font-mono" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-ink-200 mb-1">Start Date</label>
              <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs" />
            </div>
            <div>
              <label className="block text-xs text-ink-200 mb-1">End Date</label>
              <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs" />
            </div>
          </div>

          {/* Sweep parameter 1 */}
          <div className="border-t border-ink-100 pt-4">
            <label className="block text-xs font-semibold text-ink-700 mb-2">Sweep Parameter #1</label>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <select value={sweepParam1} onChange={(e) => {
                setSweepParam1(e.target.value);
                const preset = SWEEP_PRESETS[e.target.value];
                if (preset) setSweepValues1(preset.values.join(', '));
              }} className="px-2 py-1.5 border border-ink-200 rounded text-xs">
                {Object.entries(SWEEP_PRESETS).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
              <input type="text" value={sweepValues1} onChange={(e) => setSweepValues1(e.target.value)}
                placeholder="comma-separated values" className="px-2 py-1.5 border border-ink-200 rounded text-xs font-mono" />
            </div>
          </div>

          {/* Sweep parameter 2 (optional) */}
          <div className="border-t border-ink-100 pt-4">
            <label className="block text-xs font-semibold text-ink-700 mb-2">
              Sweep Parameter #2 (optional — for 2D heatmap)
            </label>
            <div className="grid grid-cols-2 gap-2">
              <select value={sweepParam2} onChange={(e) => setSweepParam2(e.target.value)}
                className="px-2 py-1.5 border border-ink-200 rounded text-xs">
                <option value="">(none)</option>
                {Object.entries(SWEEP_PRESETS).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
              <input type="text" value={sweepValues2} onChange={(e) => setSweepValues2(e.target.value)}
                placeholder="comma-separated values" disabled={!sweepParam2}
                className="px-2 py-1.5 border border-ink-200 rounded text-xs font-mono disabled:bg-ink-50" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink-700 mb-1">Base Parameters (JSON, fixed across all runs)</label>
            <textarea value={baseParams} onChange={(e) => setBaseParams(e.target.value)} rows={3}
              className="w-full px-3 py-2 border border-ink-200 rounded-lg text-xs font-mono" />
          </div>

          <div className="bg-ink-50 rounded-lg p-3 text-xs text-ink-700">
            <strong>Total combinations:</strong> {totalCombos} {totalCombos > 100 && (
              <span className="text-bear-600 font-semibold"> ⚠️ exceeds 100-run limit — reduce values</span>
            )}
          </div>

          <button type="submit" disabled={startSweep.isPending || isRunning || totalCombos > 100}
            className="w-full bg-ink-900 hover:bg-ink-800 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition flex items-center justify-center gap-2">
            <Play size={16} />
            {startSweep.isPending ? 'Dispatching…' : `▶ Run ${totalCombos} Backtests`}
          </button>
        </form>

        {/* Results */}
        <div className="space-y-4">
          {!taskId && (
            <div className="bg-white rounded-xl border border-dashed border-ink-200 p-10 text-center text-ink-200">
              Configure parameters and click Run to start a sweep.
              Results will appear here with the best run highlighted.
            </div>
          )}

          {taskId && (
            <div className="bg-white rounded-xl border border-ink-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-bold">Sweep Status</h2>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                  status?.status === 'completed' ? 'bg-bull-100 text-bull-700' :
                  status?.status === 'failed' ? 'bg-bear-100 text-bear-700' :
                  'bg-ink-100 text-ink-700'
                }`}>
                  {status?.status?.toUpperCase() || 'UNKNOWN'}
                </span>
              </div>
              {status && (
                <div className="text-xs text-ink-600">
                  Progress: {status.completed_runs} / {status.total_runs} runs completed
                  {isRunning && <span className="ml-2 animate-pulse">●</span>}
                </div>
              )}
              {status?.error_message && (
                <div className="mt-2 text-sm text-bear-700 bg-bear-50 p-3 rounded-lg">{status.error_message}</div>
              )}
            </div>
          )}

          {/* Best run highlight */}
          {status?.status === 'completed' && status.best_run && (
            <div className="bg-gradient-to-br from-bull-50 to-bull-100 border border-bull-200 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <Trophy size={18} className="text-bull-700" />
                <h3 className="font-bold text-bull-700">Best Run (Highest GtP)</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <StatCard label="GtP Ratio" value={Number(status.best_run.gtp_ratio || 0).toFixed(2)}
                  tone={status.best_run.gtp_ratio > 1.5 ? 'bull' : 'bear'} />
                <StatCard label="Net Profit" value={`₹${Number(status.best_run.net_profit || 0).toLocaleString('en-IN')}`}
                  tone={Number(status.best_run.net_profit) >= 0 ? 'bull' : 'bear'} />
                <StatCard label="Total Trades" value={status.best_run.total_trades || 0} />
                <StatCard label="Tradeable" value={status.best_run.is_tradeable ? 'YES' : 'NO'}
                  tone={status.best_run.is_tradeable ? 'bull' : 'bear'} />
              </div>
              <div className="bg-white rounded-lg p-3 text-xs font-mono">
                <div className="text-ink-200 mb-1">Best Parameters:</div>
                {JSON.stringify(status.best_run.params, null, 2)}
              </div>
            </div>
          )}

          {/* All runs table */}
          {status?.runs?.length > 0 && (
            <div>
              <h3 className="font-bold mb-2">All Runs ({status.runs.length})</h3>
              <div className="overflow-x-auto bg-white rounded-lg border border-ink-200 max-h-96">
                <table className="min-w-full text-xs">
                  <thead className="bg-ink-50 text-ink-700 uppercase sticky top-0">
                    <tr>
                      <th className="px-2 py-2 text-left">#</th>
                      <th className="px-2 py-2 text-left">Params</th>
                      <th className="px-2 py-2 text-right">Trades</th>
                      <th className="px-2 py-2 text-right">PnL</th>
                      <th className="px-2 py-2 text-right">GtP</th>
                      <th className="px-2 py-2 text-left">Tradeable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.runs.map((run, i) => {
                      const isBest = status.best_run && JSON.stringify(run.params) === JSON.stringify(status.best_run.params);
                      return (
                        <tr key={i} className={`border-t border-ink-100 ${isBest ? 'bg-bull-50' : ''}`}>
                          <td className="px-2 py-1.5">{i + 1}{isBest && ' 🏆'}</td>
                          <td className="px-2 py-1.5 font-mono">{JSON.stringify(run.params)}</td>
                          <td className="px-2 py-1.5 text-right">{run.total_trades}</td>
                          <td className={`px-2 py-1.5 text-right font-mono ${Number(run.net_profit) >= 0 ? 'text-bull-700' : 'text-bear-700'}`}>
                            ₹{Number(run.net_profit || 0).toLocaleString('en-IN')}
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">{Number(run.gtp_ratio || 0).toFixed(2)}</td>
                          <td className="px-2 py-1.5">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              run.is_tradeable ? 'bg-bull-100 text-bull-700' : 'bg-ink-100 text-ink-700'
                            }`}>
                              {run.is_tradeable ? 'YES' : 'NO'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Recent sweeps */}
      {recentSweeps?.length > 0 && (
        <div>
          <h2 className="font-bold mb-3">Recent Sweeps</h2>
          <div className="overflow-x-auto bg-white rounded-lg border border-ink-200">
            <table className="min-w-full text-sm">
              <thead className="bg-ink-50 text-ink-700 uppercase text-xs">
                <tr>
                  <th className="px-3 py-2 text-left">Strategy</th>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-right">Runs</th>
                  <th className="px-3 py-2 text-right">Best GtP</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Completed</th>
                </tr>
              </thead>
              <tbody>
                {recentSweeps.map((s) => (
                  <tr key={s.id} className="border-t border-ink-100">
                    <td className="px-3 py-2">{s.strategy_id}</td>
                    <td className="px-3 py-2 font-medium">{s.symbol}</td>
                    <td className="px-3 py-2 text-right">{s.completed_runs}/{s.total_runs}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {s.best_run ? Number(s.best_run.gtp_ratio || 0).toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs">{s.status}</td>
                    <td className="px-3 py-2 text-xs text-ink-600">
                      {s.completed_at ? new Date(s.completed_at).toLocaleString('en-IN') : '—'}
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
