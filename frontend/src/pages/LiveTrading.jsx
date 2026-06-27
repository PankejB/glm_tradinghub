/**
 * src/pages/LiveTrading.jsx
 * Toggle switches for strategies + live log console + live-mode safety warnings.
 */
import { useEffect, useRef, useState } from 'react';
import {
  useStrategies, useStartTrading, useStopTrading,
  useActiveTrading, useTradingStatus, useAlertsStatus, useSendTestAlert,
} from '../hooks/useQueries';
import { Radio, Play, Square, Activity, AlertTriangle, ShieldCheck, Send } from 'lucide-react';

export default function LiveTrading() {
  const { data: strategies } = useStrategies();
  const startTrading = useStartTrading();
  const stopTrading = useStopTrading();
  const { data: active } = useActiveTrading();
  const { data: tradingStatus } = useTradingStatus();
  const { data: alertsStatus } = useAlertsStatus();
  const sendTestAlert = useSendTestAlert();

  const [paperMode, setPaperMode] = useState(true);
  const [logs, setLogs] = useState([]);
  const logEndRef = useRef(null);

  // Auto-scroll log to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // If live trading is disabled in backend, force paper mode ON in the UI
  useEffect(() => {
    if (tradingStatus && !tradingStatus.live_trading_enabled) {
      setPaperMode(true);
    }
  }, [tradingStatus]);

  // Convert active tasks to a Set of strategy_ids for quick lookup
  const activeStratIds = new Set(
    (active?.active_live_tasks || []).map((t) => {
      try {
        const args = JSON.parse(t.args || '[]');
        return args[0];
      } catch { return null; }
    }).filter(Boolean)
  );

  const handleStart = async (stratId) => {
    try {
      const res = await startTrading.mutateAsync({
        strategy_id: stratId,
        paper_mode: paperMode,
      });
      // Backend may force paper mode if LIVE_TRADING_ENABLED=false
      const actualPaperMode = res.paper_mode ?? paperMode;
      const forcedToPaper = res.status === 'forced_paper';
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: forcedToPaper ? 'WARN' : (actualPaperMode ? 'INFO' : 'ERROR'),
        msg: forcedToPaper
          ? `⚠️ LIVE TRADING DISABLED — started strategy #${stratId} in PAPER mode instead. Set LIVE_TRADING_ENABLED=true in backend/.env to enable real orders.`
          : `${actualPaperMode ? 'PAPER' : '⚠️ LIVE'} trading started for strategy #${stratId} (task=${res.task_id})${!actualPaperMode ? ' — REAL ORDERS WILL BE PLACED' : ''}`,
      }]);
    } catch (e) {
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: 'ERROR',
        msg: `Failed to start strategy #${stratId}: ${e.response?.data?.detail || e.message}`,
      }]);
    }
  };

  const handleStop = async (stratId) => {
    try {
      const res = await stopTrading.mutateAsync({ strategy_id: stratId, square_off: true });
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: 'INFO',
        msg: `STOP signal sent for strategy #${stratId} (task=${res.task_id}, square_off=true)`,
      }]);
    } catch (e) {
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: 'ERROR',
        msg: `Failed to stop strategy #${stratId}: ${e.response?.data?.detail || e.message}`,
      }]);
    }
  };

  const handleStopAll = async () => {
    try {
      const res = await stopTrading.mutateAsync({ strategy_id: null, square_off: true });
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: 'WARN',
        msg: `STOP ALL dispatched (task=${res.task_id}). All open positions will be squared off.`,
      }]);
    } catch (e) {
      setLogs((l) => [...l, {
        t: new Date().toISOString(),
        level: 'ERROR',
        msg: `STOP ALL failed: ${e.response?.data?.detail || e.message}`,
      }]);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Radio size={22} /> Live Trading
          </h1>
          <p className="text-sm text-ink-200">Start / stop strategies · loops tick every 30s during IST market hours</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={paperMode}
              onChange={(e) => setPaperMode(e.target.checked)}
              disabled={!tradingStatus?.live_trading_enabled}
              className="w-4 h-4 accent-bull-600"
            />
            Paper Mode
            {tradingStatus?.live_trading_enabled ? (
              <span className="text-xs text-bear-600 font-semibold">
                ⚠️ Live trading is ENABLED — unchecking will place REAL orders
              </span>
            ) : (
              <span className="text-xs text-ink-200">
                (live trading disabled in .env — locked to paper)
              </span>
            )}
          </label>
          <button
            onClick={handleStopAll}
            className="bg-bear-600 hover:bg-bear-700 text-white text-sm font-semibold px-3 py-2 rounded-lg flex items-center gap-2"
          >
            <Square size={14} /> STOP ALL
          </button>
        </div>
      </div>

      {/* Safety status banner */}
      {tradingStatus && (
        <div className={`rounded-xl border p-4 flex items-start gap-3 ${
          tradingStatus.live_trading_enabled
            ? 'bg-bear-50 border-bear-200 text-bear-700'
            : 'bg-bull-50 border-bull-200 text-bull-700'
        }`}>
          {tradingStatus.live_trading_enabled ? (
            <AlertTriangle size={20} className="mt-0.5 flex-shrink-0" />
          ) : (
            <ShieldCheck size={20} className="mt-0.5 flex-shrink-0" />
          )}
          <div className="text-sm flex-1">
            <div className="font-semibold">
              {tradingStatus.live_trading_enabled
                ? '⚠️ LIVE TRADING ENABLED — REAL ORDERS WILL BE PLACED'
                : '🛡️ PAPER MODE ONLY — no real orders will be placed'}
            </div>
            <div className="text-xs mt-1 opacity-80">
              {tradingStatus.warning} · Max daily loss: ₹{Number(tradingStatus.max_daily_loss_inr || 0).toLocaleString('en-IN')} ·
              Order type: {tradingStatus.order_type_default} ·
              NSE_EQ product: {tradingStatus.product_types?.NSE_EQ} ·
              NSE_FNO product: {tradingStatus.product_types?.NSE_FNO} ·
              MCX product: {tradingStatus.product_types?.MCX}
            </div>
          </div>
        </div>
      )}

      {/* Telegram alerts status */}
      {alertsStatus && (
        <div className={`rounded-xl border p-4 flex items-start gap-3 ${
          alertsStatus.enabled
            ? 'bg-bull-50 border-bull-200 text-bull-700'
            : 'bg-ink-50 border-ink-200 text-ink-700'
        }`}>
          <Send size={18} className="mt-0.5 flex-shrink-0" />
          <div className="text-sm flex-1">
            <div className="font-semibold">
              {alertsStatus.enabled
                ? '📱 Telegram Alerts Enabled'
                : '📱 Telegram Alerts Disabled'}
            </div>
            <div className="text-xs mt-1 opacity-80">
              {alertsStatus.enabled ? (
                <>
                  Chat ID: <code className="font-mono">{alertsStatus.chat_id}</code> ·
                  Alerts: {alertsStatus.alert_settings?.on_entry && ' Entry'}{alertsStatus.alert_settings?.on_exit && ' Exit'}{alertsStatus.alert_settings?.on_error && ' Error'}{alertsStatus.alert_settings?.on_circuit_breaker && ' CircuitBreaker'}
                </>
              ) : (
                <>Set TELEGRAM_ENABLED=true + TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in backend/.env to receive trade alerts on Telegram.</>
              )}
            </div>
          </div>
          {alertsStatus.enabled && (
            <button
              onClick={() => sendTestAlert.mutate()}
              disabled={sendTestAlert.isPending}
              className="text-xs bg-bull-600 hover:bg-bull-700 text-white px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1"
            >
              <Send size={12} /> {sendTestAlert.isPending ? 'Sending…' : 'Send Test'}
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {strategies?.map((s) => {
          const isActive = activeStratIds.has(s.id);
          const canStart = s.is_tradeable || paperMode;
          return (
            <div key={s.id} className="bg-white rounded-xl border border-ink-200 p-5 shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-bold text-sm leading-tight">{s.name}</h3>
                  <p className="text-xs text-ink-200 mt-1">{s.book_reference}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                  isActive ? 'bg-bull-100 text-bull-700 animate-pulse' : 'bg-ink-100 text-ink-700'
                }`}>
                  {isActive ? '● LIVE' : '○ IDLE'}
                </span>
              </div>

              <div className="text-xs space-y-1 mb-4">
                <div className="flex justify-between">
                  <span className="text-ink-200">Tradeable:</span>
                  <span className={s.is_tradeable ? 'text-bull-700 font-semibold' : 'text-bear-700 font-semibold'}>
                    {s.is_tradeable ? 'YES' : 'NO'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-200">GtP Ratio:</span>
                  <span className="font-mono">{s.latest_gtp_ratio?.toFixed(2) || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-200">Segments:</span>
                  <span className="font-mono text-right">{(s.allowed_segments || []).join(', ')}</span>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => handleStart(s.id)}
                  disabled={isActive || !canStart}
                  className="flex-1 bg-bull-600 hover:bg-bull-700 disabled:bg-ink-200 disabled:text-ink-400 text-white text-sm font-semibold py-2 rounded-lg flex items-center justify-center gap-1"
                >
                  <Play size={14} /> Start
                </button>
                <button
                  onClick={() => handleStop(s.id)}
                  disabled={!isActive}
                  className="flex-1 bg-bear-600 hover:bg-bear-700 disabled:bg-ink-200 disabled:text-ink-400 text-white text-sm font-semibold py-2 rounded-lg flex items-center justify-center gap-1"
                >
                  <Square size={14} /> Stop
                </button>
              </div>

              {!s.is_tradeable && !paperMode && (
                <p className="text-xs text-bear-700 mt-2">
                  ⚠ Strategy is not tradeable (GtP ≤ 1.5). Run a backtest or enable Paper Mode.
                </p>
              )}
            </div>
          );
        })}
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold flex items-center gap-2">
            <Activity size={16} /> Live Logs
          </h2>
          <button
            onClick={() => setLogs([])}
            className="text-xs text-ink-200 hover:text-ink-700"
          >
            clear
          </button>
        </div>
        <div className="bg-ink-900 text-ink-50 rounded-xl p-4 font-mono text-xs h-80 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="text-ink-200 italic">// Start/stop a strategy to see logs</div>
          ) : (
            logs.map((l, i) => (
              <div key={i} className="py-0.5">
                <span className="text-ink-200">[{new Date(l.t).toLocaleTimeString('en-IN')}]</span>{' '}
                <span className={l.level === 'ERROR' ? 'text-bear-500' : l.level === 'WARN' ? 'text-yellow-400' : 'text-bull-400'}>
                  [{l.level}]
                </span>{' '}
                <span>{l.msg}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
