import { Link } from 'react-router-dom'
import { MachineCard } from '../components/MachineCard'
import { getMachineStatusSummary, machines } from '../data/machines'

export function DashboardPage() {
  const summary = getMachineStatusSummary()

  return (
    <main className='mx-auto w-full max-w-7xl px-6 py-8 lg:px-10'>
      <header className='mb-8 flex flex-wrap items-center justify-between gap-3'>
        <div>
          <p className='text-xs font-semibold uppercase tracking-[0.2em] text-slate-500'>
            Industry Fleet Dashboard
          </p>
          <h1 className='mt-2 text-3xl font-bold text-slate-900'>Machine Operations Summary</h1>
        </div>
        <Link
          to='/'
          className='rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm'
        >
          Back to Landing
        </Link>
      </header>

      <section className='mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        <div className='rounded-2xl border border-emerald-200 bg-emerald-50 p-4'>
          <p className='text-sm font-medium text-emerald-700'>Running</p>
          <p className='mt-2 text-3xl font-bold text-emerald-900'>{summary.running}</p>
        </div>
        <div className='rounded-2xl border border-amber-200 bg-amber-50 p-4'>
          <p className='text-sm font-medium text-amber-700'>Idle</p>
          <p className='mt-2 text-3xl font-bold text-amber-900'>{summary.idle}</p>
        </div>
        <div className='rounded-2xl border border-rose-200 bg-rose-50 p-4'>
          <p className='text-sm font-medium text-rose-700'>Down</p>
          <p className='mt-2 text-3xl font-bold text-rose-900'>{summary.down}</p>
        </div>
        <div className='rounded-2xl border border-slate-200 bg-white p-4'>
          <p className='text-sm font-medium text-slate-500'>Total machines</p>
          <p className='mt-2 text-3xl font-bold text-slate-900'>{machines.length}</p>
        </div>
      </section>

      <section>
        <h2 className='mb-4 text-lg font-semibold text-slate-900'>Machine List</h2>
        <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-3'>
          {machines.map((machine) => (
            <MachineCard key={machine.id} machine={machine} />
          ))}
        </div>
      </section>
    </main>
  )
}
