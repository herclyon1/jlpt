#!/usr/bin/env python3
"""把聴解文件的題号从连续 1-30 改成按大題重新编号（与库内既有格式一致）"""
import re,sys
def renum(p):
    lines=open(p,encoding='utf-8').read().split('\n')
    out=[]; dai=None; k=0; changed=0
    for l in lines:
        m=re.match(r'^#大題 問題(\d+)',l)
        if m: dai=int(m.group(1)); k=0; out.append(l); continue
        m=re.match(r'^#題 (\d+)(.*)$',l)
        if m and dai:
            k+=1
            new=f'#題 {k}{m.group(2)}'
            if new!=l: changed+=1
            out.append(new); continue
        out.append(l)
    open(p,'w',encoding='utf-8').write('\n'.join(out))
    return changed
if __name__=='__main__':
    for p in sys.argv[1:]:
        print(f"{p}: 改号 {renum(p)} 处")
