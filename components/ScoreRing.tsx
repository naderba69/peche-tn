interface ScoreRingProps {
  value: number;
  label: string;
  tone?: "mint" | "amber" | "red" | "muted";
}

export function ScoreRing({ value, label, tone = "mint" }: ScoreRingProps) {
  const radius = 43;
  const circumference = 2 * Math.PI * radius;
  const progress = circumference - (Math.max(0, Math.min(100, value)) / 100) * circumference;
  return (
    <div className={`score-ring score-${tone}`}>
      <svg viewBox="0 0 104 104" role="img" aria-label={`${label}: ${value} من مائة`}>
        <circle className="score-track" cx="52" cy="52" r={radius} />
        <circle
          className="score-progress"
          cx="52"
          cy="52"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={progress}
        />
      </svg>
      <div className="score-value"><strong>{value}</strong><span>/100</span></div>
      <small>{label}</small>
    </div>
  );
}
