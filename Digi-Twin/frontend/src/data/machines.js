const statusPool = ['running', 'idle', 'down']

const machineSeeds = [
  { zone: 'Assembly A', type: 'Dual-Arm Gripper' },
  { zone: 'Assembly B', type: 'Precision Gripper' },
  { zone: 'Packaging A', type: 'Box Pick Gripper' },
  { zone: 'Packaging B', type: 'Clamp Gripper' },
  { zone: 'QA Line 1', type: 'Vision Guided Gripper' },
  { zone: 'QA Line 2', type: 'Dual-Arm Gripper' },
  { zone: 'Storage Gate', type: 'Heavy Lift Gripper' },
  { zone: 'CNC Bay', type: 'Thermal Safe Gripper' },
  { zone: 'Dispatch 1', type: 'Clamp Gripper' },
  { zone: 'Dispatch 2', type: 'Precision Gripper' },
  { zone: 'Sorting 1', type: 'Box Pick Gripper' },
  { zone: 'Sorting 2', type: 'Vision Guided Gripper' },
]

export const machines = machineSeeds.map((seed, index) => {
  const machineNumber = `${index + 1}`.padStart(3, '0')
  const status = statusPool[index % statusPool.length]

  return {
    id: `GRP-${machineNumber}`,
    name: `Gripper Station ${machineNumber}`,
    zone: seed.zone,
    type: seed.type,
    status,
    utilization: 56 + ((index * 7) % 41),
    temperature: 34 + ((index * 3) % 20),
    cycleTimeMs: 820 + index * 35,
    errorRate: Number((0.2 + ((index * 0.07) % 1.4)).toFixed(2)),
    lastUpdated: 'Live',
  }
})

export function getMachineById(machineId) {
  return machines.find((machine) => machine.id === machineId)
}

export function getMachineStatusSummary() {
  return machines.reduce(
    (acc, machine) => {
      acc[machine.status] += 1
      return acc
    },
    { running: 0, idle: 0, down: 0 },
  )
}
