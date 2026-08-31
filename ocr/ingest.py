#!/usr/bin/env python3
"""把 sonnet 转写产物 + 答案表合并入库 converted/。
用法: python3 ocr/ingest.py <场次> [<场次>...]
- 选项编号按位置归一化为 1/2/3/4（原卷印错的编号记入 DEVIATIONS.md）
- 从答案表合并 #答
- 入库后跑 check_format.py
"""
import re,sys,os,json,glob,subprocess,collections
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,'/tmp/ans2')
def load_answers(sess,want,key):
    """两个解析器 × 多个来源，选对目标題号覆盖最好的那个"""
    try:
        from parse import solve
        from parse2 import solve2
    except Exception as e:
        print(f"    解析器导入失败 {e}"); return {}
    cands=[]
    for f in sorted(glob.glob(f'/tmp/ans2/{sess}_src*.txt')):
        txt=open(f,encoding='utf-8').read()
        try: a1,_=solve(txt)
        except Exception: a1={}
        try: a2=solve2(txt)
        except Exception: a2={}
        for tag,a in (('分组',a1),('番号',a2)):
            cov=sum(1 for q in want if (key,q) in a)
            cands.append((cov,tag,os.path.basename(f),a))
    if not cands: return {}
    cands.sort(key=lambda x:-x[0])
    cov,tag,src,a=cands[0]
    # 第二名若同样满覆盖，做一致性检查
    agree=None
    for c2,t2,s2,a2 in cands[1:]:
        if c2==cov and (s2!=src or t2!=tag):
            same=sum(1 for q in want if a.get((key,q))==a2.get((key,q)))
            agree=f"，与「{s2}/{t2}」一致 {same}/{len(want)}"
            break
    print(f"    答案源: {src}/{tag}  覆盖 {cov}/{len(want)}{agree or ''}")
    return a

def process(sess,sec,dev):
    src=f'/tmp/run/{sess}/{sec}.txt'
    if not os.path.exists(src): print(f"  {sess}_{sec}: 无转写产物"); return False
    want=[int(m.group(1)) for m in re.finditer(r'^#題\s+(\d+)',open(src,encoding='utf-8').read(),re.M)]
    key='L' if sec in ('言語知識','読解') else 'T'
    ans=load_answers(sess,want,key)
    if not ans:
        # 找不到答案源时，保留目标文件里已有的答案，不要清空
        old=f'{ROOT}/converted/{sess}_{sec}.txt'
        if os.path.exists(old):
            cur2=None
            for l in open(old,encoding='utf-8'):
                m2=re.match(r'^#題 (\d+)',l)
                if m2: cur2=int(m2.group(1))
                if l.startswith('#答') and cur2: ans[(key,cur2)]=l[3:].strip()
            if ans: print(f"    无答案源 → 保留原文件已有的 {len(ans)} 个答案")
    out=[]; qn=None; optn=0; body=open(src,encoding='utf-8').read().split('\n')
    if not body[0].startswith('#卷'): out.append(f'#卷 {sess} N1')
    for l in body:
        m=re.match(r'^#選\s',l)
        if m: l='#选 '+l[2:].lstrip()
        if l.startswith('#題'):
            mm=re.match(r'^#題\s+(\d+)',l); qn=int(mm.group(1)) if mm else None; optn=0
            out.append(l); continue
        if l.startswith('#选'):
            mm=re.match(r'^#选\s+(\d+)\s+(.*)$',l)
            if mm:
                optn+=1
                if int(mm.group(1))!=optn:
                    dev.append(f"{sess} {sec} 題{qn} 第{optn}个选项纸上印的编号是 {mm.group(1)}（已归一化为 {optn}）")
                out.append(f'#选 {optn} {mm.group(2)}')
            else: out.append(l)
            continue
        out.append(l)
    # 插入 #答
    res=[]; pend=None
    for l in out:
        mm=re.match(r'^#題\s+(\d+)',l)
        if mm:
            if pend is not None:
                v=ans.get((key,pend))
                if v: res.append(f'#答 {v}')
            pend=int(mm.group(1))
        res.append(l)
    if pend is not None:
        v=ans.get((key,pend))
        if v: res.append(f'#答 {v}')
    txt='\n'.join(x for x in res if x is not None)
    txt=re.sub(r'\n{3,}','\n\n',txt)
    dst=f'{ROOT}/converted/{sess}_{sec}.txt'
    open(dst,'w',encoding='utf-8').write(txt.rstrip()+'\n')
    r=subprocess.run([sys.executable,f'{ROOT}/ocr/check_format.py',dst],capture_output=True,text=True)
    ok='✅ 通过' in r.stdout
    if not ok:
        r2=subprocess.run([sys.executable,f'{ROOT}/ocr/check_format.py',dst,'--loose'],capture_output=True,text=True)
        if '✅ 通过' in r2.stdout:
            ok=True; r=r2
            dev.append(f"{sess} {sec}: 題数非标准（重排卷），已用 --loose 通过；実際 "
                       +", ".join(f"問題{d}={c}" for d,c in sorted(collections.Counter(
                         re.findall(r'^#大題 問題(\d+)',txt,re.M)).items())) if False else
                       f"{sess} {sec}: 題数非标准（重排卷），已按实际题数入库")
    nq=len(re.findall(r'^#題',txt,re.M)); na=len(re.findall(r'^#答',txt,re.M))
    print(f"  {sess}_{sec}: {nq}题 {na}答 → {'✅' if ok else '❌'}")
    if not ok:
        for line in r.stdout.split('\n'):
            if re.search(r'⚠|实际\d+题|不连续|选项不全|缺答案:   [1-9]',line): print(f"      {line.strip()}")
    return ok
if __name__=='__main__':
    dev=[]; ok=0; tot=0
    for sess in sys.argv[1:]:
        print(f"\n=== {sess} ===")
        for sec in ('言語知識','読解','聴解'):
            if os.path.exists(f'/tmp/run/{sess}/{sec}.txt'):
                tot+=1; ok+=process(sess,sec,dev)
    if dev:
        p=f'{ROOT}/DEVIATIONS.md'
        with open(p,'a',encoding='utf-8') as f:
            f.write('\n## 原卷印刷错误 / 归一化记录\n')
            for d in dev: f.write(f'- {d}\n')
        print(f"\n{len(dev)} 处偏差已记入 DEVIATIONS.md")
    print(f"\n入库 {ok}/{tot} 通过")
