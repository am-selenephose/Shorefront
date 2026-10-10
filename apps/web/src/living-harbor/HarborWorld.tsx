import {Suspense,useMemo,useRef} from 'react'
import {Canvas,useFrame} from '@react-three/fiber'
import {Html,Line,OrbitControls,useGLTF} from '@react-three/drei'
import * as THREE from 'three'

export type WorldVessel={id:string;name:string;status:string;x:number;z:number;kind?:'cargo'|'tug'|'pilot'}
const ROOT='/assets/living-harbor/'
const vert='varying vec2 v;void main(){v=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}'
const frag='uniform float t;varying vec2 v;void main(){float wave=sin(v.x*120.+t*.6)*sin(v.y*80.-t*.2)*.042;float shine=pow(max(0.,1.-length((v-vec2(.56,.78))*vec2(.8,1.7))),5.);float stripes=pow(max(0.,sin(v.x*270.+v.y*120.+t*.3)),35.);vec3 c=mix(vec3(.025,.135,.195),vec3(.06,.28,.32),clamp(v.y*.45+.35+wave,0.,1.));c+=vec3(.45,.25,.1)*shine*(.4+stripes*.18);c+=stripes*.025;gl_FragColor=vec4(c,1.);}'
function Water({moving}:{moving:boolean}){
 const mat=useMemo(()=>new THREE.ShaderMaterial({uniforms:{t:{value:0}},vertexShader:vert,fragmentShader:frag}),[])
 useFrame(({clock})=>{if(moving)mat.uniforms.t.value=clock.elapsedTime})
 return <mesh rotation={[-Math.PI/2,0,0]} position={[0,-1.8,0]}><planeGeometry args={[270,230]}/><primitive object={mat} attach="material"/></mesh>
}
function Land(){const {scene}=useGLTF(ROOT+'harbor_base.glb');return <primitive object={scene} dispose={null}/>}
function Boat({record,selected,moving,onSelect}:{record:WorldVessel;selected:boolean;moving:boolean;onSelect:(id:string)=>void}){
 const path=record.kind==='tug'?'tug.glb':record.kind==='pilot'?'pilot.glb':'cargo_ship.glb'
 const {scene}=useGLTF(ROOT+path)
 const model=useMemo(()=>scene.clone(true),[scene])
 const ref=useRef<THREE.Group>(null)
 useFrame(({clock})=>{if(!ref.current)return;const t=clock.elapsedTime;ref.current.position.y=moving?Math.sin(t*.65+record.x)*.13:0
  if(record.kind==='tug'&&moving){ref.current.position.x=record.x+Math.cos(t*.19)*4;ref.current.position.z=record.z+Math.sin(t*.19)*5;ref.current.rotation.y=Math.sin(t*.19)*.2}
  if(record.kind==='pilot'&&moving){ref.current.position.x=record.x+Math.sin(t*.15)*5;ref.current.position.z=record.z+Math.cos(t*.15)*3}
 })
 return <group ref={ref} position={[record.x,0,record.z]} onClick={event=>{event.stopPropagation();onSelect(record.id)}}>
  <primitive object={model} scale={record.kind==='cargo'?.98:1}/>
  {selected&&<mesh rotation={[-Math.PI/2,0,0]} position={[0,-.8,0]}><ringGeometry args={[record.kind==='cargo'?12:5,record.kind==='cargo'?12.2:5.25,48]}/><meshBasicMaterial color="#27C9ED" side={THREE.DoubleSide} depthWrite={false}/></mesh>}
  {(selected||record.kind==='cargo')&&<Html position={[0,record.kind==='cargo'?9:5,0]} center><button className={'lh-world-tag '+(selected?'active':'')} onClick={()=>onSelect(record.id)}><span className="lh-dot"/>{record.name}<small>{record.status}</small></button></Html>}
 </group>
}
function HarborLights({moving}:{moving:boolean}){
 const group=useRef<THREE.Group>(null)
 useFrame(({clock})=>{if(!group.current)return;group.current.children.forEach((x,i)=>x.scale.setScalar(moving?.9+.1*Math.sin(clock.elapsedTime+i):1))})
 return <group ref={group}>{Array.from({length:20},(_,i)=><mesh key={i} position={[21+(i%8)*6,10,Math.floor(i/8)*21-36]}><sphereGeometry args={[.3,6,5]}/><meshBasicMaterial color="#ffd48b" toneMapped={false}/></mesh>)}</group>
}
function YardCars({moving}:{moving:boolean}){
 const ref=useRef<THREE.Group>(null)
 useFrame(({clock})=>{ref.current?.children.forEach((x,i)=>{x.position.x=24+(i%3)*9+(moving?Math.sin(clock.elapsedTime*.2+i)*5:0)})})
 return <group ref={ref}>{Array.from({length:6},(_,i)=><mesh key={i} position={[24+i%3*9,2.35,Math.floor(i/3)*25-22]}><boxGeometry args={[1.6,.7,.8]}/><meshStandardMaterial color={i%2?'#f3b34a':'#3dc9d0'}/></mesh>)}</group>
}
function World({vessels,selected,onSelect,moving,proposal,quality}:{vessels:WorldVessel[];selected:string|null;onSelect:(id:string)=>void;moving:boolean;proposal:boolean;quality:'high'|'balanced'}){return <><color attach="background" args={['#173C43']}/><fog attach="fog" args={['#6a7d7d',140,340]}/><ambientLight intensity={1.3} color="#dbeddf"/><hemisphereLight args={['#fff6e0','#174e59',1.1]}/><directionalLight intensity={3} position={[-45,80,-50]} color="#ffca80"/><directionalLight intensity={.6} position={[85,25,45]} color="#91d4ef"/><Water moving={moving}/><Suspense fallback={null}><Land/>{vessels.map(v=><Boat key={v.id} record={v} selected={selected===v.id} moving={moving} onSelect={onSelect}/>)}</Suspense>{quality==='high'&&<><HarborLights moving={moving}/><YardCars moving={moving}/></>}<Line points={[[-43,.12,-9],[-30,.12,3],[-8,.12,13]]} color="#3de5e5" lineWidth={1.7} dashed dashSize={.45} gapSize={.28}/>{proposal&&<Line points={[[0,.16,25],[14,.16,-9],[18,.16,-22]]} color="#ad95ff" lineWidth={2.2} dashed dashSize={.4} gapSize={.23}/>}<OrbitControls makeDefault enableRotate={false} enablePan enableZoom enableDamping target={[0,0,0]} minZoom={5} maxZoom={14}/></>}
export default function HarborWorld(props:{vessels:WorldVessel[];selected:string|null;onSelect:(id:string)=>void;moving:boolean;proposal:boolean;quality:'high'|'balanced';onWebGLError:()=>void}){
 return <div className="lh-world"  role="img" aria-label="Interactive fictional harbor diorama. Select any vessel using the accessible call list.">
  <Canvas orthographic camera={{position:[95,112,105],zoom:8,near:.1,far:800}} dpr={[1,1.5]} gl={{antialias:props.quality==='high',powerPreference:'high-performance'}} onCreated={({gl,camera})=>{camera.lookAt(0,0,0);gl.domElement.addEventListener('webglcontextlost',props.onWebGLError,{once:true})}}>
   <World vessels={props.vessels} selected={props.selected} onSelect={props.onSelect} moving={props.moving} proposal={props.proposal} quality={props.quality}/>
  </Canvas>
  <div className="lh-world-credit">3D DIORAMA · SIMULATED GEOMETRY · NOT NAVIGATIONAL</div>
 </div>
}
