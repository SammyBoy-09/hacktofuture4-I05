import { Html, OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Box3, DoubleSide, Quaternion, Vector3 } from 'three'
import * as THREE from 'three'

const RIGHT_ARM_OFFSET_DEG = 90
const BODY_ROTATION_AXIS = 'x'
const ARM_ROTATION_AXIS = 'z'

function toRadians(value) {
  return (value * Math.PI) / 180
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function ReplicateModel({
  jointAngles,
  isCameraTwin,
  placement,
  interactiveBoneControls = false,
  onJointChange,
  jointLimits,
  onOrbitEnabledChange,
}) {
  const { scene } = useGLTF('/models/body.glb')
  const [dragState, setDragState] = useState(null)
  const boneRefs = useRef({ bodyBone: null, rightArmBone: null, leftArmBone: null })
  const rootGroupRef = useRef(null)
  const armHandleGroupRef = useRef(null)

  const { clonedScene, basePosition, boneAnchors } = useMemo(() => {
    const cloned = scene.clone(true)
    const bounds = new Box3().setFromObject(cloned)
    const center = bounds.getCenter(new Vector3())
    const liftAboveGrid = -bounds.min.y + 0.02

    cloned.updateMatrixWorld(true)

    const findBonePosition = (name, fallback) => {
      const node = cloned.getObjectByName(name)
      if (!node) {
        return fallback
      }

      const worldPosition = new Vector3()
      node.getWorldPosition(worldPosition)
      return [worldPosition.x, worldPosition.y, worldPosition.z]
    }

    const bodyAnchor = findBonePosition('Bone', [0, 1.12, 0.18])

    const anchors = {
      body: bodyAnchor,
      'r-arm': findBonePosition('Bone.005', [-0.26, 1.78, 0.18]),
    }

    return {
      clonedScene: cloned,
      basePosition: [-center.x, liftAboveGrid, -center.z],
      boneAnchors: anchors,
    }
  }, [scene])

  useEffect(() => {
    boneRefs.current = {
      bodyBone: clonedScene.getObjectByName('Bone') || null,
      rightArmBone: clonedScene.getObjectByName('Bone.005') || clonedScene.getObjectByName('Bone005') || null,
      leftArmBone: clonedScene.getObjectByName('Bone.004') || clonedScene.getObjectByName('Bone004') || null,
    }
  }, [clonedScene])

  const bodyAngle = jointAngles.body ?? 0
  const rightArmAngle = jointAngles['r-arm'] ?? 0
  const placementX = placement?.x ?? 0
  const placementY = placement?.y ?? 0
  const placementZ = placement?.z ?? 0
  const placementYaw = toRadians(placement?.yaw ?? 0)
  const placementScale = placement?.scale ?? 1

  const modelPosition = [
    basePosition[0] + placementX,
    basePosition[1] + placementY,
    basePosition[2] + placementZ,
  ]

  const handleDefinitions = useMemo(
    () => [
      {
        key: 'body',
        axis: BODY_ROTATION_AXIS,
        dragDirection: 'horizontal',
        dragMultiplier: 1,
        position: boneAnchors.body,
        color: '#0284c7',
      },
      {
        key: 'r-arm',
        axis: ARM_ROTATION_AXIS,
        dragDirection: 'vertical',
        dragMultiplier: 1,
        position: boneAnchors['r-arm'],
        color: '#f97316',
        ringPlane: 'horizontal',
      },
    ],
    [boneAnchors],
  )

  const beginDrag = (event, handleDefinition) => {
    if (isCameraTwin || !interactiveBoneControls || !jointLimits || !onJointChange) {
      return
    }

    const limits = jointLimits[handleDefinition.key]
    if (!limits) {
      return
    }

    event.stopPropagation()

    if (event.target && event.target.setPointerCapture) {
      event.target.setPointerCapture(event.pointerId)
    }

    // Convert the 3D intersection point into the local space of the arc's parent
    const object = event.object
    const localPoint = object.worldToLocal(event.point.clone())
    
    // We are on a 2D plane locally (XY plane for the circle geometry).
    const startAngle = Math.atan2(localPoint.y, localPoint.x)

    setDragState({
      jointKey: handleDefinition.key,
      pointerId: event.pointerId,
      startAngle,
      startValue: jointAngles[handleDefinition.key] ?? 0,
      object: object,
    })
    onOrbitEnabledChange?.(false)
  }

  const updateDrag = (event, handleDefinition) => {
    if (!dragState || dragState.jointKey !== handleDefinition.key || !jointLimits || !onJointChange) {
      return
    }

    const limits = jointLimits[handleDefinition.key]
    if (!limits) {
      return
    }

    // Get the current intersection with an imaginary infinite plane matching the arc's rotation
    // R3F event objects on pointerMove might not always hit the mesh if moving fast, 
    // so we calculate a Ray intersection with a mathematical Plane in the object's local space.
    const object = dragState.object
    const plane = new THREE.Plane(new Vector3(0, 0, 1), 0)
    
    // Convert ray to local space
    const localRay = event.ray.clone()
    object.parent.worldToLocal(localRay.origin)
    // Note: direction is a vector, need to inverse-transform direction without translation
    const inverseMatrix = new THREE.Matrix4().copy(object.parent.matrixWorld).invert()
    localRay.direction.transformDirection(inverseMatrix).normalize()

    const targetLocalPoint = new Vector3()
    localRay.intersectPlane(plane, targetLocalPoint)

    if (!targetLocalPoint) return

    // Reconstruct rotation in local XY space of the arc
    const currentAngle = Math.atan2(targetLocalPoint.y, targetLocalPoint.x)
    let angleDelta = currentAngle - dragState.startAngle

    // Handle wrap-around
    if (angleDelta > Math.PI) angleDelta -= 2 * Math.PI
    if (angleDelta < -Math.PI) angleDelta += 2 * Math.PI

    // Define correct multiplier per-bone
    const isBody = handleDefinition.key === 'body'
    const directionMultiplier = isBody ? 1 : 1

    const degDelta = angleDelta * (180 / Math.PI) * directionMultiplier
    const nextValue = dragState.startValue + degDelta
    const boundedValue = clamp(nextValue, limits.min, limits.max)

    onJointChange(handleDefinition.key, boundedValue, false)
  }

  const endDrag = (event) => {
    if (!dragState || (event && dragState.pointerId !== event.pointerId)) {
      return
    }

    setDragState(null)
    onOrbitEnabledChange?.(true)
  }

  const getCylinderRotation = (axis, ringPlane) => {
    if (ringPlane === 'horizontal') {
      return [Math.PI / 2, 0, 0]
    }
    if (axis === 'y') {
      return [Math.PI / 2, 0, 0]
    }
    if (axis === 'x') {
      return [0, Math.PI / 2, 0]
    }
    if (axis === 'z') {
      return [0, 0, 0]
    }
    return [0, 0, 0]
  }

  useFrame((state, delta) => {
    const { bodyBone, rightArmBone, leftArmBone } = boneRefs.current

    if (bodyBone) {
      const targetBodyRad = toRadians(bodyAngle)
      if (BODY_ROTATION_AXIS === 'x') {
        bodyBone.rotation.x = THREE.MathUtils.lerp(bodyBone.rotation.x, targetBodyRad, delta * 8)
      }
      if (BODY_ROTATION_AXIS === 'y') {
        bodyBone.rotation.y = THREE.MathUtils.lerp(bodyBone.rotation.y, targetBodyRad, delta * 8)
      }
      if (BODY_ROTATION_AXIS === 'z') {
        bodyBone.rotation.z = THREE.MathUtils.lerp(bodyBone.rotation.z, targetBodyRad, delta * 8)
      }
    }

    if (rightArmBone) {
      if (ARM_ROTATION_AXIS === 'x') {
        const targetArmRad = toRadians(rightArmAngle)
        rightArmBone.rotation.x = THREE.MathUtils.lerp(rightArmBone.rotation.x, targetArmRad, delta * 8)
      } else {
        const targetArmRad = toRadians(rightArmAngle + RIGHT_ARM_OFFSET_DEG)
        rightArmBone.rotation.z = THREE.MathUtils.lerp(rightArmBone.rotation.z, targetArmRad, delta * 8)
      }
    }

    if (leftArmBone && rightArmBone) {
      leftArmBone.rotation.x = rightArmBone.rotation.x
      leftArmBone.rotation.y = rightArmBone.rotation.y
      leftArmBone.rotation.z =
        ARM_ROTATION_AXIS === 'z' ? -rightArmBone.rotation.z : rightArmBone.rotation.z
    }

    const rootGroup = rootGroupRef.current
    const armHandleGroup = armHandleGroupRef.current

    if (!rootGroup || !armHandleGroup || !rightArmBone || !bodyBone) {
      return
    }

    const boneWorldPosition = new Vector3()
    const bodyWorldQuaternion = new Quaternion()
    const rootWorldQuaternion = new Quaternion()

    rightArmBone.getWorldPosition(boneWorldPosition)
    bodyBone.getWorldQuaternion(bodyWorldQuaternion)
    rootGroup.getWorldQuaternion(rootWorldQuaternion)

    const localPosition = rootGroup.worldToLocal(boneWorldPosition.clone())
    const localQuaternion = rootWorldQuaternion.clone().invert().multiply(bodyWorldQuaternion)

    armHandleGroup.position.copy(localPosition)
    armHandleGroup.quaternion.copy(localQuaternion)
  })

  return (
    <group
      ref={rootGroupRef}
      position={modelPosition}
      scale={0.88 * placementScale}
      rotation={[0, placementYaw, 0]}
    >
      <primitive object={clonedScene} />

      {handleDefinitions.map((handleDefinition) => {
          const isActive = interactiveBoneControls && dragState?.jointKey === handleDefinition.key
          const ringRadius = handleDefinition.key === 'body' ? 1.25 : 0.8
          const arcStart = handleDefinition.key === 'body' ? -Math.PI * 0.27 : -Math.PI * 0.0
          const arcLength = handleDefinition.key === 'body' ? Math.PI * 1 : Math.PI * 1
          const arcScale = handleDefinition.key === 'r-arm' ? [1, -1, 1] : [1, 1, 1]

          const currentAngleDeg = jointAngles[handleDefinition.key] ?? 0
          const currentAngleRad = toRadians(currentAngleDeg)

          return (
            <group
              key={`anchor-${handleDefinition.key}`}
              ref={handleDefinition.key === 'r-arm' ? armHandleGroupRef : null}
              position={handleDefinition.position}
            >
              <group
                rotation={getCylinderRotation(handleDefinition.axis, handleDefinition.ringPlane)}
                scale={arcScale}
              >
                {isCameraTwin ? (
                  <group>
                    <mesh>
                      <ringGeometry args={[ringRadius - 0.015, ringRadius + 0.015, 64, 1, 0, Math.PI * 2]} />
                      <meshStandardMaterial color={handleDefinition.color} side={DoubleSide} />
                    </mesh>
                    <group rotation={[0, 0, currentAngleRad]}>
                      <mesh position={[ringRadius, 0, 0]}>
                        <sphereGeometry args={[0.04, 16, 16]} />
                        <meshStandardMaterial color="#ef4444" />
                      </mesh>
                      <Html position={[ringRadius + 0.15, 0, 0]} center>
                        <div
                          className="pointer-events-none rounded-md bg-slate-800/80 px-2 py-1 text-[11px] font-bold text-white shadow-sm backdrop-blur-md"
                          style={{ whiteSpace: 'nowrap' }}
                        >
                          {handleDefinition.key === 'r-arm' ? 'Right Arm' : 'Body'}: {Math.abs(currentAngleDeg).toFixed(1)}°
                        </div>
                      </Html>
                    </group>
                  </group>
                ) : (
                  <mesh
                    onPointerDown={interactiveBoneControls ? (event) => beginDrag(event, handleDefinition) : undefined}
                    onPointerMove={interactiveBoneControls ? (event) => updateDrag(event, handleDefinition) : undefined}
                    onPointerUp={interactiveBoneControls ? (event) => endDrag(event) : undefined}
                    onPointerLeave={interactiveBoneControls ? (event) => endDrag(event) : undefined}
                  >
                    <circleGeometry args={[ringRadius, 64, arcStart, arcLength]} />
                    <meshStandardMaterial
                      color={isActive ? '#f97316' : handleDefinition.color}
                      emissive={isActive ? '#fb923c' : handleDefinition.color}
                      emissiveIntensity={isActive ? 0.42 : 0.2}
                      transparent
                      opacity={0.4}
                      depthTest={false}
                      side={DoubleSide}
                    />
                  </mesh>
                )}
              </group>

            </group>
          )
        })}

      {isCameraTwin ? (
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.7, 0.74, 48]} />
          <meshBasicMaterial color='#0ea5e9' transparent opacity={0.3} />
        </mesh>
      ) : null}
    </group>
  )
}

function SceneFallback() {
  return (
    <mesh>
      <boxGeometry args={[1.4, 0.4, 0.8]} />
      <meshStandardMaterial color='#1f4f53' />
    </mesh>
  )
}

export function ReplicateTwinScene({
  jointAngles,
  isCameraTwin = false,
  heightClass = 'h-[420px]',
  placement,
  interactiveBoneControls = false,
  onJointChange,
  jointLimits,
  showAngleHud = false,
  hudTitle = 'Live Joint HUD',
}) {
  const [orbitEnabled, setOrbitEnabled] = useState(true)
  const bodyValue = ((jointAngles.body ?? 0) + 90).toFixed(1)
  const rightArmValue = Math.abs(jointAngles['r-arm'] ?? 0).toFixed(1)

  return (
    <div className={`${heightClass} relative w-full overflow-hidden rounded-2xl border border-slate-200 bg-white`}>
      {showAngleHud ? (
        <div className='pointer-events-none absolute top-3 left-3 z-10 rounded-lg border border-slate-200/80 bg-white/92 px-3 py-2 shadow-sm backdrop-blur'>
          <p className='text-[11px] font-semibold tracking-wide text-slate-500 uppercase'>{hudTitle}</p>
          <p className='mt-1 text-xs font-semibold text-slate-700'>Body: {bodyValue} deg</p>
          <p className='text-xs font-semibold text-slate-700'>Right Arm: {rightArmValue} deg</p>
        </div>
      ) : null}

      <Canvas camera={{ position: [3.2, 2, 3.8], fov: 58 }}>
        <color attach='background' args={['#ffffff']} />
        <ambientLight intensity={isCameraTwin ? 0.95 : 0.8} />
        <directionalLight position={[3, 3, 2]} intensity={1.1} />
        <directionalLight position={[-2, 2, -2]} intensity={0.4} />
        <gridHelper args={[6, 18, '#1e2d48', '#123244']} />

        <Suspense fallback={<SceneFallback />}>
          <ReplicateModel
            jointAngles={jointAngles}
            isCameraTwin={isCameraTwin}
            placement={placement}
            interactiveBoneControls={interactiveBoneControls}
            onJointChange={onJointChange}
            jointLimits={jointLimits}
            onOrbitEnabledChange={setOrbitEnabled}
          />
        </Suspense>

        <OrbitControls
          enablePan={false}
          maxDistance={10}
          minDistance={2.2}
          target={[0, 0, 0]}
          enabled={orbitEnabled}
        />
      </Canvas>
    </div>
  )
}

useGLTF.preload('/models/body.glb')
