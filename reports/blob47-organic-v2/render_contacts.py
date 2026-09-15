import runpy, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from sprite_builder.tilesets.patterns import _normalize_blob_mask
m=runpy.run_path('tests/unit/test_tileset_organic_blob_variants.py')
out=Path('reports/blob47-organic-v2'); tag=sys.argv[1]
results=[]
for profile in ('grass_over_dirt','dirt_over_water','grass_over_water'):
 a,s,c=m['_blob_sources'](16)
 if profile=='dirt_over_water': a.paste((112,76,48,255),(0,0,16,16))
 if profile!='grass_over_dirt': a.paste((42,100,125,255),(16,0,32,4))
 c.update(terrainProfile=profile,edgeVariation=3)
 r=m['build_tilesetter_terrain_pattern'](a,tile_size=(16,16),sources=s,set_config=c,kind='blob_47'); results.append(r)
 def panel(masks,name):
  cols=min(12,len(masks)); rows=(len(masks)+cols-1)//cols
  im=Image.new('RGBA',(cols*18,3*rows*18),(35,35,40,255))
  for v in range(3):
   for i,mask in enumerate(masks): im.paste(Image.fromarray(m['_tile_pixels'](r,mask,v)),((i%cols)*18,(v*rows+i//cols)*18))
  # Integer pixel replication for inspection only; native exports remain untouched.
  Image.fromarray(np.repeat(np.repeat(np.asarray(im),8,0),8,1)).save(out/f'{tag}-{profile}-{name}.png')
 r.image.save(out/f'{tag}-{profile}-native.png')
 panel([t.mask for t in r.tiles if t.variant==0],'atlas')
 panel([28,112,193,7],'outer'); panel([247,223,127,253],'inner')
 grid=np.zeros((11,13),bool); grid[2:9,2:11]=True; grid[4:7,5:8]=False; grid[2,2]=False; grid[8,10]=False
 im=Image.new('RGBA',(13*16,11*16),(112,76,48,255) if profile=='grass_over_dirt' else (42,100,125,255))
 for y,x in zip(*np.where(grid)):
  mask=0
  for bit,(dy,dx) in enumerate(((-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1))):
   if grid[y+dy,x+dx]: mask|=1<<bit
  im.paste(Image.fromarray(m['_tile_pixels'](r,_normalize_blob_mask(mask),(x+y)%3)),(x*16,y*16))
 Image.fromarray(np.repeat(np.repeat(np.asarray(im),4,0),4,1)).save(out/f'{tag}-{profile}-mosaic.png')
comparison=Image.new('RGBA',(4*18*8,3*18*8))
for i,p in enumerate(('grass_over_dirt','dirt_over_water','grass_over_water')):
 im=Image.open(out/f'{tag}-{p}-outer.png'); comparison.paste(im.crop((0,0,im.width,144)),(0,i*144))
comparison.save(out/f'{tag}-profiles.png')
