/**
 * src/pages/Dashboard.jsx
 * Live equity curve + open positions + key stats.
 */
import { usePortfolio } from '../hooks/useQueries';
import EquityCurveChart from '../components/EquityCurveChart';
import StatCard from '../components/StatCard';
import TradeTable from '../components/TradeTable';
import { Wallet, TrendingUp, TrendingDown, Activity } from 'lucide-react';

export default function Dashboard() {
  const { data: portfolio, isLoading } = usePortfolio();

  if (isLoading || !portfolio) {
    return (
      <div className="text-center py-20 text-ink-200">
        Loading portfolio…
      </div>
    );
  }

  const equity = Number(portfolio.current_equity || 0);
  const startEquity = Number(portfolio.starting_capital || 0);
  const pnl = equity - startEquity;
  const pnlPct = startEquity ? (pnl / startEquity) * 100 : 0;
  const pnlPos = pnl >= 0;

  // Build a synthetic equity curve from open positions for the chart preview
  // (in a real deployment, query /api/portfolio/equity-curve for time series)
  const chartData = portfolio.equity_curve?.length
    ? portfolio.equity_curve
    : [
        { t: new Date(Date.now() - 86400000).toISOString(), equity: startEquity },
        { t: new Date().toISOString(), equity },
      ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-ink-200">Live portfolio overview · auto-refreshes every 10s</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Current Equity"
          value={`₹${equity.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          sub={`Start: ₹${startEquity.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          tone="ink"
          icon={<Wallet size={18} />}
        />
        <StatCard
          label="Available Margin"
          value={`₹${Number(portfolio.available_margin || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          sub="Free for new positions"
          tone="neutral"
        />
        <StatCard
          label="Open PnL"
          value={`${pnlPos ? '+' : ''}₹${Number(portfolio.open_pnl || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
          sub="Mark-to-market on open trades"
          tone={pnlPos ? 'bull' : 'bear'}
          icon={pnlPos ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <StatCard
          label="Realised PnL (Today)"
          value={`${Number(portfolio.realized_pnl_today || 0) >= 0 ? '+' : ''}₹${Number(portfolio.realized_pnl_today || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
          sub={`${pnlPct.toFixed(2)}% vs start`}
          tone={Number(portfolio.realized_pnl_today || 0) >= 0 ? 'bull' : 'bear'}
          icon={<Activity size={18} />}
        />
      </div>

      <div className="bg-white rounded-xl border border-ink-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold">Equity Curve</h2>
          <span className="text-xs text-ink-200">Live · updated every 10s</span>
        </div>
        <EquityCurveChart data={chartData} initialCapital={startEquity} height={340} />
      </div>

      <div>
        <h2 className="font-bold mb-3">Open Positions ({portfolio.open_positions?.length || 0})</h2>
        <TradeTable trades={portfolio.open_positions || []} />
      </div>
    </div>
  );
}
