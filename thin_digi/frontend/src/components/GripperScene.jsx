import { OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Suspense, useMemo } from 'react'
import { Box3, Vector3 } from 'three'

function GripperModel() {
  const { scene } = useGLTF('/models/body.glb')
  const { clonedScene, modelPosition } = useMemo(() => {
    const cloned = scene.clone(true)
    const bounds = new Box3().setFromObject(cloned)
    const center = bounds.getCenter(new Vector3())
    const liftAboveGrid = -bounds.min.y - 0.25

    return {
      clonedScene: cloned,
      modelPosition: [-center.x + 0.45, liftAboveGrid, -center.z - 1],
    }
  }, [scene])

  return (
    <group scale={0.9} rotation={[0, 0, 0]} position={modelPosition}>
      <primitive object={clonedScene} />
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

export function GripperScene({ heightClass = 'h-[460px]' }) {
  return (
    <div className={`${heightClass} w-full overflow-hidden rounded-2xl border border-slate-200 bg-white`}>
      <Canvas camera={{ position: [3.2, 2, 3.8], fov: 58 }}>
        <color attach='background' args={['#ffffff']} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[3, 3, 2]} intensity={1.2} />
        <directionalLight position={[-2, 2, -2]} intensity={0.35} />
        <gridHelper args={[6, 12, '#1e2d48', '#123244']} />

        <Suspense fallback={<SceneFallback />}>
          <GripperModel />
        </Suspense>

        <OrbitControls
          enablePan={false}
          maxDistance={10}
          minDistance={2.2}
          target={[0, 0, 0]}
        />
      </Canvas>
    </div>
  )
}

useGLTF.preload('/models/body.glb')
