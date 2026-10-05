import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import ProductRecords, {RecordEditor} from './ProductRecords'
import ProductCoordination from './ProductCoordination'
import ProductEvidence from './ProductEvidence'
import ProductDecisions from './ProductDecisions'
import ProductAccount from './ProductAccount'
import {OperationalCalls, OperationalExceptions, OperationalPlan, OperationalPulse} from './ProductWorkspaces'
import {ProductError, productRequest, setSession, validateWorkspace, type Fact, type Session, type User, type Workspace} from './productClient'
import './product.css'

const views = ['Pulse', 'Plan', 'Calls', 'Exceptions', 'Coordination', 'Recovery', 'Records', 'Evidence', 'Team'] as const
type View = typeof views[number]
function readView(): View {return views.find(v => `#${v.toLowerCase()}` === location.hash) ?? 'Pulse'}
function ThemeButton() {
  const [dark, setDark] = useState(document.documentElement.dataset.theme === 'dark')
  return <button onClick={() => {const theme = dark ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; setDark(!dark); try {localStorage.setItem('shorefront.theme', theme)} catch { /* theme still works for this visit */ }}} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? 'Light mode' : 'Dark mode'}</button>
}

function readSetupToken() {
  if (!location.hash.startsWith('#setup=')) return ''
  return decodeURIComponent(location.hash.slice('#setup='.length))
}


function SignIn({setup, onSession}: {setup: boolean; onSession: (value: Session) => void}) {
  const [invite, setInvite] = useState(false)
  const [setupToken] = useState(() => setup ? readSetupToken() : '')
  useEffect(() => {
    if (setupToken && location.hash.startsWith('#setup=')) history.replaceState(null, '', location.pathname + location.search)
  }, [setupToken])
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const data = Object.fromEntries(new FormData(event.currentTarget))
    if (setup && setupToken) data.bootstrap_token = setupToken
    try {onSession(await productRequest<Session>(setup ? '/auth/bootstrap' : invite ? '/auth/accept' : '/auth/login', data))}
    catch (failure) {setError(failure instanceof Error ? failure.message : 'Sign-in failed')}
    finally {setBusy(false)}
  }
  return <div className="product-login"><header><a className="product-wordmark" href="/">SHOREFRONT<span>OPERATIONS, WITH A RECORD.</span></a><ThemeButton/></header>
    <main><section className="product-login-intro"><span className="product-index">YOUR PRIVATE OPERATIONAL WORKSPACE</span><h1>{setup ? 'Open your operational workspace' : invite ? 'Join your team' : 'Sign in to Shorefront'}</h1><p>One shared picture. Accountable decisions. A history that stays intact.</p><div className="product-rule"/><p className="product-small">This installation starts with your data. Nothing here is filled with demo vessels, synthetic weather, or invented outcomes.</p></section>
      <section className="product-login-form"><p className="eyebrow">{setup ? 'INSTALLATION SETUP' : invite ? 'INVITATION' : 'SECURE ACCESS'}</p><form onSubmit={submit} aria-busy={busy}><fieldset disabled={busy}>
        {setup && !setupToken && <label>Setup token<input name="bootstrap_token" type="password" required autoComplete="off"/><small>Use the one-time setup link from your installation operator, or enter its recovery token here.</small></label>}
        {setup && setupToken && <div className="product-setup-verified"><b>Installation access verified</b><span>Create the first administrator. The setup secret has been removed from the address bar.</span></div>}
        {invite && !setup && <label>Invitation token<input name="invitation_token" type="password" required autoComplete="off"/></label>}
        {(setup || invite) && <label>Full name<input name="display_name" required maxLength={200} autoComplete="name"/></label>}
        <label>Email<input name="email" type="email" required autoComplete="email" maxLength={254} spellCheck={false}/></label>
        <label>Password<input name="password" aria-label="Password" aria-describedby={setup || invite ? 'password-help' : undefined} type={showPassword ? 'text' : 'password'} required minLength={setup || invite ? 15 : 1} maxLength={128} autoComplete={setup || invite ? 'new-password' : 'current-password'}/></label>{(setup || invite) && <small id="password-help">At least 15 characters. A memorable passphrase works well.</small>}
        <button className="product-quiet" type="button" onClick={() => setShowPassword(!showPassword)}>{showPassword ? 'Hide password' : 'Show password'}</button>
        {error && <p className="product-error" role="alert">{error}</p>}
        <button className="product-primary" type="submit">{busy ? 'Please wait…' : setup ? 'Create workspace' : invite ? 'Accept invitation' : 'Sign in'}</button>
      </fieldset></form>{!setup && <button className="product-quiet" onClick={() => {setInvite(!invite); setError('')}}>{invite ? 'Back to sign in' : 'I have an invitation'}</button>}<a className="product-showcase-link" href="/?showcase=1">Explore Shorefront demo</a><p className="product-small">Access is granted by your organisation. Contact your installation operator if you need account recovery.</p></section></main>
    </div>
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

function ContextEditor({record,kind,payload,facts,team,writable,onSave,onCancel}: {record:Fact|null;kind:string;payload?:Fact['payload'];facts:Fact[];team:User[];writable:boolean;onSave:()=>Promise<void>;onCancel:()=>void}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(()=>{const node=dialog.current; node?.showModal(); return ()=>node?.close()},[])
  return <dialog ref={dialog} className="product-context-dialog" aria-label="Operational record" onCancel={onCancel}>
    <RecordEditor record={record} initialKind={kind} initialPayload={payload} fixedKind facts={facts} team={team} writable={writable} onSave={onSave} onCancel={onCancel}/>
  </dialog>
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
  const [editor,setEditor] = useState<{record:Fact|null;kind:string;payload?:Fact['payload'];id:string}|null>(null)
  const epoch = useRef(0)
  const refreshing = useRef(false)
  const locked = useRef((() => {try {return sessionStorage.getItem('shorefront.view_locked') === '1'} catch {return false}})())
  function lockView(value: boolean) {
    locked.current = value
    try {if (value) sessionStorage.setItem('shorefront.view_locked', '1'); else sessionStorage.removeItem('shorefront.view_locked')} catch { /* in-memory lock still applies */ }
  }
  const clearSession = useCallback(() => {epoch.current++; setSession(null); updateSession(null); setWorkspace(null); setTeam([]); setFresh(false); setEditor(null)}, [])
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
  useEffect(() => {const navigate = () => setView(readView()); const expire = () => {clearSession(); setError('Your session has expired or access was revoked.')}; const offline = () => {setFresh(false); setError('Connection lost. This view may be stale; changes are disabled.')}; window.addEventListener('hashchange', navigate); navigate(); window.addEventListener('shorefront:unauthorized', expire); window.addEventListener('offline', offline); return () => {window.removeEventListener('hashchange', navigate); window.removeEventListener('shorefront:unauthorized', expire); window.removeEventListener('offline', offline)}}, [clearSession])
  async function signOut() {
    epoch.current++
    lockView(true)
    try {await productRequest('/auth/logout', {}); clearSession(); setError('')}
    catch (failure) {clearSession(); setError(`Local view cleared. Server sign-out could not be confirmed; reconnect and sign in to revoke it. ${String(failure)}`)}
  }
  if (initial) return <div className="boot" role="status">SHOREFRONT<span>Checking workspace access…</span></div>
  if (!session) return <>{error && <p className="product-error" role="alert">{error}</p>}<SignIn setup={setup} onSession={value => {epoch.current++; lockView(false); adopt(value); void refresh().catch(() => {})}}/></>
  const writable = fresh && session.user.role !== 'viewer'
  const actions = {writable,onCreate:(kind:string,payload?:Fact['payload'])=>setEditor({record:null,kind,payload,id:crypto.randomUUID()}),onEdit:(record:Fact)=>setEditor({record,kind:record.kind,id:crypto.randomUUID()})}
  const sessionEpoch = epoch.current
  return <div className="product-shell" key={session.user.id}><aside className="product-sidebar"><a href="#pulse" className="product-wordmark">SHOREFRONT<span>OPERATIONAL WORKSPACE</span></a><nav aria-label="Workspace">{views.map((item, index) => <a key={item} href={`#${item.toLowerCase()}`} aria-current={view === item ? 'page' : undefined}><span aria-hidden="true">0{index+1}</span>{item}</a>)}</nav><div className="product-sidebar-foot"><span className="product-index">PRIVATE INSTALLATION</span><strong>{session.user.name}</strong><small>{session.user.role}</small><button onClick={() => void signOut()}>Sign out</button></div></aside>
    <main><header className="product-topbar"><span className="product-index">{workspace?.installation_id ?? 'Loading workspace'} / {fresh ? 'CONNECTED' : 'NOT CURRENT'}</span><ThemeButton/></header>
      {error && <div className="product-error" role="alert">{error} <button onClick={() => void refresh().catch(() => {})}>Retry connection</button></div>}
      {!workspace ? <section className="product-empty" role="status"><h1>Loading your operational records…</h1><button onClick={() => void refresh().catch(() => {})}>Retry</button></section> : <>
        {view === 'Pulse' && <OperationalPulse workspace={workspace} team={team} {...actions}/>}
        {view === 'Plan' && <><OperationalPlan workspace={workspace} {...actions}/><div className="ops-decision-review"><ProductDecisions facts={workspace.records} user={session.user} writable={writable} onRefresh={refresh}/></div></>}
        {view === 'Calls' && <OperationalCalls workspace={workspace} {...actions}/>}
        {view === 'Exceptions' && <OperationalExceptions workspace={workspace} team={team} {...actions}/>}
        {view === 'Coordination' && <ProductCoordination facts={workspace.records} team={team} writable={writable} onRefresh={refresh} onCreate={actions.onCreate}/>}
        {view === 'Recovery' && <ProductDecisions facts={workspace.records} user={session.user} writable={writable} onRefresh={refresh}/>}
        {view === 'Records' && <ProductRecords facts={workspace.records} team={team} writable={writable} onSave={refresh}/>}
        {view === 'Evidence' && <ProductEvidence facts={workspace.records} team={team}/>}
        {view === 'Team' && <Team members={team} session={session} writable={fresh} onRefresh={refresh} onSession={value => {if (locked.current || sessionEpoch !== epoch.current) return; epoch.current++; adopt(value)}}/>}
        {editor && <ContextEditor key={editor.id} record={editor.record} kind={editor.kind} payload={editor.payload} facts={workspace.records} team={team} writable={writable} onCancel={()=>setEditor(null)} onSave={async()=>{await refresh();setEditor(null)}}/>}
      </>}
      <footer>SHOREFRONT · Advisory operations. Human authority. Preserved evidence.</footer>
    </main></div>
}
