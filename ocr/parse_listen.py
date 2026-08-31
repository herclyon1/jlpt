#!/usr/bin/env python3
"""从「答案解析+听力原文」OCR 文本提取听力台本 → 标准格式 #文 块
台本结构: [問題N] / N.M 标记 / 情境句 / 対話(男：女：) / 設問句
"""
import re,sys,os,collections
FW=str.maketrans('０１２３４５６７８９','0123456789')
def norm(s): return s.translate(FW).replace('．','.').replace('　',' ').strip()
MARK=re.compile(r'^([1-5])\s*[.\-]\s*(\d{1,2})$')     # 1.2 = 問題1 2番
MOND=re.compile(r'^問題\s*([1-5])$')
SPK =re.compile(r'^(男|女|男の人|女の人|男の学生|女の学生|店員|司会|アナウンサー|M|F)\s*[：:]')
CJK =re.compile(r'[的了是在和有个我他这那们]')          # 中文解析行特征
OPT=re.compile(r'^([1-4])\s*[.、]?\s*([^\d\s].{2,})$')
def extract_q4(L,start):
    """問題4 即時応答: 提示句 + 3个应答, 标记 4.N 可能缺失"""
    items=[]; cur=None
    for l in L[start:]:
        if re.match(r'^問題\s*[15]$',l) or re.match(r'^5\s*[.\-]\s*\d',l): break
        if re.match(r'^4\s*[.\-]\s*\d{1,2}$',l):
            cur={'dai':4,'num':int(l.split('.')[-1].split('-')[-1]),'lines':[],'opts':[]}
            items.append(cur); continue
        mo=OPT.match(l)
        if cur and mo and len(cur['opts'])<3 and int(mo.group(1))==len(cur['opts'])+1:
            cur['opts'].append(mo.group(2).strip()); continue
        if not re.search(r'[ぁ-ゖァ-ヶ]',l) or CJK.search(l): continue
        # 新提示句: 上一题已满3个应答, 或还没开始
        if cur is None or len(cur['opts'])>=3:
            cur={'dai':4,'num':(items[-1]['num']+1 if items else 1),'lines':[l],'opts':[]}
            items.append(cur)
        elif not cur['lines']: cur['lines']=[l]
    return [x for x in items if x['lines'] and len(x['opts'])>=2]

def extract(path):
    L=[norm(l) for l in open(path,encoding='utf-8',errors='ignore')]
    L=[l for l in L if l and not l.startswith('=== PAGE')]
    items=[]; cur=None; dai=None; started=False
    for l in L:
        m=MOND.match(l)
        if m: dai=int(m.group(1)); started=True; continue
        mk=MARK.match(l)
        if mk:
            dai=int(mk.group(1)); started=True
            cur={'dai':dai,'num':int(mk.group(2)),'lines':[]}; items.append(cur); continue
        if not started: continue
        if SPK.match(l) or (cur and cur['lines']):
            if cur is None:
                cur={'dai':dai or 1,'num':1,'lines':[]}; items.append(cur)
            if CJK.search(l) and not SPK.match(l) and len(re.findall(r'[ぁ-ゖァ-ヶ]',l))<4: continue
            cur['lines'].append(l)
        elif SPK.match(l)==None and cur is None and len(l)>14 and re.search(r'[ぁ-ゖ]',l) \
             and not CJK.search(l):
            cur={'dai':dai or 1,'num':1,'lines':[l]}; items.append(cur)
    # 补首题号
    seen=collections.Counter()
    for it in items:
        if it['num']==0: it['num']=seen[it['dai']]+1
        seen[it['dai']]=max(seen[it['dai']],it['num'])
    items=[it for it in items if len(it['lines'])>=2]
    # 問題4 单独处理
    for i,l in enumerate(L):
        if re.match(r'^問題\s*4$',l):
            items=[x for x in items if x['dai']!=4] + extract_q4(L,i+1); break
    return items
def emit(items,exam):
    out=[f"#卷 {exam} N1","#科 聴解"]
    bydai=collections.defaultdict(list)
    for it in items: bydai[it['dai']].append(it)
    n=0
    for d in sorted(bydai):
        out.append(f"#大題 問題{d}")
        for it in sorted(bydai[d],key=lambda x:x['num']):
            out.append(f"#題 {it['num']}")
            out.append(f"#文 T{d}-{it['num']}")
            out += it['lines']
            out.append("#文完")
            for i,o in enumerate(it.get('opts',[]),1): out.append(f"#选 {i} {o}")
            n+=1
    return '\n'.join(out)+'\n', n
if __name__=='__main__':
    p=sys.argv[1]
    exam=sys.argv[sys.argv.index('--exam')+1] if '--exam' in sys.argv else '????'
    outdir=sys.argv[sys.argv.index('--out')+1] if '--out' in sys.argv else None
    it=extract(p); txt,n=emit(it,exam)
    c=collections.Counter(x['dai'] for x in it)
    print(f"  台本 {n} 题  逐大題 {dict(sorted(c.items()))}",file=sys.stderr)
    if outdir:
        os.makedirs(outdir,exist_ok=True)
        open(f"{outdir}/{exam}_聴解.txt",'w',encoding='utf-8').write(txt)
    else: print(txt)
