"""按题目边界切图: 题干行顶格、选项行缩进, 只在题干起始处下刀"""
import fitz,io,numpy as np
from PIL import Image
def blocks_of(im_gray,dpi):
    a=np.array(im_gray); H,W=a.shape
    ink=(a<160)
    rs=ink.sum(axis=1); rows=rs>max(2,rs.max()*0.005)
    bl=[];s=None
    for y in range(H):
        if rows[y] and s is None: s=y
        elif not rows[y] and s is not None:
            if y-s>=6: bl.append((s,y)); s=None
    if s is not None: bl.append((s,H))
    mg=[]
    for b in bl:
        if mg and b[0]-mg[-1][1] < dpi*0.10: mg[-1]=(mg[-1][0],b[1])
        else: mg.append(b)
    out=[]
    for y0,y1 in mg:
        seg=ink[y0:y1]; cols=np.where(seg.any(axis=0))[0]
        out.append((y0,y1,int(cols[0]) if len(cols) else 10**6))
    return out,H,W
def question_chunks(pdf,page,dpi=300,max_frac=0.30):
    doc=fitz.open(pdf) if isinstance(pdf,str) else pdf
    pix=doc[page].get_pixmap(dpi=dpi)
    im=Image.open(io.BytesIO(pix.tobytes("png")))
    g=im.convert('L')
    bl,H,W=blocks_of(g,dpi)
    if not bl: return []
    lefts=[b[2] for b in bl if b[2]<10**5]
    if not lefts: return []
    base=np.percentile(lefts,20)          # 顶格位置
    starts=[i for i,b in enumerate(bl) if b[2] <= base+dpi*0.12]   # 题干起始块
    if not starts: starts=[0]
    groups=[]
    for k,i in enumerate(starts):
        j = starts[k+1] if k+1<len(starts) else len(bl)
        groups.append((bl[i][0], bl[j-1][1]))
    # 相邻小组打包, 不超过 max_frac 页高
    packs=[];cur=None
    for y0,y1 in groups:
        if cur and (y1-cur[0])/H <= max_frac: cur=(cur[0],y1)
        elif cur: packs.append(cur); cur=(y0,y1)
        else: cur=(y0,y1)
    if cur: packs.append(cur)
    pad=int(H*0.006)
    return [im.crop((0,max(0,a-pad),W,min(H,b+pad))) for a,b in packs]
if __name__=='__main__':
    doc=fitz.open("exams/raw/2026-07/2026年7月N1真题.pdf")
    n=0
    for p in range(3):
        cs=question_chunks(doc,p)
        n+=len(cs)
        print(f"页{p}: {len(cs)} chunk 高度占比 {[round(c.size[1]/ (doc[p].get_pixmap(dpi=300).height),2) for c in cs]}")
        for i,c in enumerate(cs): c.save(f"/tmp/qc_p{p}_{i}.png")
    print(f"前3页 {n} 个chunk")
