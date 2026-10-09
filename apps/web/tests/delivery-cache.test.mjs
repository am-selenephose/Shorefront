// Real Nginx delivery checks. Uses a prebuilt local image, disposable containers,
// loopback ports and no operational database/network or browser credentials.
import {execFileSync} from 'node:child_process'
import {mkdtempSync, readFileSync, writeFileSync, unlinkSync, rmdirSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
import http from 'node:http'
import https from 'node:https'
import assert from 'node:assert/strict'
import {test} from 'node:test'

const webRoot = fileURLToPath(new URL('..', import.meta.url))
const image = process.env.SHOREFRONT_TEST_WEB_IMAGE || 'shorefront-web:local'
const docker = (...args) => execFileSync('docker', args, {encoding:'utf8', timeout:30000}).trim()
function get(url, headers={}) {
  return new Promise((resolve,reject) => {
    const client=url.startsWith('https:')?https:http
    const request=client.get(url,{headers,rejectUnauthorized:false},response=>{
      response.resume()
      response.on('end',()=>resolve({status:response.statusCode,headers:response.headers}))
    })
    request.setTimeout(3000,()=>request.destroy(new Error('Local Nginx response timed out')))
    request.on('error',reject)
  })
}

for(const tls of [false,true]) test(`${tls?'TLS':'HTTP'} entry points revalidate after deployment without losing security headers`,async()=>{
  const directory=mkdtempSync(join(tmpdir(),'shorefront-delivery-test-'))
  const files=[]
  let container=''
  try {
    const name=tls?'nginx.tls.conf.template':'nginx.conf'
    const config=join(directory,'nginx.conf')
    writeFileSync(config,readFileSync(join(webRoot,name),'utf8').replaceAll('${SHOREFRONT_PUBLIC_HTTPS_ORIGIN}','https://localhost'))
    files.push(config)
    if(tls) {
      files.push(join(directory,'tls.key'),join(directory,'tls.crt'))
      execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
        '-keyout',join(directory,'tls.key'),'-out',join(directory,'tls.crt')],{stdio:'pipe',timeout:30000})
    }
    const port=tls?443:80
    container=docker('run','--rm','--pull=never','-d','--add-host','api:127.0.0.1',
      '-p',`127.0.0.1::${port}`,'--mount',`type=bind,source=${config},target=/etc/nginx/conf.d/default.conf,readonly`,
      '--mount',`type=bind,source=${directory},target=/etc/nginx/tls,readonly`,image)
    assert.match(container,/^[a-f0-9]{64}$/)
    const bindings=JSON.parse(docker('inspect','--format','{{json .NetworkSettings.Ports}}',container))
    const base=`${tls?'https':'http'}://127.0.0.1:${bindings[`${port}/tcp`][0].HostPort}`
    let ready=false
    for(let attempt=0;attempt<30;attempt++) {
      try {ready=(await get(base+'/')).status===200;if(ready)break} catch {}
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert.ok(ready,'Disposable Nginx must start before header assertions')
    for(const path of ['/','/?showcase=1','/index.html','/workspace/deep-link','/theme-init.js']) {
      const response=await get(base+path)
      assert.equal(response.status,200,path)
      assert.equal(response.headers['cache-control'],'no-cache',`${name} ${path} must revalidate`)
      assert.equal(response.headers['x-content-type-options'],'nosniff')
      assert.equal(response.headers['x-frame-options'],'DENY')
      assert.equal(response.headers['referrer-policy'],'no-referrer')
      if(tls)assert.match(response.headers['strict-transport-security'],/max-age=/)
    }
    const metrics=await get(base+'/metrics')
    assert.equal(metrics.status,404,'Operational metrics must remain private to the API network')
    const initial=await get(base+'/index.html')
    const conditional=await get(base+'/index.html',{'If-Modified-Since':initial.headers['last-modified']})
    assert.equal(conditional.status,304,'Unchanged shells may be conditionally revalidated')
    assert.equal(conditional.headers['cache-control'],'no-cache')
  } finally {
    if(/^[a-f0-9]{64}$/.test(container))docker('stop','--time','1',container)
    for(const path of files)unlinkSync(path)
    rmdirSync(directory)
  }
})
