import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { GripperScene } from '../components/GripperScene'
import { ReplicateTwinScene } from '../components/ReplicateTwinScene'
import { StatusPill } from '../components/StatusPill'
import { getMachineById } from '../data/machines'

const tabOptions = [
  { id: 'monitor', label: 'Monitor Movements' },
  { id: 'replicate', label: 'Replicate On Real Gripper' },
  { id: 'agent', label: 'AI Agent Command' },
  { id: 'replay', label: 'Replay Past' },
]

const JOINT_LIMITS = {
  body: { label: 'Body Yaw', min: -45, max: 45, unit: 'deg' },
  'r-arm': { label: 'Right Arm (Bone.005)', min: -90, max: 0, unit: 'deg' },
}

const JOINT_ORDER = ['body', 'r-arm']

const INITIAL_JOINT_ANGLES = {
  body: 0,
  'r-arm': 0,
}

const INITIAL_REPLICATE_PLACEMENT = {
  x: 0,
  y: 0,
  z: 0,
  yaw: 0,
  scale: 1,
}

export function MachineDetailPage() {
  const { machineId } = useParams()
  const machine = getMachineById(machineId)

  const [activeTab, setActiveTab] = useState('monitor')
  const [telemetry, setTelemetry] = useState(() => ({
    utilization: machine?.utilization ?? 0,
    temperature: machine?.temperature ?? 0,
    cycleTimeMs: machine?.cycleTimeMs ?? 0,
    confidence: 96.2,
  }))
  const [commandedAngles, setCommandedAngles] = useState(INITIAL_JOINT_ANGLES)
  const [trackedAngles, setTrackedAngles] = useState(INITIAL_JOINT_ANGLES)
  const [agentPrompt, setAgentPrompt] = useState('Pick up the nearest box and align at station B')
  const [agentPlan, setAgentPlan] = useState(null)
  const [approvalState, setApprovalState] = useState('awaiting')
  const [sequenceTime, setSequenceTime] = useState(1)
  const [aiHistory, setAiHistory] = useState([])
  const [selectedHistoryItem, setSelectedHistoryItem] = useState(null)
  const [replayAngles, setReplayAngles] = useState(INITIAL_JOINT_ANGLES)

  // Fetch AI History when in replay tab
  useEffect(() => {
    if (activeTab === 'replay') {
      fetch('http://localhost:8000/api/ai-history')
        .then(res => res.json())
        .then(data => setAiHistory(data.history || []))
        .catch(err => console.error('Failed to load history', err))
    }
  }, [activeTab])
  const [sequenceLoop, setSequenceLoop] = useState(1)

  // Teleoperation WebSocket
  const wsRef = useRef(null)
  const loopExecutingRef = useRef(false)

  useEffect(() => {
    if (activeTab === 'replicate') {
      wsRef.current = new WebSocket('ws://10.35.41.238:8000/ws/teleop')
      wsRef.current.onopen = () => console.log('Connected to backend for teleoperation')
      wsRef.current.onerror = (e) => console.error('WebSocket error:', e)
      
      return () => {
        if (wsRef.current) {
          wsRef.current.close()
          wsRef.current = null
        }
      }
    }
  }, [activeTab])

  // Stream angles when they change
  useEffect(() => {
    if (activeTab === 'replicate' && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        body: commandedAngles.body,
        'r-arm': commandedAngles['r-arm']
      }))
    }
  }, [commandedAngles, activeTab])

  useEffect(() => {
    const timer = setInterval(() => {
      setTelemetry((prev) => ({
        utilization: clamp(prev.utilization + randomOffset(4), 35, 98),
        temperature: clamp(prev.temperature + randomOffset(1.8), 28, 68),
        cycleTimeMs: clamp(prev.cycleTimeMs + randomOffset(25), 640, 1600),
        confidence: clamp(Number((prev.confidence + randomOffset(0.45)).toFixed(2)), 89, 99.8),
      }))
    }, 1100)

    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    // Removed dummy data tracking interval to mimic real teleop data from CameraCapturePanels
  }, [])

  const healthState = useMemo(() => {
    if (telemetry.confidence < 92) {
      return 'Warning'
    }
    if (telemetry.temperature > 58) {
      return 'Watch temperature'
    }
    return 'Nominal'
  }, [telemetry.confidence, telemetry.temperature])

  const trackingError = useMemo(() => {
    const deltas = {}
    let total = 0

    JOINT_ORDER.forEach((jointKey) => {
      const delta = Math.abs(commandedAngles[jointKey] - trackedAngles[jointKey])
      deltas[jointKey] = Number(delta.toFixed(1))
      total += delta
    })

    const average = Number((total / JOINT_ORDER.length).toFixed(2))

    let syncStatus = 'aligned'
    if (average >= 1.5) {
      syncStatus = 'adjusting'
    }
    if (average >= 4) {
      syncStatus = 'mismatch'
    }

    return { deltas, average, syncStatus }
  }, [commandedAngles, trackedAngles])

  if (!machine) {
    return (
      <main className='mx-auto flex min-h-screen w-full max-w-4xl items-center justify-center px-6'>
        <div className='rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm'>
          <h1 className='text-2xl font-bold text-slate-900'>Machine not found</h1>
          <p className='mt-3 text-slate-600'>This machine ID does not exist in dummy data.</p>
          <Link
            to='/dashboard'
            className='mt-6 inline-flex rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white'
          >
            Return to dashboard
          </Link>
        </div>
      </main>
    )
  }

  const handleJointChange = (jointKey, nextValue, isDisplayValue = true) => {
    const limits = JOINT_LIMITS[jointKey]
    const numericValue = isDisplayValue
      ? fromDisplayAngle(jointKey, Number(nextValue))
      : Number(nextValue)
    const boundedValue = clamp(numericValue, limits.min, limits.max)

    if (jointKey === 'r-arm') {
      setCommandedAngles((previous) => ({
        ...previous,
        'r-arm': boundedValue,
      }))
      return
    }

    setCommandedAngles((previous) => ({
      ...previous,
      [jointKey]: boundedValue,
    }))
  }

  const handleSimulatePlan = async () => {
    const now = Date.now()
    setApprovalState('awaiting')
    try {
      const response = await fetch('http://localhost:8000/api/plan-movement', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt: agentPrompt, sequence_time: sequenceTime }),
      })
      if (!response.ok) throw new Error('API request failed')
      const data = await response.json()
      setAgentPlan({
        generatedAt: new Date(now).toLocaleTimeString(),
        ...data
      })
    } catch (error) {
      console.error(error)
      setAgentPlan({
        error: 'Failed to generate plan',
        generatedAt: new Date(now).toLocaleTimeString()
      })
    }
  }

  const handlePlayOnTwin = async () => {
    if (!agentPlan || !agentPlan.sequence) return
    const originalAngles = { ...commandedAngles }

    for (const step of agentPlan.sequence.steps) {
      setCommandedAngles(prev => {
        const bodyAngle = step.body_tilt !== undefined ? step.body_tilt - 90 : prev.body;
        const armAngle = step.gripper_angle !== undefined ? -step.gripper_angle : prev['r-arm'];
        return {
          ...prev,
          body: bodyAngle,
          'r-arm': armAngle
        }
      })
      await new Promise(resolve => setTimeout(resolve, sequenceTime * 1000))
    }
  }

  const handleExecutePlan = async () => {
    if (!agentPlan || !agentPlan.sequence) return
    setApprovalState('authorized (executing loop)')
    loopExecutingRef.current = true

    for (let count = 0; count < sequenceLoop; count++) {
      if (!loopExecutingRef.current) {
        setApprovalState('canceled')
        break
      }
      try {
        const response = await fetch('http://localhost:8000/api/execute-movement', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sequence_time: sequenceTime,
            sequence: agentPlan.sequence
          }),
        })
        if (!response.ok) throw new Error('Execute API failed')
      } catch (error) {
        console.error('Execution failed:', error)
        if (loopExecutingRef.current) setApprovalState('awaiting')
        loopExecutingRef.current = false
        return
      }
    }
    
    // Complete after successful loops
    if (loopExecutingRef.current) {
      setApprovalState('completed')
      loopExecutingRef.current = false
    }
  }

  const executePlanFast = async (historyPlan) => {
    setApprovalState('executing')
    loopExecutingRef.current = true

    try {
      // Start sending to real machine in the background
      fetch('http://localhost:8000/api/execute-movement', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sequence_time: sequenceTime, sequence: historyPlan }),
      }).catch(e => console.error('BG execution failed:', e))

      // Simulate visually on the 3D model
      if (historyPlan && historyPlan.steps) {
        for (const step of historyPlan.steps) {
          if (!loopExecutingRef.current) break

          // Convert backend variables to frontend UI variables (same ratio logic)
          const targetBody = step.body_tilt - 90
          const targetArm =  -step.gripper_angle

          setReplayAngles({
            body: targetBody,
            'r-arm': targetArm
          })

          // Wait sequence time for visual representation
          await new Promise(r => setTimeout(r, sequenceTime * 1000))
        }
      }
    } catch (error) {
      console.error('Execution failed:', error)
    } finally {
      loopExecutingRef.current = false
      setApprovalState('completed')
      
      // Auto reset 3D avatar 2 seconds after sequence completes
      setTimeout(() => {
        setReplayAngles(INITIAL_JOINT_ANGLES)
        setApprovalState('awaiting')
      }, 2000)
    }
  }

  const handleCancelLoop = () => {
    loopExecutingRef.current = false
    setApprovalState('canceled')
    setAgentPlan(null)
  }

  return (
    <main className='mx-auto w-full max-w-7xl px-6 py-8 lg:px-10'>
      <header className='mb-6 flex flex-wrap items-start justify-between gap-4'>
        <div>
          <Link to='/dashboard' className='text-sm font-semibold text-cyan-700 hover:text-cyan-800'>
            ← Back to dashboard
          </Link>
          <h1 className='mt-2 text-3xl font-bold text-slate-900'>{machine.name}</h1>
          <p className='mt-1 text-sm text-slate-600'>
            {machine.type} · {machine.zone}
          </p>
        </div>
        <StatusPill status={machine.status} />
      </header>

      <section className='rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6'>
        <nav className='mb-5 flex flex-wrap gap-2 border-b border-slate-200 pb-4'>
          {tabOptions.map((tab) => (
            <button
              key={tab.id}
              type='button'
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                activeTab === tab.id
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {activeTab === 'replay' && (
          <div className='grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]'>
            <ReplicateTwinScene heightClass='h-[620px]' placement={INITIAL_REPLICATE_PLACEMENT} jointAngles={replayAngles} />
            <div className='space-y-6'>
              <div className='rounded-2xl border border-slate-200 bg-slate-50 p-5'>
                <h2 className='text-lg font-semibold text-slate-900'>Past AI Actions</h2>
                <div className='mt-4 flex flex-col gap-3 max-h-[500px] overflow-y-auto'>
                  {aiHistory.map((item, idx) => (
                    <div 
                      key={idx} 
                      className={`relative rounded-xl border p-4 transition cursor-pointer ${selectedHistoryItem === item ? 'border-cyan-600 bg-cyan-50' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                      onClick={() => setSelectedHistoryItem(item)}
                    >
                      <button 
                        className="absolute right-3 top-3 text-slate-400 hover:text-cyan-700"
                        title="View JSON"
                        onClick={(e) => {
                          e.stopPropagation()
                          alert(JSON.stringify(item, null, 2))
                        }}
                      >
                        ⓘ
                      </button>
                      <h3 className='font-bold text-slate-800 pr-6'>{item.task_name}</h3>
                      <p className='text-xs text-slate-500 mt-1'>
                        {new Date(item.generated_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                  {aiHistory.length === 0 && (
                    <p className="text-sm text-slate-500 italic">No past AI actions found.</p>
                  )}
                </div>
              </div>
              
              {selectedHistoryItem && (
                <button
                  type='button'
                  onClick={() => executePlanFast(selectedHistoryItem)}
                  disabled={approvalState === 'executing'}
                  className='w-full rounded-xl bg-cyan-600 px-6 py-4 font-bold text-white shadow-sm transition hover:bg-cyan-700 disabled:opacity-50'
                >
                  {approvalState === 'executing' ? 'Replaying...' : 'Replay Selected Action'}
                </button>
              )}
            </div>
          </div>
        )}

        {activeTab === 'monitor' && (
          <div className='grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]'>
            <GripperScene heightClass='h-[620px]' />
            <div className='space-y-4'>
              <TelemetryPanel telemetry={telemetry} healthState={healthState} />
              <div className='rounded-2xl border border-slate-200 bg-slate-50 p-5'>
                <h2 className='text-lg font-semibold text-slate-900'>Live Monitoring</h2>
                <ul className='mt-3 space-y-2 text-sm text-slate-600'>
                  <li>Trajectory stream: 30 FPS equivalent mock data</li>
                  <li>Websocket state: Connected (simulated)</li>
                  <li>Joint sync drift: within threshold</li>
                  <li>Safety mode: Human authorization required</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'replicate' && (
          <div className='space-y-6'>
            <div className='grid gap-6 xl:grid-cols-2'>
              <div className='rounded-2xl border border-slate-200 bg-slate-50 p-4'>
                <div className='mb-3 flex items-center justify-between'>
                  <h2 className='text-base font-semibold text-slate-900'>Command Twin (Operator Control)</h2>
                  <span className='rounded-full bg-cyan-100 px-3 py-1 text-xs font-semibold text-cyan-700'>
                    constrained joints
                  </span>
                </div>
                <ReplicateTwinScene
                  jointAngles={commandedAngles}
                  heightClass='h-[420px]'
                  placement={INITIAL_REPLICATE_PLACEMENT}
                  interactiveBoneControls
                  onJointChange={handleJointChange}
                  jointLimits={JOINT_LIMITS}
                  showAngleHud
                  hudTitle='Command Angles'
                />
              </div>

              <div className='rounded-2xl border border-slate-200 bg-slate-50 p-4'>
                <div className='mb-3 flex items-center justify-between'>
                  <h2 className='text-base font-semibold text-slate-900'>Camera Reconstruction Twin</h2>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${getSyncStatusPillClass(
                      trackingError.syncStatus,
                    )}`}
                  >
                    {trackingError.syncStatus}
                  </span>
                </div>
                <ReplicateTwinScene
                  jointAngles={trackedAngles}
                  isCameraTwin
                  heightClass='h-[420px]'
                  placement={INITIAL_REPLICATE_PLACEMENT}
                />
              </div>
            </div>

            <div className='grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]'>
              <div className='rounded-2xl border border-slate-200 bg-white p-5'>
                <h2 className='text-lg font-semibold text-slate-900'>Interactive Bone Controls</h2>
                <p className='mt-1 text-sm text-slate-600'>
                  Move the gripper joints in real time. Every control is clamped to safe movement
                  limits. Left arm (Bone.004) automatically mirrors right arm (Bone.005).
                </p>

                <div className='mt-4 grid gap-3'>
                  {JOINT_ORDER.map((jointKey) => {
                    const limits = JOINT_LIMITS[jointKey]
                    const displayValue = toDisplayAngle(jointKey, commandedAngles[jointKey])
                    const displayMin = Math.min(
                      toDisplayAngle(jointKey, limits.min),
                      toDisplayAngle(jointKey, limits.max),
                    )
                    const displayMax = Math.max(
                      toDisplayAngle(jointKey, limits.min),
                      toDisplayAngle(jointKey, limits.max),
                    )
                    return (
                      <label
                        key={jointKey}
                        className='rounded-xl border border-slate-200 bg-slate-50 p-3'
                      >
                        <div className='flex items-center justify-between'>
                          <span className='text-sm font-semibold text-slate-800'>{limits.label}</span>
                          <span className='text-sm font-semibold text-cyan-700'>
                            {displayValue.toFixed(1)} {limits.unit}
                          </span>
                        </div>
                        <input
                          type='range'
                          min={displayMin}
                          max={displayMax}
                          step='0.5'
                          value={displayValue}
                          onChange={(event) => handleJointChange(jointKey, event.target.value)}
                          className='mt-3 w-full accent-cyan-700'
                        />
                        <div className='mt-1 flex justify-between text-[11px] text-slate-500'>
                          <span>
                            min {displayMin} {limits.unit}
                          </span>
                          <span>
                            max {displayMax} {limits.unit}
                          </span>
                        </div>
                      </label>
                    )
                  })}
                </div>
              </div>

              <div className='space-y-4'>
              <div className='flex gap-4'>
                <div className='flex-1'>
                  <CameraCapturePanel 
                    viewTitle='Top View' 
                    viewKey='top' 
                    onPoseAngleUpdate={(angle) => {
                      // arm split maps to negative r-arm
                      const mappedVal = clamp(-angle / 2.0, JOINT_LIMITS['r-arm'].min, JOINT_LIMITS['r-arm'].max);
                      setTrackedAngles(p => ({ ...p, 'r-arm': mappedVal }))
                    }} 
                  />
                </div>
                <div className='flex-1'>
                  <CameraCapturePanel 
                    viewTitle='Side View' 
                    viewKey='side' 
                    onPoseAngleUpdate={(angle) => {
                      // side body leaning: raw 90 -> 0 center
                      const mappedVal = clamp(angle - 90, JOINT_LIMITS['body'].min, JOINT_LIMITS['body'].max);
                      setTrackedAngles(p => ({ ...p, 'body': mappedVal }))
                    }} 
                  />
                </div>
              </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'agent' && (
          <div className='grid gap-6 lg:grid-cols-[minmax(0,1.8fr)_minmax(340px,1fr)]'>
            <div>
              <label htmlFor='agentPrompt' className='text-sm font-semibold text-slate-700'>
                Prompt AI Agent
              </label>
              <textarea
                id='agentPrompt'
                value={agentPrompt}
                onChange={(event) => setAgentPrompt(event.target.value)}
                className='mt-2 h-28 w-full rounded-xl border border-slate-300 p-3 text-sm outline-none ring-cyan-600 transition focus:ring-2'
              />
              <div className='mt-4'>
                <label htmlFor='sequenceTime' className='text-sm font-semibold text-slate-700 mr-3'>
                  Sequence Step Duration (seconds)
                </label>
                <input
                  id='sequenceTime'
                  type='number'
                  min='0.1'
                  step='0.1'
                  value={sequenceTime}
                  onChange={(e) => setSequenceTime(Number(e.target.value))}
                  className='w-24 rounded-lg border border-slate-300 p-2 text-sm outline-none ring-cyan-600 transition focus:ring-2'
                />
              </div>
              <div className='mt-4'>
                <label htmlFor='sequenceLoop' className='text-sm font-semibold text-slate-700 mr-3'>
                  Loop Count (How many times)
                </label>
                <input
                  id='sequenceLoop'
                  type='number'
                  min='1'
                  step='1'
                  value={sequenceLoop}
                  onChange={(e) => setSequenceLoop(Number(e.target.value))}
                  className='w-24 rounded-lg border border-slate-300 p-2 text-sm outline-none ring-cyan-600 transition focus:ring-2'
                />
              </div>
              <div className='mt-4 flex gap-3'>
                <button
                  type='button'
                  onClick={handleSimulatePlan}
                  className='rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800'
                >
                  Fetch AI Trajectory
                </button>

                {agentPlan && (
                  <button
                    type='button'
                    onClick={handlePlayOnTwin}
                    className='rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50'
                  >
                    Play on Digital Twin
                  </button>
                )}
              </div>

              {agentPlan && (
                <div className='mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4'>
                  <p className='text-sm font-semibold text-slate-900'>Proposed trajectory ({agentPlan.status})</p>
                  <p className='mt-1 text-xs text-slate-500'>Generated at {agentPlan.generatedAt}</p>
                  <pre className='mt-3 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100'>
                    {JSON.stringify(agentPlan, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className='space-y-4'>
              <ReplicateTwinScene
                jointAngles={commandedAngles}
                heightClass='h-[500px]'
                placement={INITIAL_REPLICATE_PLACEMENT}
              />
              <div className='mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-5'>
                <h2 className='text-lg font-semibold text-slate-900'>HITL Authorization Gate</h2>
                <p className='mt-2 text-sm text-slate-600'>
                  Demo flow: AI proposes a safe path, then operator approves or cancels execution.
                </p>
                <div className='mt-4 flex gap-2'>
                  <button
                    type='button'
                    onClick={handleExecutePlan}
                    className='rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700'
                  >
                    Authorize Execute
                  </button>
                  <button
                    type='button'
                    onClick={handleCancelLoop}
                    className='rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-700'
                  >
                    Cancel
                  </button>
                </div>
                <p className='mt-3 text-sm font-medium text-slate-700'>
                  Decision: <span className='capitalize'>{approvalState}</span>
                </p>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

function TelemetryPanel({ telemetry, healthState }) {
  return (
    <div className='rounded-2xl border border-slate-200 bg-white p-4'>
      <div className='grid grid-cols-2 gap-3'>
        <MetricTile label='Utilization' value={`${Math.round(telemetry.utilization)}%`} />
        <MetricTile label='Temperature' value={`${Math.round(telemetry.temperature)} C`} />
        <MetricTile label='Cycle Time' value={`${Math.round(telemetry.cycleTimeMs)} ms`} />
        <MetricTile label='Vision Confidence' value={`${telemetry.confidence}%`} />
      </div>
      <p className='mt-3 text-xs font-semibold text-cyan-700'>{healthState}</p>
    </div>
  )
}

function CameraCapturePanel({ viewTitle, viewKey, onPoseAngleUpdate }) {
  const [cameraState, setCameraState] = useState('stopped')
  const [frameSrc, setFrameSrc] = useState('')
  const [poseAngle, setPoseAngle] = useState(null)
  const [boxFlag, setBoxFlag] = useState(null)
  const wsRef = useRef(null)

  const startCamera = () => {
    if (wsRef.current) return
    setCameraState('connecting...')
    
    // Connect to the Python FastAPI broker, using current hostname so it works across devices
    const wsHost = window.location.hostname;
    wsRef.current = new WebSocket(`ws://${wsHost}:8000/ws/camera_out/${viewKey}`)
    
    wsRef.current.onopen = () => {
      setCameraState('streaming')
    }
    
    wsRef.current.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.image) {
          const incomingData = parsed.image;
          if (incomingData.startsWith('data:image')) {
            setFrameSrc(incomingData);
          } else {
            setFrameSrc(`data:image/jpeg;base64,${incomingData}`);
          }
        }
        if (parsed.angle !== undefined && parsed.angle !== null) {
          setPoseAngle(parsed.angle);
          if (onPoseAngleUpdate) onPoseAngleUpdate(parsed.angle);
        }
        if (parsed.box_flag !== undefined && parsed.box_flag !== null) {
          setBoxFlag(parsed.box_flag);
        }
      } catch (e) {
        // Fallback for raw text
        const incomingData = event.data;
        if (incomingData.startsWith('data:image')) {
          setFrameSrc(incomingData);
        } else {
          setFrameSrc(`data:image/jpeg;base64,${incomingData}`);
        }
      }
    }
    
    wsRef.current.onerror = () => {
      setCameraState('error')
    }
    
    wsRef.current.onclose = () => {
      setFrameSrc('')
      setCameraState('stopped')
      wsRef.current = null
    }
  }

  const stopCamera = () => {
    if (wsRef.current) {
      wsRef.current.close()
    }
  }

  return (
    <div className='rounded-2xl border border-slate-200 bg-slate-50 p-4'>
      <div className='flex items-center justify-between'>
        <h2 className='text-base font-semibold text-slate-900'>{viewTitle}</h2>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            cameraState === 'streaming'
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-slate-200 text-slate-600'
          }`}
        >
          {cameraState}
        </span>
      </div>

      <div className='mt-3 overflow-hidden rounded-xl border border-slate-300 bg-slate-900 flex items-center justify-center aspect-[9/16]'>
        {frameSrc ? (
          <img
            src={frameSrc}
            alt={`${viewTitle} Feed`}
            className='h-full w-full object-cover'
          />
        ) : (
          <div className='text-center p-4'>
            <p className='text-sm text-slate-500'>Camera feed stopped</p>
            <p className='mt-1 text-xs text-slate-600'>Waiting for stream...</p>
          </div>
        )}
      </div>

      {poseAngle !== null && (
        <div className='mt-2 rounded-lg bg-cyan-50 border border-cyan-100 p-2 text-center'>
          <p className='text-xs font-semibold text-cyan-800 uppercase tracking-widest'>Current Angle</p>
          <p className='text-lg font-bold text-cyan-900'>{poseAngle.toFixed(1)}°</p>
        </div>
      )}

      {boxFlag !== null && (
        <div className={`mt-2 rounded-lg border p-2 text-center ${boxFlag ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-50 border-slate-200'}`}>
          <p className={`text-xs font-semibold uppercase tracking-widest ${boxFlag ? 'text-emerald-800' : 'text-slate-500'}`}>Object in Gripper</p>
          <p className={`text-lg font-bold ${boxFlag ? 'text-emerald-900' : 'text-slate-400'}`}>{boxFlag ? 'DETECTED' : 'CLEAR'}</p>
        </div>
      )}

      {cameraState === 'error' && (
        <p className='mt-2 text-xs text-rose-700'>Failed to connect to backend feed broker.</p>
      )}

      <div className='mt-3 flex gap-2'>
        <button
          type='button'
          onClick={startCamera}
          className='flex-1 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800'
        >
          Connect
        </button>
        <button
          type='button'
          onClick={stopCamera}
          className='flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100'
        >
          Stop
        </button>
      </div>
    </div>
  )
}

function MetricTile({ label, value }) {
  return (
    <article className='rounded-xl border border-slate-200 bg-slate-50 p-3'>
      <p className='text-xs font-semibold tracking-wide text-slate-500 uppercase'>{label}</p>
      <p className='mt-2 text-2xl font-bold text-slate-900'>{value}</p>
    </article>
  )
}

function randomOffset(step) {
  return (Math.random() - 0.5) * step
}

function toDisplayAngle(jointKey, value) {
  if (jointKey === 'body') {
    return value + 90
  }
  if (jointKey === 'r-arm') {
    return -value
  }
  return value
}

function fromDisplayAngle(jointKey, value) {
  if (jointKey === 'body') {
    return value - 90
  }
  if (jointKey === 'r-arm') {
    return -value
  }
  return value
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function getSyncStatusPillClass(syncStatus) {
  if (syncStatus === 'mismatch') {
    return 'bg-rose-100 text-rose-700'
  }
  if (syncStatus === 'adjusting') {
    return 'bg-amber-100 text-amber-700'
  }
  return 'bg-emerald-100 text-emerald-700'
}
