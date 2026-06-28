/**
 * src/components/EquityCurveChart.jsx
 * Recharts line chart for equity curve. Used on Dashboard + Backtest pages.
 */
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Area, ComposedChart,
} from 'recharts';

export default function EquityCurveChart({
  data = [],
  height = 320,
  initialCapital = null,
  showDrawdown = false,
}) {
  if (!data.length) {
    return (
      <div className="h-64 flex items-center justify-center text-ink-200 text-sm border border-dashed border-ink-200 rounded-lg bg-white">
        No equity data yet
      </div>
    );
  }

  // Downsample if too many points (keep <= 250)
  const points = data.length > 250
    ? data.filter((_, i) => i % Math.ceil(data.length / 250) === 0)
    : data;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="t"
          tick={{ fontSize: 10, fill: '#64748b' }}
          tickFormatter={(t) => {
            try {
              return new Date(t).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
            } catch {
              return t;
            }
          }}
          minTickGap={30}
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#64748b' }}
          tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`}
          domain={['auto', 'auto']}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(value, name) => {
            if (name === 'equity') return [`₹${Number(value).toLocaleString('en-IN')}`, 'Equity'];
            if (name === 'drawdown_pct') return [`${Number(value).toFixed(2)}%`, 'Drawdown'];
            return [value, name];
          }}
          labelFormatter={(t) => new Date(t).toLocaleString('en-IN')}
        />
        {initialCapital && (
          <ReferenceLine
            y={initialCapital}
            stroke="#94a3b8"
            strokeDasharray="4 4"
            label={{ value: 'Start', fontSize: 10, fill: '#64748b', position: 'insideTopLeft' }}
          />
        )}
        <Area
          type="monotone"
          dataKey="equity"
          stroke="#059669"
          strokeWidth={2}
          fill="url(#equityFill)"
        />
        {showDrawdown && (
          <Line
            type="monotone"
            dataKey="drawdown_pct"
            stroke="#ef4444"
            strokeWidth={1}
            dot={false}
            yAxisId={0}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
