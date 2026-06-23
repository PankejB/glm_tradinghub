/**
 * src/components/TradeTable.jsx
 * Reusable table for displaying TradeLog rows.
 */
export default function TradeTable({ trades = [], mode = 'live' }) {
  if (!trades.length) {
    return (
      <div className="text-sm text-ink-200 py-8 text-center border border-dashed border-ink-200 rounded-lg bg-white">
        No trades to show
      </div>
    );
  }

  const fmtINR = (v) => (v == null ? '—' : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`);
  const fmtPct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`);
  const fmtTime = (t) => (t ? new Date(t).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—');

  return (
    <div className="overflow-x-auto bg-white rounded-lg border border-ink-200">
      <table className="min-w-full text-sm">
        <thead className="bg-ink-50 text-ink-700 uppercase text-xs">
          <tr>
            <th className="px-3 py-2 text-left">Side</th>
            <th className="px-3 py-2 text-left">Symbol</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Entry</th>
            <th className="px-3 py-2 text-right">SL</th>
            <th className="px-3 py-2 text-right">Exit</th>
            <th className="px-3 py-2 text-right">PnL</th>
            <th className="px-3 py-2 text-right">PnL%</th>
            <th className="px-3 py-2 text-left">Reason</th>
            <th className="px-3 py-2 text-left">Entry Time</th>
            <th className="px-3 py-2 text-left">Exit Time</th>
            {mode === 'score' && <th className="px-3 py-2 text-right">Score</th>}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const pnlPos = (t.pnl || 0) >= 0;
            return (
              <tr key={t.id} className="border-t border-ink-100 hover:bg-ink-50">
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                    t.side === 'BUY' ? 'bg-bull-100 text-bull-700' : 'bg-bear-100 text-bear-700'
                  }`}>
                    {t.side}
                  </span>
                </td>
                <td className="px-3 py-2 font-medium">{t.symbol}</td>
                <td className="px-3 py-2 text-right font-mono">{t.quantity}</td>
                <td className="px-3 py-2 text-right font-mono">{fmtINR(t.entry_price)}</td>
                <td className="px-3 py-2 text-right font-mono text-bear-600">{fmtINR(t.stop_loss)}</td>
                <td className="px-3 py-2 text-right font-mono">
                  {t.exit_price != null ? fmtINR(t.exit_price) : <span className="text-bull-600">OPEN</span>}
                </td>
                <td className={`px-3 py-2 text-right font-mono font-semibold ${pnlPos ? 'text-bull-700' : 'text-bear-700'}`}>
                  {t.pnl != null ? fmtINR(t.pnl) : '—'}
                </td>
                <td className={`px-3 py-2 text-right ${pnlPos ? 'text-bull-700' : 'text-bear-700'}`}>
                  {fmtPct(t.pnl_pct)}
                </td>
                <td className="px-3 py-2 text-xs text-ink-600">{t.exit_reason || '—'}</td>
                <td className="px-3 py-2 text-xs text-ink-600">{fmtTime(t.entry_time)}</td>
                <td className="px-3 py-2 text-xs text-ink-600">{fmtTime(t.exit_time)}</td>
                {mode === 'score' && (
                  <td className="px-3 py-2 text-right font-mono">
                    {t.bar_score != null ? Number(t.bar_score).toFixed(2) : '—'}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
