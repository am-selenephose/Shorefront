export type User = {id: string; email: string; name: string; role: 'admin'|'operator'|'supervisor'|'viewer'; active: number}
export type Fact = {sequence: number; kind: string; record_id: string; revision: number; valid_at: string; known_at: string; source: string; actor_id: string; payload: Record<string, string|number|boolean|null>}
export type Workspace = {runtime_mode: 'operational'; installation_id: string; records: Fact[]; attention: Fact[]; read_at: string; user: User}
export type Session = {user: User; csrf_token: string}
export class ProductError extends Error { constructor(message: string, public status: number) {super(message)} }
let csrf = ''
export function setSession(session: Session | null) {csrf = session?.csrf_token ?? ''}

export async function productRequest<T>(path: string, body?: unknown, key?: string): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch(`/api/v1${path}`, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal: controller.signal,
      headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(key ? {'Idempotency-Key': key} : {})},
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const value = await response.json()
    if (!response.ok) {
      if (response.status === 401 && !['/auth/login', '/auth/me'].includes(path)) window.dispatchEvent(new Event('shorefront:unauthorized'))
      const detail = value.detail
      throw new ProductError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: {loc?: string[]; msg?: string}) => `${e.loc?.join('.') ?? ''}: ${e.msg ?? 'Invalid value'}`).join('; ') : 'Request could not be completed', response.status)
    }
    return value as T
  } catch (error) {
    if (error instanceof ProductError) throw error
    throw new ProductError(controller.signal.aborted ? 'Request timed out. Your input is preserved; retry when connected.' : 'Cannot reach Shorefront. Check the connection and retry.', 0)
  } finally { window.clearTimeout(timer) }
}

export function validateWorkspace(value: Workspace): Workspace {
  if (value?.runtime_mode !== 'operational' || !Array.isArray(value.records) || !Array.isArray(value.attention) ||
      !value.records.every(r => r && typeof r.kind === 'string' && typeof r.record_id === 'string' && Number.isInteger(r.revision) && r.payload && typeof r.payload === 'object')) {
    throw new ProductError('Invalid workspace response. Retaining the last verified view.', 0)
  }
  return value
}
export function recordName(r: Fact) { return String(r.payload.name ?? r.payload.title ?? r.record_id) }
export function dateLabel(value: string) {return new Date(value).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}
