import {useState, type FormEvent} from 'react'
import {productRequest, type Session} from './productClient'

export default function ProductAccount({writable, onSession}: {writable:boolean; onSession:(value:Session)=>void}) {
  const [busy, setBusy] = useState(false)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  async function change(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!writable || busy) return
    const form = event.currentTarget
    setBusy(true); setError(''); setSuccess(false)
    try {
      const session = await productRequest<Session>('/auth/password', Object.fromEntries(new FormData(form)))
      onSession(session); form.reset(); setSuccess(true)
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Password could not be changed.')}
    finally {setBusy(false)}
  }
  return <section className="product-card"><h2>Your account security</h2><p>Changing your password ends every other session for your account. This browser receives a new session.</p>
    <form onSubmit={change} aria-busy={busy}><fieldset disabled={!writable || busy}><div className="product-form-grid">
      <label>Current password<input name="current_password" type={visible ? 'text' : 'password'} required maxLength={128} autoComplete="current-password"/></label>
      <label>New password<input name="new_password" aria-label="New password" type={visible ? 'text' : 'password'} required minLength={15} maxLength={128} autoComplete="new-password" aria-describedby="new-password-help"/><small id="new-password-help">At least 15 characters. Spaces are preserved.</small></label>
    </div><div className="product-actions"><button className="product-primary" type="submit">{busy ? 'Changing password…' : 'Change password'}</button><button type="button" onClick={() => setVisible(!visible)}>{visible ? 'Hide passwords' : 'Show passwords'}</button></div></fieldset></form>
    {success && <p role="status">Password changed. Other sessions have been revoked.</p>}{error && <p role="alert" className="product-error">{error}</p>}
  </section>
}
