#!/usr/bin/env python3
"""按场次跑全科评估，输出每卷三科得分与是否过线（100/180 且三科≥19）"""
import sys,os,glob,re,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import solve as S
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# JLPT 换算: 言語知識+読解 各占 60 分(合计120)，聴解 60 分。按题数线性折算。
SCALE={'言語知識':60,'読解':60,'聴解':60}
sess=sorted({os.path.basename(f).rsplit('_',1)[0] for f in glob.glob(f'{ROOT}/converted/*.txt')})
G=collections.defaultdict(lambda:[0,0,0]); ROUTE=collections.defaultdict(lambda:[0,0])
rows=[]
for s in sess:
    per={}
    for sec in ('言語知識','読解','聴解'):
        p=f'{ROOT}/converted/{s}_{sec}.txt'
        if not os.path.exists(p): continue
        exp=0.0; n=0
        for q,pick,meth in S.run(p):
            k=(q['sec'] or '?')+'|'+(q['dai'] or '?')
            g=G[k]; g[2]+=1; n+=1
            if pick:
                g[1]+=1; ok=bool(q['ans'] and pick==q['ans'])
                g[0]+=ok; exp+=ok
                r=ROUTE[meth or '?']; r[1]+=1; r[0]+=ok
            else: exp+=0.25
        per[sec]=(exp,n)
        print(f"  {s}_{sec}: {exp:.1f}/{n}",flush=True)
    rows.append((s,per))
print(f"\n{'场次':<10}{'言語知識':>12}{'読解':>12}{'聴解':>12}{'总分/180':>11}{'判定':>8}")
print('-'*68)
for s,per in rows:
    tot=0; ok=True; cells=[]
    for sec in ('言語知識','読解','聴解'):
        if sec not in per: cells.append('—'); ok=False; continue
        e,n=per[sec]; sc=e/n*SCALE[sec]
        cells.append(f"{e:.1f}/{n}({sc:.0f})")
        tot+=sc
        if sc<19: ok=False
    v='✅过' if (ok and tot>=100) else ('✗未过' if len(per)==3 else '数据缺')
    print(f"{s:<10}{cells[0]:>13}{cells[1]:>13}{cells[2]:>13}{tot:>10.0f}{v:>9}")
print(f"\n{'科目|大題':<26}{'出手':>9}{'正确率':>9}   期望分")
T=[0.0,0]
for k in sorted(G):
    a,f,n=G[k]; exp=a+(n-f)*0.25; T[0]+=exp; T[1]+=n
    print(f"{k:<26}{f}/{n:<5}{100*a/f if f else 0:>7.1f}%   {exp:>6.1f}/{n}")
print(f"{'合计':<26}{'':>9}{'':>9}   {T[0]:.1f}/{T[1]} = {100*T[0]/T[1]:.1f}%")
print(f"\n{'路线':<24}{'出手':>7}{'正确':>7}{'正确率':>9}{'比蒙多拿':>10}")
for m,(a,n) in sorted(ROUTE.items(),key=lambda kv:-kv[1][0]):
    print(f"{m:<24}{n:>7}{a:>7}{100*a/n:>8.1f}%{a-n*0.25:>9.1f}题")
