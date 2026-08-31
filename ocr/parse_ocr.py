#!/usr/bin/env python3
"""OCR 文本 → 标准卷面格式 (FORMAT.md)
用法: python3 ocr/parse_ocr.py <ocr.txt> --exam 2023-07 [--out 目录]
"""
import re,sys,os
FW=str.maketrans('０１２３４５６７８９','0123456789')
def norm(s):
    return s.translate(FW).replace('．','.').replace('，',',').replace('　',' ').strip()
def load(p):
    return [norm(l) for l in open(p,encoding='utf-8',errors='ignore')
            if not l.startswith('=== PAGE') and norm(l)]

MOND=re.compile(r'^(?:問題|聴解)\s*(\d+)')
QNUM=re.compile(r'^(\d{1,2})\s*[.、]\s*(.*)$')
OPT =re.compile(r'^([1-4])\s*([^\d\s].*)$')
SEC =re.compile(r'^(?:N1\s*[.．]\s*)?聴\s*解$')
NOISE=re.compile(r'(試験が始まる|問題用紙|受験番号|Examinee|最終バージョン|微公介号|資料舗|解答用紙|Language Knowledge)')

def parse(lines):
    sec='言語知識'; blocks=[]; cur=None; q=None; buf=[]
    seen_dai=set()
    for ln in lines:
        if NOISE.search(ln) and not MOND.match(ln): continue
        if SEC.match(ln):
            sec='聴解'; cur=None; q=None; seen_dai=set(); continue
        m=MOND.match(ln)
        if m:
            d=int(m.group(1))
            # 言語知識段里第二次出现小号大題 = 进入聴解
            if sec=='言語知識' and d<=5 and d in seen_dai:
                sec='聴解'; seen_dai=set()
            seen_dai.add(d)
            s2 = '聴解' if sec=='聴解' else ('読解' if 8<=d<=13 else '言語知識')
            if ln.startswith('聴解'): s2='聴解'; sec='聴解'
            cur={'sec':s2,'dai':d,'qs':[],'passage':[]}; blocks.append(cur); q=None
            continue
        if cur is None: continue
        mo=OPT.match(ln); mq=QNUM.match(ln)
        # ── 选项
        if q is not None and len(q['opts'])<4 and mo:
            n=int(mo.group(1))
            if n==len(q['opts'])+1:
                q['opts'].append(mo.group(2).strip()); continue
        # ── 新题号
        if mq:
            n=int(mq.group(1)); body=mq.group(2).strip()
            if cur['sec']=='聴解' and body in ('番','番.','.番',''):
                if q is not None and not q['opts'] and not q['stem']: cur['qs'].pop()
                q={'num':n,'stem':'','opts':[]}; cur['qs'].append(q); continue
            short_ok = cur['dai']==4          # 問題4 题干是裸词, 允许很短
            if 1<=n<=70 and (len(body)>=4 or (short_ok and len(body)>=1)):
                if q is not None and not q['opts'] and len(q['stem'])<3: cur['qs'].pop()
                q={'num':n,'stem':body,'opts':[]}; cur['qs'].append(q); continue
        # ── 题干续行（含 ★ 行）
        if q is not None and not q['opts']:
            q['stem'] += ('＿★＿' if ln=='★' else ln)
            continue
        # ── 未开始出题 = 文章正文
        if q is None and len(ln)>6: cur['passage'].append(ln)
    return blocks

def fill_cloze(blocks):
    """問題7: 文章里有【41】【42】而题目没抓全时, 按标记补出题号"""
    for b in blocks:
        if b['dai']!=7 or not b['passage']: continue
        marks=[int(x) for x in re.findall(r'[【\[](\d{2})[】\]]', '\n'.join(b['passage']))]
        have={q['num'] for q in b['qs']}
        for m in sorted(set(marks)):
            if m not in have: b['qs'].append({'num':m,'stem':'','opts':[]})
        b['qs'].sort(key=lambda q:q['num'])
    return blocks

def emit(blocks,exam,want):
    out=[f"#卷 {exam} N1",f"#科 {want}"]
    n=0
    for b in blocks:
        if b['sec']!=want or not b['qs']: continue
        out.append(f"#大題 問題{b['dai']}")
        pid=None
        if b['passage'] and (b['dai']>=7 or want=='読解'):
            pid=f"P{b['dai']}"
            out.append(f"#文 {pid}"); out+=b['passage']; out.append("#文完")
        for q in b['qs']:
            out.append(f"#題 {q['num']}" + (f" @文 {pid}" if pid else ""))
            if q['stem']: out.append(f"#干 {q['stem']}")
            for i,o in enumerate(q['opts'],1): out.append(f"#选 {i} {o}")
            n+=1
    return '\n'.join(out)+'\n', n

if __name__=='__main__':
    p=sys.argv[1]
    exam=sys.argv[sys.argv.index('--exam')+1] if '--exam' in sys.argv else '????'
    outdir=sys.argv[sys.argv.index('--out')+1] if '--out' in sys.argv else None
    B=fill_cloze(parse(load(p)))
    for want in ('言語知識','読解','聴解'):
        txt,n=emit(B,exam,want)
        if n==0: continue
        if outdir:
            os.makedirs(outdir,exist_ok=True)
            fp=f"{outdir}/{exam}_{want}.txt"
            open(fp,'w',encoding='utf-8').write(txt)
            print(f"  {os.path.basename(fp)}: {n} 题",file=sys.stderr)
        else:
            print(txt)
    # 诊断
    print("# 逐大題:",file=sys.stderr)
    for b in B:
        if not b['qs']: continue
        c4=sum(1 for q in b['qs'] if len(q['opts'])==4)
        print(f"#   [{b['sec']}] 問題{b['dai']}: {len(b['qs'])}题 齐全{c4} 文章{len(b['passage'])}行",file=sys.stderr)
