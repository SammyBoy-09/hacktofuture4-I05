import { Link } from 'react-router-dom'
import { StatusPill } from './StatusPill'

export function MachineCard({ machine }) {
  return (
    <Link
      to={`/machines/${machine.id}`}
      className='group rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-sm transition hover:-translate-y-1 hover:shadow-lg'
    >
      <div className='mb-3 flex items-start justify-between gap-2'>
        <div>
          <h3 className='font-semibold text-slate-900'>{machine.name}</h3>
          <p className='text-sm text-slate-500'>{machine.zone}</p>
        </div>
        <StatusPill status={machine.status} />
      </div>

      <dl className='grid grid-cols-2 gap-3 text-sm'>
        <div>
          <dt className='text-slate-500'>Utilization</dt>
          <dd className='font-semibold text-slate-800'>{machine.utilization}%</dd>
        </div>
        <div>
          <dt className='text-slate-500'>Temp</dt>
          <dd className='font-semibold text-slate-800'>{machine.temperature} C</dd>
        </div>
        <div>
          <dt className='text-slate-500'>Cycle</dt>
          <dd className='font-semibold text-slate-800'>{machine.cycleTimeMs} ms</dd>
        </div>
        <div>
          <dt className='text-slate-500'>Error</dt>
          <dd className='font-semibold text-slate-800'>{machine.errorRate}%</dd>
        </div>
      </dl>

      <div className='mt-4 text-sm font-medium text-cyan-700 transition group-hover:text-cyan-800'>
        Open machine dashboard
      </div>
    </Link>
  )
}
