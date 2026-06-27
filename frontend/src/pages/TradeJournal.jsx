/**
 * src/pages/TradeJournal.jsx
 * Performance analytics dashboard — trade history, equity curve, monthly
 * returns, streaks, profit factor, per-symbol breakdown.
 */
import { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Cell,
} from 'recharts';
import {
  useJournalTrades, useJournalAnalytics, useJournalEquityCurve,
  useMonthlyReturns, useStreaks,
} from '../hooks/useQueries';
import StatCard from '../components/StatCard';
import EquityCurveChart from '../components/EquityCurveChart';
import TradeTable from '../components/TradeTable';
import { BookOpen, TrendingUp, Flame, Calendar } from 'lucide-react';

export default function TradeJournal() {
  const [mode, setMode] = useState('live');
  const [days, setDays] = useState(90);

  const { data: analytics } = useJournalAnalytics(mode, days);
  const { data: tradesData } = useJournalTrades({ mode, limit: 50 });
  const { data: equityData } = useJournalEquityCurve(days);
  const { data: monthly } = useMonthlyReturns(null, mode);
  const { data: streaks } = useStreaks(mode);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookOpen size={22} /> Trade Journal
          </h1>
          <p className="text-sm text-ink-200">Performance analytics · trade history · streaks</p>
        </div>
        <div className="flex gap-3">
          <select value={mode} onChange={(e) => setMode(e.target.value)}
            className="px-3 py-2 border border-ink-200 rounded-lg text-sm">
            <option value="live">Live Trades</option>
            <option value="backtest">Backtest Trades</option>
            <option value="all">All Trades</option>
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-2 border border-ink-200 rounded-lg text-sm">
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
            <option value={365}>Last 365 days</option>
          </select>
        </div>
      </div>

      {/* Key metrics */}
      {analytics && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label="Total PnL" value={`₹${Number(analytics.total_pnl || 0).toLocaleString('en-IN')}`}
            tone={Number(analytics.total_pnl) >= 0 ? 'bull' : 'bear'} />
          <StatCard label="Win Rate" value={`${Number(analytics.win_rate || 0).toFixed(1)}%`} />
          <StatCard label="Profit Factor" value={Number(analytics.profit_factor || 0).toFixed(2)}
            tone={Number(analytics.profit_factor) >= 1.5 ? 'bull' : 'bear'} />
          <StatCard label="Total Trades" value={analytics.total_trades || 0} />
          <StatCard label="Avg Win" value={`₹${Number(analytics.avg_win || 0).toLocaleString('en-IN')}`} tone="bull" />
          <StatCard label="Avg Loss" value={`₹${Number(analytics.avg_loss || 0).toLocaleString('en-IN')}`} tone="bear" />
          <StatCard label="Largest Win" value={`₹${Number(analytics.largest_win || 0).toLocaleString('en-IN')}`} tone="bull" />
          <StatCard label="Largest Loss" value={`₹${Number(analytics.largest_loss || 0).toLocaleString('en-IN')}`} tone="bear" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Equity curve */}
        <div className="bg-white rounded-xl border border-ink-200 p-5">
          <h3 className="font-bold mb-3 flex items-center gap-2">
            <TrendingUp size={16} /> Equity Curve ({days} days)
          </h3>
          {equityData?.points?.length > 0 ? (
            <EquityCurveChart
              data={equityData.points.map((p) => ({ t: p.t, equity: p.equity }))}
              height={260}
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-ink-200 text-sm">
              No equity curve data. Run live trades to populate.
            </div>
          )}
        </div>

        {/* Monthly returns bar chart */}
        <div className="bg-white rounded-xl border border-ink-200 p-5">
          <h3 className="font-bold mb-3 flex items-center gap-2">
            <Calendar size={16} /> Monthly Returns ({monthly?.year})
          </h3>
          {monthly?.months && (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthly.months}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748b' }} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }}
                  tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => `₹${Number(v).toLocaleString('en-IN')}`}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                  {monthly.months.map((m, i) => (
                    <Cell key={i} fill={Number(m.pnl) >= 0 ? '#10b981' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          <div className="mt-2 text-xs text-ink-600">
            Total: <span className={Number(monthly?.total_pnl) >= 0 ? 'text-bull-700' : 'text-bear-700'}>
              ₹{Number(monthly?.total_pnl || 0).toLocaleString('en-IN')}
            </span> across {monthly?.total_trades || 0} trades
          </div>
        </div>

        {/* Streaks */}
        <div className="bg-white rounded-xl border border-ink-200 p-5">
          <h3 className="font-bold mb-3 flex items-center gap-2">
            <Flame size={16} /> Streak Analysis
          </h3>
          {streaks && (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <StatCard label="Current Streak"
                  value={`${streaks.current_streak.count}${streaks.current_streak.type}`}
                  tone={streaks.current_streak.type === 'W' ? 'bull' : streaks.current_streak.type === 'L' ? 'bear' : 'neutral'} />
                <StatCard label="Longest Win Streak" value={streaks.longest_win_streak} tone="bull" />
                <StatCard label="Longest Loss Streak" value={streaks.longest_loss_streak} tone="bear" />
              </div>
              <div>
                <div className="text-xs text-ink-200 mb-1">Recent sequence (last 20 trades):</div>
                <div className="font-mono text-lg tracking-wider">
                  {streaks.recent_sequence?.split('').map((s, i) => (
                    <span key={i} className={s === 'W' ? 'text-bull-600' : s === 'L' ? 'text-bear-600' : 'text-ink-300'}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Per-symbol breakdown + exit reasons */}
        <div className="bg-white rounded-xl border border-ink-200 p-5">
          <h3 className="font-bold mb-3">Per-Symbol Breakdown</h3>
          {analytics?.per_symbol?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-ink-50 text-ink-700 uppercase text-xs">
                  <tr>
                    <th className="px-2 py-2 text-left">Symbol</th>
                    <th className="px-2 py-2 text-right">Trades</th>
                    <th className="px-2 py-2 text-right">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.per_symbol.map((s, i) => (
                    <tr key={i} className="border-t border-ink-100">
                      <td className="px-2 py-2 font-medium">{s.symbol}</td>
                      <td className="px-2 py-2 text-right">{s.trades}</td>
                      <td className={`px-2 py-2 text-right font-mono ${Number(s.pnl) >= 0 ? 'text-bull-700' : 'text-bear-700'}`}>
                        ₹{Number(s.pnl).toLocaleString('en-IN')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-sm text-ink-200 py-4 text-center">No trades in this period</div>
          )}
          {analytics?.exit_reasons && Object.keys(analytics.exit_reasons).length > 0 && (
            <div className="mt-4 pt-4 border-t border-ink-100">
              <div className="text-xs font-semibold text-ink-700 mb-2">Exit Reasons:</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(analytics.exit_reasons).map(([reason, count]) => (
                  <span key={reason} className="text-xs px-2 py-1 bg-ink-100 rounded">
                    {reason}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Trade history table */}
      <div>
        <h3 className="font-bold mb-3">Trade History ({tradesData?.total || 0} total)</h3>
        <TradeTable trades={tradesData?.trades || []} mode="score" />
      </div>
    </div>
  );
}
