#!/usr/bin/env python3
"""Pixel-level sheet/atlas geometry and mask checks. Does not prove visual correctness."""
import sys,json
from pathlib import Path
from PIL import Image

def main():
    if len(sys.argv)!=3:
        print('Usage: validate_sheet_atlas.py image.png atlas.json');return 2
    image=Image.open(sys.argv[1]).convert('RGBA'); meta=json.loads(Path(sys.argv[2]).read_text())
    w,h=image.size
    bad=[]
    size=meta.get('image_size',meta.get('canvas_size',meta.get('size')))
    if isinstance(size,dict):s=(size.get('width'),size.get('height'))
    elif isinstance(size,list):s=tuple(size[:2])
    else:s=None
    if s and s!=(w,h):bad.append(f'canvas metadata {s} != actual {(w,h)}')
    for i,f in enumerate(meta.get('frames',[])):
        rect=f.get('rect',f.get('frame'))
        if isinstance(rect,dict): rect=[rect.get(k) for k in ('x','y','w','h')]
        if not isinstance(rect,list) or len(rect)!=4 or any(type(v) is not int for v in rect):bad.append(f'frame {i}: missing/invalid rect');continue
        x,y,cw,ch=rect
        if x<0 or y<0 or cw<=0 or ch<=0 or x+cw>w or y+ch>h:bad.append(f'frame {i}: out-of-bounds rectangle')
    if not meta.get('frames'):bad.append('no frames list (cannot verify atlas)')
    # All delivered source PNGs must be fully opaque; actual visible pixels may have any non-key color.
    alpha=image.getchannel('A').getextrema()
    if alpha!=(255,255):bad.append(f'alpha not fully opaque: {alpha}')
    bg=meta.get('mask_color',meta.get('background_color'))
    if bg and str(bg).upper()!='#FF00FF':bad.append(f'mask color mismatch: {bg}')
    # Key-background corner check is intentionally not mandatory: some valid sprites touch corners.
    if bad:
        for b in bad:print('FAIL',b)
        return 1
    print(f'PASS geometric/alpha checks: {w}x{h}, frames={len(meta["frames"])}. Visual pixel mask correctness NOT proven.');return 0
if __name__=='__main__':sys.exit(main())