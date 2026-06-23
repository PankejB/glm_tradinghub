/**
 * src/components/StatCard.jsx
 * Compact metric tile used on the Dashboard.
 */
export default function StatCard({ label, value, sub, tone = 'neutral', icon }) {
  const tones = {
    neutral: 'bg-white text-ink-900 border-ink-200',
    bull: 'bg-bull-50 text-bull-700 border-bull-100',
    bear: 'bg-bear-50 text-bear-700 border-bear-100',
    ink: 'bg-ink-900 text-white border-ink-900',
  };
  return (
    <div className={`rounded-xl border shadow-sm p-4 ${tones[tone]}`}>
      <div className="flex items-start justify-between">
        <div className="text-xs uppercase tracking-wider opacity-70 font-semibold">
          {label}
        </div>
        {icon && <div className="opacity-70">{icon}</div>}
      </div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {sub && <div className="text-xs opacity-60 mt-1">{sub}</div>}
    </div>
  );
}
