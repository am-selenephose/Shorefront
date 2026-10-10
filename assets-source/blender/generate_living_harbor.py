import bpy, random, os
random.seed(27)
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'../../apps/web/public/assets/living-harbor'))
os.makedirs(ROOT,exist_ok=True)
def clean():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name, rgb, glow=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*rgb,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*rgb,1);bs.inputs['Roughness'].default_value=.75
    if glow:
        bs.inputs['Emission Color'].default_value=(*rgb,1);bs.inputs['Emission Strength'].default_value=glow
    return m
def box(name,pos,size,m):
    bpy.ops.mesh.primitive_cube_add(size=1,location=pos)
    o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(m)
    return o
def export(name):
    bpy.ops.export_scene.gltf(filepath=os.path.join(ROOT,name),export_format='GLB')
    print('EXPORTED',name,os.stat(os.path.join(ROOT,name)).st_size)
def empty(name,pos):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.location=pos
clean()
ground=material('Sunlit concrete',(.51,.50,.44));wall=material('Blue-grey quay stone',(.20,.30,.31))
dark=material('Asphalt',(.12,.19,.21));road=material('Lane markings',(.79,.76,.59))
metal=material('Golden cranes',(.87,.49,.22));metal2=material('Turquoise cranes',(.47,.77,.74))
lamp=material('Golden worklights',(.98,.74,.38),2)
palette=[material('Container-'+str(i),c) for i,c in enumerate(((.15,.43,.67),(.67,.29,.19),(.19,.48,.45),(.75,.55,.25),(.37,.39,.45)))]
# Fixed illustrative geometry, water comes from Three shader.
for idx,(x,y,sx,sy) in enumerate(((40,16,68,29),(44,-17,55,17),(53,-44,47,18),(-62,41,50,30),(-62,-42,53,26),(-7,52,37,13))):
    box('QUAY_%d_WALL'%idx,(x,y,0),(sx,sy,3.2),wall)
    box('QUAY_%d_SURFACE'%idx,(x,y,1.66),(sx-1,sy-1,.28),ground)
    for n in range(3):
        q=x-sx/2+7+n*max(4,(sx-10)/3)
        box('ROAD_%d_%d'%(idx,n),(q,y,1.83),(1.3,sy-4,.09),dark)
    for q in (-1,1):
        box('LANE_%d_%d'%(idx,q),(x,y+q*(sy/2-2),1.84),(sx-4,.22,.03),road)
for i,(x,y) in enumerate(((7,17),(12,-14),(20,-26),(38,-37))):
    empty('BERTH_B%d_ANCHOR'%(i+1),(x,y,2))
    box('BERTH_B%d_EDGE'%(i+1),(x,y,2),(1,13,.4),palette[i])
# Repeated container yard detail in terminal and far shoreline.
for label,origin,nx,ny in [('EAST',(24,-11),8,7),('WEST',(-82,29),7,4)]:
    for i in range(nx):
        for j in range(ny):
            h=random.choice((1,2,2,3))
            for k in range(h):
                box('%s_CONTAINER_%d_%d_%d'%(label,i,j,k),
                    (origin[0]+i*5.35,origin[1]+j*3.25,2.45+k*1.12),
                    (4.7,2.45,1.04),random.choice(palette))
for i,(x,y) in enumerate(((9,19),(10,-8),(19,-25),(40,-40),(2,53))):
    m=metal if i%2==0 else metal2
    for dx in (-3.4,3.4):
        for dy in (-2.0,2.0):
            box('CRANE_%d_LEG_%s_%s'%(i,dx,dy),(x+dx,y+dy,8),(.44,.44,12),m)
    box('CRANE_%d_GANTRY'%i,(x,y,14),(9,5,.75),m)
    box('CRANE_%d_BOOM'%i,(x-5,y,14.5),(23,.65,.75),m)
    box('CRANE_%d_HOIST'%i,(x-10,y,9.8),(.18,.18,8),dark)
for i in range(4):
    x=40+(i%2)*22;y=12+(i//2)*12
    box('WAREHOUSE_%d'%i,(x,y,4),(16,9,4.1),ground)
    box('WAREHOUSE_ROOF_%d'%i,(x,y,6.1),(16.4,9.4,.45),dark)
for i in range(65):
    x=random.choice((-1,1))*random.uniform(55,90)
    y=random.choice((-1,1))*random.uniform(31,65)
    if -45<x<75 and -51<y<30:continue
    h=random.uniform(2,11)
    box('CITY_BUILDING_%02d'%i,(x,y,2+h/2),(random.uniform(2,5),random.uniform(2,5),h),random.choice((ground,wall,dark)))
for i in range(55):
    x=random.uniform(-85,85)
    y=random.choice((-1,1))*random.uniform(30,62)
    box('HARBOR_LIGHT_POLE_%02d'%i,(x,y,6),(.15,.15,8),dark)
    box('HARBOR_LIGHT_%02d'%i,(x,y,10.1),(.48,.48,.5),lamp)
export('harbor_base.glb')
clean()
hull=material('Cargo hull naval',(.06,.19,.31));deck=material('Deck steel',(.46,.52,.51))
white=material('Bridge bone',(.83,.85,.78));blue=material('Windows cyan',(.29,.60,.64))
box('CARGO_SHIP_HULL',(0,0,.7),(6,22,2.2),hull)
box('CARGO_SHIP_DECK',(0,0,1.9),(5.7,21,.35),deck)
box('CARGO_SHIP_BRIDGE',(0,-8.4,3.4),(4.1,3.1,2.5),white)
box('CARGO_SHIP_WINDOWS',(0,-10.03,3.5),(3.6,.10,.6),blue)
for i in range(2):
  for j in range(6):
    for k in range((i+j)%3+1):
      box('SHIP_BOX_%d_%d_%d'%(i,j,k),(-1.4+i*2.8,-5+j*2.6,2.55+k*1.08),(2.5,2.2,1),palette[(i+j+k)%5])
export('cargo_ship.glb')
clean()
gold=material('Tug amber',(.88,.51,.20));tug=material('Tug marine dark',(.1,.3,.42))
box('TUG_HULL',(0,0,.6),(3.6,7.3,1.7),tug)
box('TUG_RUBBER_BUMPER',(0,0,.85),(4,7.5,.45),gold)
box('TUG_CABIN',(0,-.5,2.15),(2.5,2.7,2.1),white)
box('TUG_WINDOW',(0,1,2.5),(2.15,.11,.64),blue)
export('tug.glb')
clean()
pilot=material('Pilot blue',(.08,.42,.72))
box('PILOT_HULL',(0,0,.5),(2.1,5.8,1.5),pilot)
box('PILOT_DECK',(0,0,1.38),(1.8,5.4,.2),white)
box('PILOT_CABIN',(0,-.6,2),(1.5,2,1.2),white)
box('PILOT_WINDOW',(0,.45,2.1),(1.25,.08,.48),blue)
export('pilot.glb')
print('SHOREFRONT_ASSETS_READY')
