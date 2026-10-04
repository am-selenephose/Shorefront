import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import ProductRecords from './ProductRecords'
import ProductDecisions from './ProductDecisions'
import ProductAccount from './ProductAccount'
import {ProductError, dateLabel, productRequest, recordName, setSession, validateWorkspace, type Fact, type Session, type User, type Workspace} from './productClient'
import './product.css'

const views = ['Pulse', 'Records', 'Plan', 'Evidence', 'Team'] as const
type View = typeof views[number]
function readView(): View {return views.find(v => `#${v.toLowerCase()}` === location.hash) ?? 'Pulse'}
function ThemeButton() {
  const [dark, setDark] = useState(document.documentElement.dataset.theme === 'dark')
  return <button onClick={() => {const theme = dark ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; setDark(!dark); try {localStorage.setItem('shorefront.theme', theme)} catch { /* theme still works for this visit */ }}} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? 'Light mode' : 'Dark mode'}</button>
}

function SignIn({setup, onSession}: {setup: boolean; onSession: (value: Session) => void}) {
  const [invite, setInvite] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const data = Object.fromEntries(new FormData(event.currentTarget))
    try {onSession(await productRequest<Session>(setup ? '/auth/bootstrap' : invite ? '/auth/accept' : '/auth/login', data))}
    catch (failure) {setError(failure instanceof Error ? failure.message : 'Sign-in failed')}
    finally {setBusy(false)}
  }
  return <div className="product-login"><header><a className="product-wordmark" href="/">SHOREFRONT<span>OPERATIONS, WITH A RECORD.</span></a><ThemeButton/></header>
    <main><section className="product-login-intro"><span className="product-index">YOUR PRIVATE OPERATIONAL WORKSPACE</span><h1>{setup ? 'Open your operational workspace' : invite ? 'Join your team' : 'Sign in to Shorefront'}</h1><p>One shared picture. Accountable decisions. A history that stays intact.</p><div className="product-rule"/><p className="product-small">This installation starts with your data. Nothing here is filled with demo vessels, synthetic weather, or invented outcomes.</p></section>
      <section className="product-login-form"><p className="eyebrow">{setup ? 'INSTALLATION SETUP' : invite ? 'INVITATION' : 'SECURE ACCESS'}</p><form onSubmit={submit} aria-busy={busy}><fieldset disabled={busy}>
        {setup && <label>Setup token<input name="bootstrap_token" type="password" required autoComplete="off"/><small>Provided privately by your installation operator.</small></label>}
        {invite && !setup && <label>Invitation token<input name="invitation_token" type="password" required autoComplete="off"/></label>}
        {(setup || invite) && <label>Full name<input name="display_name" required maxLength={200} autoComplete="name"/></label>}
        <label>Email<input name="email" type="email" required autoComplete="email" maxLength={254} spellCheck={false}/></label>
        <label>Password<input name="password" aria-label="Password" aria-describedby={setup || invite ? 'password-help' : undefined} type={showPassword ? 'text' : 'password'} required minLength={setup || invite ? 15 : 1} maxLength={128} autoComplete={setup || invite ? 'new-password' : 'current-password'}/></label>{(setup || invite) && <small id="password-help">At least 15 characters. A memorable passphrase works well.</small>}
        <button className="product-quiet" type="button" onClick={() => setShowPassword(!showPassword)}>{showPassword ? 'Hide password' : 'Show password'}</button>
        {error && <p className="product-error" role="alert">{error}</p>}
        <button className="product-primary" type="submit">{busy ? 'Please wait…' : setup ? 'Create workspace' : invite ? 'Accept invitation' : 'Sign in'}</button>
      </fieldset></form>{!setup && <button className="product-quiet" onClick={() => {setInvite(!invite); setError('')}}>{invite ? 'Back to sign in' : 'I have an invitation'}</button>}<p className="product-small">Access is granted by your organisation. Contact your installation operator if you need account recovery.</p></section></main>
    </div>
}

function Pulse({workspace, team}: {workspace: Workspace; team:User[]}) {
  const {records, attention} = workspace
  const port = records.find(r => r.kind === 'port')
  return <><section className="product-pulse-heading"><span className="product-index">PULSE / OPERATIONAL WORKSPACE</span><h1>Your port. Your operational record.</h1><p>{port ? `${recordName(port)} — facts supplied by your team, with their sources preserved.` : 'Start with your port, then bring its berths, vessels and calls into one accountable picture.'}</p></section>
    <div className="product-stats">{[['Port calls', records.filter(r => r.kind === 'call').length], ['Open incidents', records.filter(r => r.kind === 'incident' && r.payload.status !== 'resolved').length], ['Actions to complete', attention.length], ['Recorded facts', records.length]].map(([name, count], i) => <div key={name}><span className="product-index">0{i+1} / {name}</span><strong>{count}</strong></div>)}</div>
    <div className="product-section-heading"><div><p className="eyebrow">ATTENTION</p><h2>The next accountable action.</h2></div><a href="#records">Manage records →</a></div>
    {attention.length ? <div className="product-record-grid">{attention.map(task => <article className="product-card" key={task.record_id}><span className="product-index">{task.payload.status === 'in_progress' ? 'IN PROGRESS' : 'OPEN'} · {new Date(String(task.payload.due_at)) < new Date() ? 'OVERDUE' : 'SCHEDULED'}</span><h2>{recordName(task)}</h2><p>Due {dateLabel(String(task.payload.due_at))}</p><p>{task.payload.assignee_id ? `Assigned to ${team.find(member => member.id === task.payload.assignee_id)?.name ?? task.payload.assignee_id}` : 'Unassigned — choose an owner'}</p><p className="product-provenance">{task.source}</p></article>)}</div> : <section className="product-empty"><span className="product-index">CLEAR QUEUE</span><h2>No open tasks recorded.</h2><p>This means no open tasks are in Shorefront. It does not certify that the port is free of operational risk.</p><a href="#records">Record an incident or task →</a></section>}
    <aside className="product-boundary"><b>Recorded facts, not a simulated harbor.</b><p>Weather, vessel positions and predicted savings stay unknown until supported by actual observations and validated integrations. Shorefront does not control vessels.</p></aside>
  </>
}

function Evidence() {
  const [history, setHistory] = useState<Fact[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [download, setDownload] = useState(false)
  const [knownAt, setKnownAt] = useState('')
  const [validAt, setValidAt] = useState('')
  const [replay, setReplay] = useState<Fact[]|null>(null)
  async function load(after=0) {
    setLoading(true); setError('')
    try {const rows = await productRequest<Fact[]>(`/history?after=${after}&limit=100`); if (!Array.isArray(rows)) throw new Error('Invalid history response'); setHistory(old => after ? [...old, ...rows] : rows); setMore(rows.length === 100)}
    catch (failure) {setError(String(failure))} finally {setLoading(false)}
  }
  useEffect(() => {void load()}, [])
  async function exportEvidence() {
    setDownload(true); setError('')
    try {
      const data = await productRequest('/evidence')
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}))
      const link = document.createElement('a'); link.href=url; link.download='shorefront-evidence.json'; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (failure) {setError(String(failure))} finally {setDownload(false)}
  }
  async function reconstruct(event: FormEvent) {
    event.preventDefault(); setError(''); setReplay(null)
    try {const params = new URLSearchParams({known_at:new Date(knownAt).toISOString(), valid_at:new Date(validAt).toISOString()}); setReplay(validateWorkspace(await productRequest<Workspace>(`/workspace?${params}`)).records)}
    catch (failure) {setError(String(failure))}
  }
  return <><div className="product-section-heading"><div><p className="eyebrow">EVIDENCE / PRESERVED CONTEXT</p><h1>Every correction keeps its past.</h1></div><button disabled={download} onClick={() => void exportEvidence()}>{download ? 'Preparing…' : 'Export evidence'}</button></div>
    <p>Recorded time answers “what did we know?” Effective time answers “when did it apply?” The audit uses a SHA-256 chain, not a digital signature.</p>
    <form className="product-replay" onSubmit={reconstruct}><label>Known by<input type="datetime-local" value={knownAt} required onChange={e => setKnownAt(e.target.value)}/></label><label>Effective at<input type="datetime-local" value={validAt} required onChange={e => setValidAt(e.target.value)}/></label><button type="submit">Reconstruct view</button></form>
    {replay !== null && <section className="product-card"><h2>Historical facts · {replay.length}</h2>{replay.map(r => <p key={`${r.kind}:${r.record_id}`}>{recordName(r)} · revision {r.revision}</p>)}</section>}
    {error && <p role="alert" className="product-error">{error} <button onClick={() => void load()}>Retry</button></p>}
    <h2>Record history</h2>{loading && <p role="status">Loading recorded history…</p>}
    {!loading && !history.length && <div className="product-empty"><h3>No operational versions yet.</h3><p>Create a record to start its history.</p></div>}
    <ol className="product-history">{history.map(r => <li key={r.sequence}><div><span className="product-index">{r.kind} / V{r.revision}</span><strong>{recordName(r)}</strong><span>{r.source}</span></div><div><span>Recorded {dateLabel(r.known_at)}</span><span>Effective {dateLabel(r.valid_at)}</span></div></li>)}</ol>
    {more && <button disabled={loading} onClick={() => void load(history.at(-1)?.sequence)}>Load older versions</button>}
  </>
}

function Team({members, session, writable, onRefresh, onSession}: {members: User[]; session: Session; writable: boolean; onRefresh: () => Promise<void>; onSession:(value:Session)=>void}) {
  const [error, setError] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState<string|null>(null)
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setToken('')
    const form = event.currentTarget
    try {const result = await productRequest<{invitation_token:string}>('/auth/invitations', Object.fromEntries(new FormData(form))); setToken(result.invitation_token); form.reset()}
    catch (failure) {setError(String(failure))} finally {setBusy(false)}
  }
  async function revoke(id: string) {
    setBusy(true); setError('')
    try {await productRequest(`/team/${id}/revoke`, {}); setConfirm(null); await onRefresh()}
    catch (failure) {setError(String(failure))} finally {setBusy(false)}
  }
  return <><p className="eyebrow">TEAM / EXPLICIT AUTHORITY</p><h1>Access is accountable.</h1><p>Roles are enforced by the API. A display preference never grants permission.</p>
    <ProductAccount writable={writable} onSession={onSession}/>
    {session.user.role === 'admin' && <section className="product-card"><h2>Invite a team member</h2><form onSubmit={invite}><fieldset disabled={!writable || busy}><div className="product-form-grid"><label>Invitation email<input type="email" name="email" required autoComplete="email"/></label><label>Role<select name="role" aria-label="Role" defaultValue="operator">{['operator','supervisor','viewer','admin'].map(r => <option key={r}>{r}</option>)}</select></label></div><button className="product-primary">{busy ? 'Working…' : 'Create invitation'}</button></fieldset></form>
      {token && <div className="product-boundary"><b>One-time invitation · expires in 24 hours</b><p>No email was sent. Share this token privately with the named recipient. They select “I have an invitation” on the sign-in page.</p><code>{token}</code><button onClick={() => setToken('')}>Hide token</button></div>}</section>}
    {error && <p role="alert" className="product-error">{error}</p>}
    <div className="product-record-grid">{members.map(member => <article className="product-card" key={member.id}><span className="product-index">{member.role} / {member.active ? 'ACTIVE' : 'REVOKED'}</span><h2>{member.name}</h2><p>{member.email}</p>{session.user.role === 'admin' && member.id !== session.user.id && !!member.active && (confirm === member.id ? <div><p>Revoke access and all sessions for {member.name}?</p><button disabled={!writable || busy} onClick={() => void revoke(member.id)}>Confirm revocation</button><button onClick={() => setConfirm(null)}>Cancel</button></div> : <button disabled={!writable} onClick={() => setConfirm(member.id)}>Revoke access</button>)}</article>)}</div>
  </>
}

export default function ProductApp({needsSetup}: {needsSetup: boolean}) {
  const [setup, setSetup] = useState(needsSetup)
  const [session, updateSession] = useState<Session|null>(null)
  const [workspace, setWorkspace] = useState<Workspace|null>(null)
  const [team, setTeam] = useState<User[]>([])
  const [error, setError] = useState('')
  const [initial, setInitial] = useState(true)
  const [fresh, setFresh] = useState(false)
  const [view, setView] = useState(readView)
  const epoch = useRef(0)
  const refreshing = useRef(false)
  const locked = useRef((() => {try {return sessionStorage.getItem('shorefront.view_locked') === '1'} catch {return false}})())
  function lockView(value: boolean) {
    locked.current = value
    try {if (value) sessionStorage.setItem('shorefront.view_locked', '1'); else sessionStorage.removeItem('shorefront.view_locked')} catch { /* in-memory lock still applies */ }
  }
  const clearSession = useCallback(() => {epoch.current++; setSession(null); updateSession(null); setWorkspace(null); setTeam([]); setFresh(false)}, [])
  const adopt = useCallback((value: Session) => {setSession(value); updateSession(value); setSetup(false); setError('')}, [])
  const refresh = useCallback(async () => {
    if (locked.current) {setInitial(false); return}
    if (refreshing.current) return
    refreshing.current = true
    const generation = epoch.current
    try {
      const current = await productRequest<Session>('/auth/me')
      const [picture, members] = await Promise.all([productRequest<Workspace>('/workspace'), productRequest<User[]>('/team')])
      if (generation !== epoch.current) return
      if (!Array.isArray(members)) throw new Error('Invalid team response')
      adopt(current); setWorkspace(validateWorkspace(picture)); setTeam(members); setFresh(true); setError('')
    } catch (failure) {
      if (generation !== epoch.current) return
      setFresh(false)
      if (failure instanceof ProductError && failure.status === 401) clearSession()
      else setError(failure instanceof Error ? failure.message : 'Workspace could not be loaded')
      throw failure
    } finally {refreshing.current = false; setInitial(false)}
  }, [adopt, clearSession])
  useEffect(() => {void refresh().catch(() => {}); const timer = window.setInterval(() => {if (!document.hidden) void refresh().catch(() => {})}, 15000); return () => window.clearInterval(timer)}, [refresh])
  useEffect(() => {const navigate = () => setView(readView()); const expire = () => {clearSession(); setError('Your session has expired or access was revoked.')}; const offline = () => {setFresh(false); setError('Connection lost. This view may be stale; changes are disabled.')}; window.addEventListener('hashchange', navigate); window.addEventListener('shorefront:unauthorized', expire); window.addEventListener('offline', offline); return () => {window.removeEventListener('hashchange', navigate); window.removeEventListener('shorefront:unauthorized', expire); window.removeEventListener('offline', offline)}}, [clearSession])
  async function signOut() {
    epoch.current++
    lockView(true)
    try {await productRequest('/auth/logout', {}); clearSession(); setError('')}
    catch (failure) {clearSession(); setError(`Local view cleared. Server sign-out could not be confirmed; reconnect and sign in to revoke it. ${String(failure)}`)}
  }
  if (initial) return <div className="boot" role="status">SHOREFRONT<span>Checking workspace access…</span></div>
  if (!session) return <>{error && <p className="product-error" role="alert">{error}</p>}<SignIn setup={setup} onSession={value => {epoch.current++; lockView(false); adopt(value); void refresh().catch(() => {})}}/></>
  const writable = fresh && session.user.role !== 'viewer'
  const sessionEpoch = epoch.current
  return <div className="product-shell" key={session.user.id}><aside className="product-sidebar"><a href="#pulse" className="product-wordmark">SHOREFRONT<span>OPERATIONAL WORKSPACE</span></a><nav aria-label="Workspace">{views.map((item, index) => <a key={item} href={`#${item.toLowerCase()}`} aria-current={view === item ? 'page' : undefined}><span aria-hidden="true">0{index+1}</span>{item}</a>)}</nav><div className="product-sidebar-foot"><span className="product-index">PRIVATE INSTALLATION</span><strong>{session.user.name}</strong><small>{session.user.role}</small><button onClick={() => void signOut()}>Sign out</button></div></aside>
    <main><header className="product-topbar"><span className="product-index">{workspace?.installation_id ?? 'Loading workspace'} / {fresh ? 'CONNECTED' : 'NOT CURRENT'}</span><ThemeButton/></header>
      {error && <div className="product-error" role="alert">{error} <button onClick={() => void refresh().catch(() => {})}>Retry connection</button></div>}
      {!workspace ? <section className="product-empty" role="status"><h1>Loading your operational records…</h1><button onClick={() => void refresh().catch(() => {})}>Retry</button></section> : <>
        {view === 'Pulse' && <Pulse workspace={workspace} team={team}/>}
        {view === 'Records' && <ProductRecords facts={workspace.records} team={team} writable={writable} onSave={refresh}/>}
        {view === 'Plan' && <ProductDecisions facts={workspace.records} user={session.user} writable={writable} onRefresh={refresh}/>}
        {view === 'Evidence' && <Evidence/>}
        {view === 'Team' && <Team members={team} session={session} writable={fresh} onRefresh={refresh} onSession={value => {if (locked.current || sessionEpoch !== epoch.current) return; epoch.current++; adopt(value)}}/>}
      </>}
      <footer>SHOREFRONT · Advisory operations. Human authority. Preserved evidence.</footer>
    </main></div>
}
