import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

test('operational and showcase CSS never declare sub-14px readable text',()=>{
  const files=['src/product.css','src/styles.css','src/ProductEvidence.css']
  for(const file of files){
    const css=readFileSync(file,'utf8')
    let declarations=0
    const failures=[]
    for(const match of css.matchAll(/\bfont(?:-size)?\s*:\s*([^;}]+)/g)){
      declarations++
      for(const size of match[1].matchAll(/(?<![\d.])(\d+(?:\.\d+)?)px\b/g)){
        if(Number(size[1])<14)
          failures.push(match[0].replace(/\s+/g,' ').slice(0,125))
      }
    }
    assert.ok(declarations>0,'Missing typographic rules: '+file)
    assert.deepEqual(failures,[],file+' reintroduced sub-14px text')
  }
})
