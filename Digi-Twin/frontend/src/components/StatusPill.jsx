const statusStyles = {
  running: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  idle: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  down: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
}

export function StatusPill({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${statusStyles[status]}`}
    >
      {status}
    </span>
  )
}
