import {useRef, useState, type FormEvent} from 'react'
import {productRequest, type Fact} from './productClient'

// This checks file framing only. Typed values, authority, references and revisions
// remain the server's responsibility, inside one all-or-nothing transaction.
export default function ProductImport({writable, onSave}: {writable:boolean; onSave:()=>Promise<void>}) {
  const [file, setFile] = useState<File|null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')
  const attempt = useRef<{intent:string; key:string}|null>(null)
  async function submit(event:FormEvent) {
    event.preventDefault()
    if (!file || !writable || busy) return
    setBusy(true); setError(''); setResult('')
    try {
      if (file.size > 262144) throw new Error('Choose a JSON file smaller than 256 KiB.')
      let body:unknown
      try {body = JSON.parse(await file.text())} catch {throw new Error('This file is not valid JSON. Correct the file and select it again.')}
      if (!body || typeof body !== 'object' || !('records' in body) || !Array.isArray(body.records) || body.records.length < 1 || body.records.length > 100) throw new Error('The file must contain a records array with 1–100 entries.')
      const intent = JSON.stringify(body)
      if (attempt.current?.intent !== intent) attempt.current = {intent, key:crypto.randomUUID()}
      const saved = await productRequest<{records:Fact[]}>('/imports', body, attempt.current.key)
      setResult(`Imported ${saved.records.length} record${saved.records.length === 1 ? '' : 's'} atomically.`)
      await onSave()
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Could not import records. Your file is still selected.')}
    finally {setBusy(false)}
  }
  return <section className="product-editor" aria-label="Record import"><h2>Import your operational records</h2>
    <p>Choose a JSON batch of up to 100 records and 256 KiB. References must already exist or appear earlier in the batch. If any record fails validation, none of the batch is written.</p>
    <details><summary>View file format</summary><pre className="product-code">{JSON.stringify({records:[{kind:'vessel',command:{record_id:'your-vessel-id',expected_revision:0,source:'Your vessel register',payload:{name:'Your vessel name'}}}]},null,2)}</pre><p>Use expected_revision 0 for a new record, or its current revision for a correction. Keep record IDs stable when retrying an import.</p></details>
    <form onSubmit={submit} aria-busy={busy}><fieldset disabled={!writable || busy}><label>Record file<input type="file" accept="application/json,.json" required onChange={e => {setFile(e.target.files?.[0] ?? null); setError(''); setResult('')}}/></label>
      <button type="submit" className="product-primary" disabled={!file}>{busy ? 'Validating and importing…' : 'Validate and import'}</button></fieldset></form>
    {result && <p role="status">{result}</p>}{error && <p className="product-error" role="alert">{error}</p>}
  </section>
}
