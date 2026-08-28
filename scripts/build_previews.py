import json
from pathlib import Path
from PIL import Image, ImageEnhance
import numpy as np
import rasterio


def stretch(a, lo=2, hi=98):
    a=a.astype('float32')
    p1,p2=np.nanpercentile(a,[lo,hi])
    if p2<=p1: return np.zeros_like(a,dtype='uint8')
    return (np.clip((a-p1)/(p2-p1),0,1)*255).astype('uint8')


def preview(rgb_paths, output, max_size=1400):
    chans=[]
    for p in rgb_paths:
        with rasterio.open(p) as s:
            x=s.read(1,masked=True).filled(np.nan)
            chans.append(stretch(x))
    arr=np.dstack(chans)
    im=Image.fromarray(arr,'RGB')
    im.thumbnail((max_size,max_size))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    im.save(output,quality=88,optimize=True)


def main():
    import argparse
    ap=argparse.ArgumentParser(description='Create RGB/false-color preview from three co-registered single-band rasters')
    ap.add_argument('bands',nargs=3,help='Three raster paths in display R,G,B order')
    ap.add_argument('--output',required=True)
    a=ap.parse_args(); preview(a.bands,a.output)

if __name__=='__main__': main()
