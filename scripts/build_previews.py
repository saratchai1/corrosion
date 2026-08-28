from pathlib import Path
from PIL import Image
import numpy as np
import rasterio


def stretch(a, lo=2, hi=98):
    a=a.astype('float32')
    p1,p2=np.nanpercentile(a,[lo,hi])
    if p2<=p1: return np.zeros_like(a,dtype='uint8')
    scaled=np.clip((a-p1)/(p2-p1),0,1)*255
    return np.nan_to_num(scaled,nan=0.0,posinf=255.0,neginf=0.0).astype('uint8')


def preview(rgb_paths, output, max_size=1400):
    chans=[]
    for p in rgb_paths:
        with rasterio.open(p) as s:
            # Convert integer reflectance/backscatter rasters before filling
            # masked pixels with NaN for percentile stretching.
            x=s.read(1, masked=True).astype("float32").filled(np.nan)
            chans.append(stretch(x))
    if len(chans) == 1:
        im=Image.fromarray(chans[0], 'L')
    elif len(chans) == 3:
        arr=np.dstack(chans)
        im=Image.fromarray(arr,'RGB')
    else:
        raise ValueError('preview requires one grayscale band or three RGB bands')
    im.thumbnail((max_size,max_size))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    im.save(output,quality=88,optimize=True)


def main():
    import argparse
    ap=argparse.ArgumentParser(description='Create a grayscale or RGB/false-color preview from co-registered single-band rasters')
    ap.add_argument('bands',nargs='+',help='One grayscale band or three raster paths in display R,G,B order')
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    if len(a.bands) not in (1, 3):
        ap.error('provide exactly one grayscale band or three RGB bands')
    preview(a.bands,a.output)

if __name__=='__main__': main()
