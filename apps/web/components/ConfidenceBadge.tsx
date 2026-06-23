"use client";

interface ConfidenceBadgeProps {
  value: number;
}

export default function ConfidenceBadge({ value }: ConfidenceBadgeProps) {
  const pct = Math.round(value * 100);
  let color = "bg-green-100 text-green-800";
  if (pct < 50) color = "bg-red-100 text-red-800";
  else if (pct < 75) color = "bg-yellow-100 text-yellow-800";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}
