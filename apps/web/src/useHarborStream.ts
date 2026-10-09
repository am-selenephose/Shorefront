import { useCallback, useEffect, useRef, useState } from 'react'
import type { HarborState } from './types'
import { isHarborSnapshot } from './runtimeValidation'

export async function readJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const deadline = new AbortController()
  const timer = setTimeout(() => deadline.abort(), 6000)
  try {
    const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, deadline.signal]) : deadline.signal })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    return await response.json() as T
  } finally {
    clearTimeout(timer)
  }
}

export function useHarborStream() {
  const [state, updateState] = useState<HarborState | null>(null)
  const [online, setOnline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [now, setNow] = useState(Date.now)
  const lastReceived = useRef(0)
  const latestTimestamp = useRef(0)
  const accept = useCallback((value: unknown) => {
    if (!isHarborSnapshot(value)) throw new Error('Invalid operations snapshot; last verified state retained.')
    const timestamp = Date.parse(value.generated_at)
    if (timestamp < latestTimestamp.current) return
    latestTimestamp.current = timestamp
    lastReceived.current = Date.now()
    updateState(value)
    setError(null)
  }, [])

  useEffect(() => {
    let dead = false
    let ws: WebSocket | undefined
    let reconnect: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()
    setError(null)
    setOnline(false)
    void readJson<unknown>('/api/v1/harbor', controller.signal).then(value => {
      if (!dead) accept(value)
    }).catch(() => {
      if (!dead && !lastReceived.current) setError('Operations picture unavailable. Check the API connection and retry.')
    })
    const connect = () => {
      if (dead) return
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/harbor`)
      ws = socket
      socket.onopen = () => { if (!dead) setOnline(true) }
      socket.onmessage = event => {
        if (dead) return
        try { accept(JSON.parse(event.data)) } catch {
          setError('Invalid stream data; last verified state retained.')
          socket.close()
        }
      }
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (!dead) {
          setOnline(false)
          reconnect = setTimeout(connect, 1500)
        }
      }
    }
    connect()
    const clock = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      dead = true
      controller.abort()
      clearTimeout(reconnect)
      clearInterval(clock)
      if (ws) {
        ws.onmessage = null
        ws.onclose = null
        ws.onerror = null
        if (ws.readyState === WebSocket.CONNECTING) ws.onopen = () => ws?.close()
        else ws.close()
      }
    }
  }, [epoch, accept])

  const stale = !!state && (now - lastReceived.current > 10000 || now - Date.parse(state.generated_at) > 15000)
  return { state, setState: accept, online, error, stale, retry: () => setEpoch(value => value + 1) }
}
