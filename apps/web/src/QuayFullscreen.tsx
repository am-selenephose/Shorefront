import {useEffect,useRef,useState,type ReactNode} from 'react'

type Props={
  className:string
  label:string
  heading:ReactNode
  tools?:ReactNode
  children:ReactNode
}

/** Quay-specific, independent timeline fullscreen. Never mutates call records. */
export default function QuayFullscreen({className,label,heading,tools,children}:Props){
  const container=useRef<HTMLElement|null>(null)
  const [native,setNative]=useState(false)
  const [fallback,setFallback]=useState(false)
  const expanded=native||fallback

  useEffect(()=>{
    const onNativeChange=()=>setNative(document.fullscreenElement===container.current)
    const onKey=(event:KeyboardEvent)=>{
      if(event.key!=='Escape')return
      if(fallback){
        event.preventDefault()
        setFallback(false)
      }else if(document.fullscreenElement===container.current){
        void document.exitFullscreen().catch(()=>{})
      }
    }
    document.addEventListener('fullscreenchange',onNativeChange)
    document.addEventListener('keydown',onKey)
    return()=>{
      document.removeEventListener('fullscreenchange',onNativeChange)
      document.removeEventListener('keydown',onKey)
      if(document.fullscreenElement===container.current)
        void document.exitFullscreen().catch(()=>{})
    }
  },[fallback])

  useEffect(()=>{
    if(!fallback)return
    const previous=document.body.style.overflow
    document.body.style.overflow='hidden'
    return()=>{document.body.style.overflow=previous}
  },[fallback])

  async function toggle(){
    if(document.fullscreenElement===container.current){
      await document.exitFullscreen()
      return
    }
    if(fallback){setFallback(false);return}
    if(container.current?.requestFullscreen){
      try{
        await container.current.requestFullscreen()
        return
      }catch{
        // Embedded/mobile browser refused native fullscreen.
      }
    }
    setFallback(true)
  }

  return <section ref={container}
    className={className+' quay-fullscreen'+(fallback?' is-quay-expanded':'')}
    data-quay-expanded={expanded?'true':'false'}
    role="region"
    aria-label={label}>
    <header className="quay-panel-header">
      {heading}
      <div className="quay-panel-tools">
        {tools}
        <button type="button" className="quay-expand-button"
          aria-label={expanded?'Exit full screen quay':'Full screen quay'}
          aria-pressed={expanded} onClick={()=>void toggle()}>
          <span aria-hidden="true">{expanded?'↙':'⛶'}</span>
          {expanded?'Exit full screen':'Full screen'}
        </button>
      </div>
    </header>
    <div className="quay-fullscreen-body">{children}</div>
    {expanded&&<div className="quay-fullscreen-boundary" role="note">
      <span>RECORDED BERTH WINDOWS</span>
      <span>Source-backed timeline, not navigation clearance. Press Esc or Exit full screen to return.</span>
    </div>}
  </section>
}
