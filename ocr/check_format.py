#!/usr/bin/env python3
"""校验标准格式文件；用法: python3 ocr/check_format.py converted/xxx.txt"""
import re,sys,collections
EXPECT={'言語知識':{1:6,2:7,3:6,4:6,5:10,6:5,7:4},
        '読解':{8:4,9:8,10:3,11:2,12:3,13:2},
        '聴解':{1:5,2:6,3:5,4:11,5:3}}
def check(fp):
    sec=None;dai=None;qs=[];cur=None;pas=set();ref=set();err=[];ln=0
    inpas=False
    for line in open(fp,encoding='utf-8'):
        ln+=1; l=line.rstrip('\n')
        if inpas:
            if l.startswith('#文完'): inpas=False
            continue
        if not l.startswith('#'):
            # 允许 #干/#选 的续行（FORMAT.md 允许多行题干）
            if l.strip() and not cur: err.append(f"L{ln}: 非标记行且不在#題/#文块内: {l[:30]!r}")
            continue
        m=re.match(r'^#(卷|科|大題|題|干|选|答|文|文完)\s*(.*)$',l)
        if not m: err.append(f"L{ln}: 无法识别的标记: {l[:30]!r}"); continue
        t,v=m.groups()
        if t=='科': sec=v.strip()
        elif t=='文': pas.add(v.strip()); inpas=True
        elif t=='大題':
            d=re.search(r'\d+',v); dai=int(d.group()) if d else None
        elif t=='題':
            pm=re.match(r'^(\d+)\s*(?:[@＠]文\s*(\S+))?',v)
            if not pm: err.append(f"L{ln}: #題 格式错: {v!r}"); continue
            cur={'num':int(pm.group(1)),'dai':dai,'opts':0,'ans':None,'ln':ln,'ref':pm.group(2)}
            qs.append(cur)
            if pm.group(2): ref.add(pm.group(2))
        elif t=='选':
            if not cur: err.append(f"L{ln}: #选 出现在 #題 之前")
            else:
                om=re.match(r'^(\d+)\s+\S',v)
                if not om: err.append(f"L{ln}: #选 格式错(应为「#选 1 内容」): {v[:20]!r}")
                else:
                    cur['opts']+=1
                    if int(om.group(1))!=cur['opts']:
                        err.append(f"L{ln}: 題{cur['num']} 选项编号不连续(应为{cur['opts']}, 实为{om.group(1)})")
        elif t=='答':
            if not cur: err.append(f"L{ln}: #答 出现在 #題 之前")
            elif not re.match(r'^[1-4]$',v.strip()): err.append(f"L{ln}: #答 应为1-4: {v!r}")
            else: cur['ans']=int(v.strip())
    print(f"文件: {fp}\n科目: {sec}   题数: {len(qs)}")
    byd=collections.Counter(q['dai'] for q in qs)
    exp=EXPECT.get(sec,{})
    print(f"\n{'大題':<6}{'实际':>5}{'应有':>5}   状态")
    for d in sorted(set(byd)|set(exp)):
        a=byd.get(d,0); e=exp.get(d,'?')
        st='✅' if e=='?' or a==e else ('⚠少'+str(e-a) if isinstance(e,int) and a<e else '⚠多')
        print(f"問題{d:<4}{a:>5}{str(e):>5}   {st}")
    noopt=[q for q in qs if q['opts']<(3 if sec=='聴解' and q['dai']==4 else 4)]
    noans=[q for q in qs if q['ans'] is None]
    bad=[r for r in ref if r not in pas]
    print(f"\n选项不全: {len(noopt)} 题" + (f"  → 題{[q['num'] for q in noopt][:12]}" if noopt else ""))
    print(f"缺答案:   {len(noans)} 题" + (f"  → 題{[q['num'] for q in noans][:12]}" if noans else ""))
    if bad: print(f"引用了不存在的文章块: {bad}")
    if err:
        print(f"\n格式错误 {len(err)} 处:")
        for e in err[:15]: print("  "+e)
    ok = not err and not noopt and not noans and not bad
    print("\n"+("✅ 通过" if ok else "❌ 不通过——把上面的报错贴回给 DeepSeek 让它修"))
    return ok
if __name__=='__main__':
    sys.exit(0 if all(check(f) for f in sys.argv[1:]) else 1)
