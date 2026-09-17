function scoreColor(score: number): string {
  if (score >= 80) return 'text-emerald-600'
  if (score >= 60) return 'text-amber-500'
  return 'text-red-600'
}

function scoreLabel(score: number): string {
  if (score >= 80) return 'Good'
  if (score >= 60) return 'Fair'
  return 'Poor'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-emerald-50 border-emerald-200'
  if (score >= 60) return 'bg-amber-50 border-amber-200'
  return 'bg-red-50 border-red-200'
}

interface Props {
  score: number
}

export default function ScoreGauge({ score }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center rounded-2xl border-2 p-8 ${scoreBg(score)}`}>
      <span className={`text-7xl font-bold tabular-nums ${scoreColor(score)}`}>{score}</span>
      <span className="mt-1 text-sm font-medium text-slate-500">out of 100</span>
      <span className={`mt-3 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${scoreColor(score)} bg-white/60`}>
        {scoreLabel(score)}
      </span>
    </div>
  )
}
