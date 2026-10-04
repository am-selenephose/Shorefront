import {StrictMode, Suspense, lazy, useEffect, useState} from 'react'
import {createRoot} from 'react-dom/client'
import './styles.css'
import {productRequest} from './productClient'
const TrainingApp = lazy(() => import('./App'))
const ProductApp = lazy(() => import('./ProductApp'))
function Runtime() {
  const [runtime, setRuntime] = useState<{runtime_mode: string; needs_setup: boolean}|null>(null)
  const [error, setError] = useState('')
  async function load() {
    setError('')
    try {
      const value = await productRequest<{runtime_mode: string; needs_setup: boolean}>('/runtime/capabilities')
      if (!['operational', 'training'].includes(value.runtime_mode)) throw new Error('Server did not identify an available runtime. No demo fallback was used.')
      setRuntime(value)
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Cannot identify workspace')}
  }
  useEffect(() => {void load()}, [])
  if (!runtime) return <div className="boot" role="status">SHOREFRONT<span>{error || 'Connecting to your workspace…'}</span>{error && <button onClick={() => void load()}>Retry connection</button>}</div>
  return <Suspense fallback={<div className="boot">SHOREFRONT<span>Opening workspace…</span></div>}>{runtime.runtime_mode === 'training' ? <TrainingApp/> : <ProductApp needsSetup={runtime.needs_setup}/>}</Suspense>
}
createRoot(document.getElementById('root')!).render(<StrictMode><Runtime/></StrictMode>)
