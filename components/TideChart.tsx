import { formatHour } from "@/lib/format";
import type { HourDecision, TideEvent } from "@/lib/types";

interface TideChartProps {
  hours: HourDecision[];
  events: TideEvent[];
}

export function TideChart({ hours, events }: TideChartProps) {
  const points = hours
    .map((hour, index) => ({ index, time: hour.time, level: hour.forecast.sea_level_height_msl_m }))
    .filter((point): point is { index: number; time: string; level: number } => point.level !== null);
  if (points.length < 2) {
    return <div className="empty-inline">بيانات مستوى البحر غير كافية للرسم.</div>;
  }

  const width = 760;
  const height = 180;
  const paddingX = 28;
  const paddingY = 22;
  const min = Math.min(...points.map((point) => point.level));
  const max = Math.max(...points.map((point) => point.level));
  const range = Math.max(max - min, 0.02);
  const x = (index: number) => paddingX + (index / Math.max(hours.length - 1, 1)) * (width - paddingX * 2);
  const y = (level: number) => height - paddingY - ((level - min) / range) * (height - paddingY * 2);
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(point.index)} ${y(point.level)}`).join(" ");
  const eventByTime = new Map(events.map((event) => [event.time, event]));

  return (
    <div className="tide-chart-wrap">
      <svg className="tide-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="تغير مستوى البحر المتوقع">
        <defs>
          <linearGradient id="tideArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#42e8c4" stopOpacity="0.34" />
            <stop offset="1" stopColor="#42e8c4" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={paddingX} x2={width - paddingX} y1={height / 2} y2={height / 2} className="chart-grid" />
        <path d={`${path} L ${x(points.at(-1)!.index)} ${height - paddingY} L ${x(points[0].index)} ${height - paddingY} Z`} fill="url(#tideArea)" />
        <path d={path} className="tide-line" />
        {points.map((point) => {
          const event = eventByTime.get(point.time);
          return event ? (
            <g key={point.time}>
              <circle cx={x(point.index)} cy={y(point.level)} r="5" className={event.kind === "high" ? "event-high" : "event-low"} />
              <text x={x(point.index)} y={y(point.level) - 11} textAnchor="middle" className="chart-event-label">
                {event.kind === "high" ? "قمة" : "قاع"} {formatHour(event.time)}
              </text>
            </g>
          ) : null;
        })}
        <text x={paddingX} y={height - 4} className="chart-axis">{formatHour(points[0].time)}</text>
        <text x={width - paddingX} y={height - 4} textAnchor="end" className="chart-axis">{formatHour(points.at(-1)!.time)}</text>
      </svg>
      <div className="chart-range">
        <span>أدنى {min.toFixed(2)} م</span>
        <span>المدى النموذجي {(max - min).toFixed(2)} م</span>
        <span>أعلى {max.toFixed(2)} م</span>
      </div>
    </div>
  );
}
