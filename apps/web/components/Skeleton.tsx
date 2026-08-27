/**
 * Shimmering placeholder block. Compose these into a layout that mirrors the
 * real content so the page doesn't jump when the data lands.
 *
 * The `.shimmer` class lives in app/globals.css.
 */
export function SkeletonBar({ className = "" }: { className?: string }) {
  return <div className={`shimmer rounded ${className}`} />;
}

/** A table-shaped skeleton matching the list pages' bordered card + table. */
export function SkeletonTable({
  columns,
  rows = 6,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <div className="bg-white rounded-xl border overflow-hidden">
      <div className="bg-gray-50 border-b flex gap-4 py-3 px-4">
        {Array.from({ length: columns }).map((_, i) => (
          <SkeletonBar key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="border-b last:border-0 flex gap-4 py-3.5 px-4">
          {Array.from({ length: columns }).map((__, c) => (
            <SkeletonBar key={c} className="h-3.5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
