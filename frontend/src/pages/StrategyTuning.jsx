/**
 * src/pages/StrategyTuning.jsx
 * Visual parameter tuning page with sliders instead of raw JSON.
 *
 * Workflow:
 * 1. User picks a strategy from the dropdown
 * 2. Backend returns slider specs (min/max/step/default) per parameter
 * 3. Sliders render grouped by category (Entry Filters, Exit Rules, etc.)
 * 4. User also picks an instrument + date range
 * 5. "Run Backtest with These Parameters" dispatches a backtest
 * 6. Results show inline (stat cards + equity curve)
 */
import { useEffect, useState } from 'react';
import {
  useStrategies, useTuningSchema, useStartBacktest, useBacktestStatus,
} from '../hooks/useQueries';
import EquityCurveChart from '../components/EquityCurveChart';
import StatCard from '../components/StatCard';
import { Sliders, Play, RotateCcw } from 'lucide-react';

const DEFAULT_SYMBOLS = {
  stock_counter_trend: { symbol: 'RELIANCE', security_id: '2885', segment: 'NSE_EQ' },
  mcx_trend_following: { symbol: 'GOLD',     security_id: '466583', segment: 'MCX' },
  index_bar_scoring:   { symbol: 'NIFTY 50', security_id: '13',    segment: 'NSE_FNO' },
};

export default function StrategyTuning() {
  const { data: strategies } = useStrategies();
  const [strategyId, setStrategyId] = useState('');
  const { data: schema } = useTuningSchema(strategyId);

  const [params, setParams] = useState({});        // {key: value}
  const [instrument, setInstrument] = useState({
    segment: 'NSE_EQ', security_id: '2885', symbol: 'RELIANCE',
  });
  const [dates, setDates] = useState({
    start_date: '', end_date: '', initial_capital: 1_000_000,
  });

  const startBacktest = useStartBacktest();
  const [taskId, setTaskId] = useState(null);
  const { data: status } = useBacktestStatus(taskId);

  // Auto-select first strategy
  useEffect(() => {
    if (!strategies?.length) return;
    if (!strategyId) setStrategyId(strategies[0].id);
  }, [strategies, strategyId]);

  // When schema loads, initialise params from defaults
  useEffect(() => {
    if (!schema) return;
    const defaults = {};
    schema.groups.forEach((g) => {
      g.parameters.forEach((p) => {
        defaults[p.key] = p.type === 'select' ? p.default : Number(p.default);
      });
    });
    setParams(defaults);

    // Also update instrument defaults based on strategy type
    const defaults2 = DEFAULT_SYMBOLS[schema.strategy_type];
    if (defaults2) {
      setInstrument({
        segment: defaults2.segment,
        security_id: defaults2.security_id,
        symbol: defaults2.symbol,
      });
    }
  }, [schema]);

  const onStrategyChange = (id) => setStrategyId(Number(id));

  const updateParam = (key, value) => {
    setParams({ ...params, [key]: value });
  };

  const resetToDefaults = () => {
    if (!schema) return;
    const defaults = {};
    schema.groups.forEach((g) => {
      g.parameters.forEach((p) => {
        defaults[p.key] = p.type === 'select' ? p.default : Number(p.default);
      });
    });
    setParams(defaults);
  };

  const handleRunBacktest = async () => {
    const payload = {
      strategy_id: Number(strategyId),
      segment: instrument.segment,
      security_id: instrument.security_id,
      symbol: instrument.symbol,
      start_date: new Date(dates.start_date || Date.now() - 365 * 86400000).toISOString(),
      end_date: new Date(dates.end_date || Date.now()).toISOString(),
      initial_capital: Number(dates.initial_capital),
      parameters: params,
    };
    const res = await startBacktest.mutateAsync(payload);
    setTaskId(res.task_id);
  };

  const isRunning = status?.status === 'pending' || status?.status === 'running';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sliders size={22} /> Strategy Tuning
          </h1>
          <p className="text-sm text-ink-200">
            Adjust parameters with sliders · run backtests instantly · find the sweet spot
          </p>
        </div>
      </div>

      {/* Strategy selector */}
      <div className="bg-white rounded-xl border border-ink-200 p-4">
        <label className="block text-xs font-semibold text-ink-700 mb-2">Strategy</label>
        <select
          value={strategyId}
          onChange={(e) => onStrategyChange(e.target.value)}
          className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
        >
          {strategies?.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* LEFT: Sliders */}
        <div className="space-y-4">
          {schema?.groups?.map((group) => (
            <div key={group.title} className="bg-white rounded-xl border border-ink-200 p-5">
              <h3 className="font-bold text-sm uppercase tracking-wider text-ink-700 mb-4">
                {group.title}
              </h3>
              <div className="space-y-4">
                {group.parameters.map((p) => (
                  <ParameterControl
                    key={p.key}
                    spec={p}
                    value={params[p.key]}
                    onChange={(v) => updateParam(p.key, v)}
                  />
                ))}
              </div>
            </div>
          ))}

          <div className="flex gap-2">
            <button
              onClick={resetToDefaults}
              className="flex-1 bg-ink-100 hover:bg-ink-200 text-ink-700 font-semibold py-2.5 rounded-lg transition flex items-center justify-center gap-2"
            >
              <RotateCcw size={14} /> Reset to Defaults
            </button>
          </div>
        </div>

        {/* RIGHT: Instrument + Run + Results */}
        <div className="space-y-4">
          {/* Instrument selection */}
          <div className="bg-white rounded-xl border border-ink-200 p-5 space-y-3">
            <h3 className="font-bold text-sm uppercase tracking-wider text-ink-700">Instrument</h3>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-xs text-ink-200 mb-1">Segment</label>
                <select
                  value={instrument.segment}
                  onChange={(e) => setInstrument({ ...instrument, segment: e.target.value })}
                  className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs"
                >
                  <option value="NSE_EQ">NSE_EQ</option>
                  <option value="NSE_FNO">NSE_FNO</option>
                  <option value="MCX">MCX</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-ink-200 mb-1">Symbol</label>
                <input
                  type="text" value={instrument.symbol}
                  onChange={(e) => setInstrument({ ...instrument, symbol: e.target.value })}
                  className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-200 mb-1">Sec ID</label>
                <input
                  type="text" value={instrument.security_id}
                  onChange={(e) => setInstrument({ ...instrument, security_id: e.target.value })}
                  className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs font-mono"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-ink-200 mb-1">Start Date</label>
                <input
                  type="date" value={dates.start_date}
                  onChange={(e) => setDates({ ...dates, start_date: e.target.value })}
                  className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-200 mb-1">End Date</label>
                <input
                  type="date" value={dates.end_date}
                  onChange={(e) => setDates({ ...dates, end_date: e.target.value })}
                  className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-ink-200 mb-1">Initial Capital (₹)</label>
              <input
                type="number" value={dates.initial_capital}
                onChange={(e) => setDates({ ...dates, initial_capital: e.target.value })}
                className="w-full px-2 py-1.5 border border-ink-200 rounded text-xs"
              />
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={handleRunBacktest}
            disabled={startBacktest.isPending || isRunning}
            className="w-full bg-bull-600 hover:bg-bull-700 disabled:opacity-50 text-white font-semibold py-3 rounded-lg transition flex items-center justify-center gap-2"
          >
            <Play size={16} />
            {startBacktest.isPending ? 'Dispatching…' : isRunning ? 'Running…' : 'Run Backtest with These Parameters'}
          </button>

          {/* Live parameters JSON preview */}
          <div className="bg-ink-900 text-ink-50 rounded-xl p-4">
            <div className="text-xs text-ink-200 uppercase tracking-wider mb-2">
              Parameters Preview (JSON sent to backend)
            </div>
            <pre className="text-xs font-mono overflow-x-auto">
              {JSON.stringify(params, null, 2)}
            </pre>
          </div>

          {/* Results */}
          {taskId && (
            <div className="bg-white rounded-xl border border-ink-200 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold">Result</h3>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                  status?.status === 'completed' ? 'bg-bull-100 text-bull-700' :
                  status?.status === 'failed' ? 'bg-bear-100 text-bear-700' :
                  'bg-ink-100 text-ink-700'
                }`}>
                  {status?.status?.toUpperCase() || 'UNKNOWN'}
                </span>
              </div>
              {status?.error_message && (
                <div className="text-sm text-bear-700 bg-bear-50 p-3 rounded-lg mb-3">
                  {status.error_message}
                </div>
              )}
              {isRunning && (
                <div className="text-sm text-ink-200 animate-pulse py-4 text-center">
                  Running backtest… polling every 2s
                </div>
              )}
              {status?.status === 'completed' && (
                <>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    <StatCard label="Net Profit" value={`₹${Number(status.net_profit || 0).toLocaleString('en-IN')}`}
                      tone={Number(status.net_profit) >= 0 ? 'bull' : 'bear'} />
                    <StatCard label="GtP" value={Number(status.gtp_ratio || 0).toFixed(2)}
                      tone={status.gtp_ratio > 1.5 ? 'bull' : 'bear'} />
                    <StatCard label="Trades" value={status.total_trades || 0} />
                    <StatCard label="Win Rate" value={`${Number(status.win_rate || 0).toFixed(0)}%`} />
                  </div>
                  <EquityCurveChart
                    data={status.equity_curve_json || []}
                    initialCapital={Number(status.initial_capital || 1_000_000)}
                    height={220}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
//  Parameter control — renders slider or select
// ============================================================

function ParameterControl({ spec, value, onChange }) {
  if (spec.type === 'select') {
    return (
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-sm font-medium text-ink-700">{spec.label}</label>
          <span className="text-xs text-ink-200">{spec.description}</span>
        </div>
        <select
          value={value || spec.default}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm"
        >
          {spec.options?.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    );
  }

  // Number / integer slider
  const numValue = value !== undefined ? Number(value) : Number(spec.default);
  const isPercent = spec.unit === '%';
  const displayValue = isPercent
    ? `${(numValue * 100).toFixed(2)}%`
    : `${numValue}${spec.unit ? ' ' + spec.unit : ''}`;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-sm font-medium text-ink-700">{spec.label}</label>
        <span className="text-sm font-mono font-semibold px-2 py-0.5 bg-ink-100 rounded text-ink-900">
          {displayValue}
        </span>
      </div>
      <input
        type="range"
        min={spec.min}
        max={spec.max}
        step={spec.step}
        value={numValue}
        onChange={(e) => onChange(spec.type === 'integer' ? parseInt(e.target.value) : parseFloat(e.target.value))}
        className="w-full h-2 bg-ink-100 rounded-lg appearance-none cursor-pointer accent-bull-600"
      />
      <div className="flex justify-between text-[10px] text-ink-200 mt-0.5">
        <span>{isPercent ? `${(spec.min * 100).toFixed(2)}%` : spec.min}</span>
        <span>{isPercent ? `${(spec.max * 100).toFixed(2)}%` : spec.max}</span>
      </div>
      <p className="text-xs text-ink-200 mt-1">{spec.description}</p>
    </div>
  );
}
