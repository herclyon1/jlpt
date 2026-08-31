#!/usr/bin/env python3
"""JLPT N1 全栈判题器: 规则 + BERT + 句子嵌入
用法: python3 solve.py <标准格式卷面.txt> [更多文件...]
"""
import re,sys,glob,json,math,collections,warnings
warnings.filterwarnings('ignore')
import numpy as np, torch
sys.path.insert(0,__import__('os').path.dirname(__file__) or '.')
import onyomi
from transformers import AutoTokenizer, AutoModelForMaskedLM
from sentence_transformers import SentenceTransformer

DEV="mps" if torch.backends.mps.is_available() else "cpu"
_BERT=_TK=_SB=None
def bert():
    global _BERT,_TK
    if _BERT is None:
        n="tohoku-nlp/bert-base-japanese-v3"
        _TK=AutoTokenizer.from_pretrained(n); _BERT=AutoModelForMaskedLM.from_pretrained(n).eval().to(DEV)
    return _TK,_BERT
def sbert():
    global _SB
    if _SB is None:
        _SB=SentenceTransformer("oshizo/sbert-jsnli-luke-japanese-base-lite").to(DEV)
    return _SB

@torch.no_grad()
def pll(text,tail=None):
    tk,md=bert()
    ids=tk(text,return_tensors='pt',truncation=True,max_length=256)['input_ids'][0]
    if len(ids)<3: return -1e9
    idx=list(range(1,len(ids)-1))
    if tail: idx=idx[-tail:]
    out=[]
    for k in range(0,len(idx),64):
        ch=idx[k:k+64]
        b=ids.unsqueeze(0).repeat(len(ch),1).clone()
        for r,i in enumerate(ch): b[r,i]=tk.mask_token_id
        lp=torch.log_softmax(md(b.to(DEV)).logits,dim=-1)
        out+=[lp[r,i,ids[i]].item() for r,i in enumerate(ch)]
    return sum(out)/max(len(out),1)

def parse(fp):
    qs=[];cur=None;dai=None;sec=None;pas={};cp=None
    for line in open(fp,encoding='utf-8'):
        line=line.rstrip('\n')
        if cp is not None:
            if line.startswith('#文完'):
                pas[cp[0]]='\n'.join(cp[1])
                if cur is not None and not cur['pas']: cur['pas']=cp[0]
                cp=None
            else: cp[1].append(line)
            continue
        m=re.match(r'^[#＃](卷|科|大題|大题|題|题|干|选|選|答|文)\s*(.*)$',line)
        if not m: continue
        t,v=m.groups()
        if t=='文': cp=[v.strip(),[]]
        elif t=='科': sec=v.strip()
        elif t in('大題','大题'): dai=v.strip()
        elif t in('題','题'):
            pm=re.match(r'^(\d+)\s*(?:[@＠]文\s*(\S+))?',v)
            cur={'sec':sec,'dai':dai,'num':pm.group(1) if pm else '','opts':[],'ans':None,
                 'stem':'','pas':pm.group(2) if pm else None};qs.append(cur)
        elif t=='干' and cur: cur['stem']=v
        elif t in('选','選') and cur:
            om=re.match(r'^(\d+)\s+(.*)$',v);cur['opts'].append((om.group(2) if om else v).strip())
        elif t=='答' and cur:
            try: cur['ans']=int(v.strip())
            except: pass
    return qs,pas

def sents(p):
    out=[]
    for para in p.split('\n'):
        para=para.strip()
        if not para or para.startswith('（注') or para=='整理中': continue
        out+=[s.strip() for s in re.split(r'(?<=[。？！])',para) if len(s.strip())>6]
    return out
def toks(s):
    o=set()
    for r in re.findall(r'[一-鿿]+',s):
        o.add(r) if len(r)==1 else o.update(r[i:i+2] for i in range(len(r)-1))
    o|=set(re.findall(r'[ァ-ヶー]{2,}',s))
    o|=set(re.findall(r'[ぁ-ゖ]{3,}',s))     # 与JS引擎一致: 含平假名串
    return o

# ---------- 各题型求解 ----------
def solve_cloze(q,pas):
    """問題2/3/5/7: BERT 伪对数似然"""
    st=q['stem']
    if '（　）' not in st:
        if q['pas'] and q['pas'] in pas:
            b=pas[q['pas']]; mk='【'+q['num']+'】'; i=b.find(mk)
            if i<0: return None,None
            lo=max(0,b.rfind('。',0,i)+1); hi=b.find('。',i)
            st=b[lo:hi+1 if hi>0 else len(b)].replace(mk,'（　）').strip()
        else:
            m=re.search(r'＜(.+?)＞',st)
            if not m: return None,None
            st=st[:m.start()]+'（　）'+st[m.end():]
    i=st.find('（　）'); pre,post=st[:i],st[i+3:]
    sc=[pll(pre+o+post) for o in q['opts']]
    return int(np.argmax(sc))+1,'BERT-PLL'
def solve_usage(q):
    sc=[pll(re.sub(r'[＜＞]','',o)) for o in q['opts']]
    return int(np.argmax(sc))+1,'BERT-PLL'
def solve_star(q):
    import itertools
    st=q['stem']; sl=re.findall(r'＿★＿|＿＿',st)
    if len(sl)<4 or '＿★＿' not in sl: return None,None
    star=sl.index('＿★＿'); pre=st[:st.find(sl[0])]; post=st[st.rfind(sl[-1])+len(sl[-1]):]
    best=max(itertools.permutations(range(4)),
             key=lambda pm: pll(pre+''.join(q['opts'][i] for i in pm)+post))
    return best[star]+1,'BERT-排列'
def solve_reading(q,pas):
    if not q['pas'] or q['pas'] not in pas or len(q['opts'])<2: return None,None
    s=sents(pas[q['pas']])
    if len(s)<3: return None,'短文-规则不适用'
    sb=sbert()
    E=sb.encode(s,convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False)
    O=sb.encode(q['opts'],convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False)
    return int(np.argmax((O@E.T).max(1)))+1,'句子嵌入'
def solve_lis_lean(q,pas):
    if not q['pas'] or q['pas'] not in pas or len(q['opts'])<2: return None,None
    st=toks(pas[q['pas']])
    if len(st)<5: return None,None
    sc=[len(toks(o)&st)/max(min(len(toks(o)),len(st)),1) for o in q['opts']]
    return int(np.argmin(sc))+1,'听A-最少重叠'
def solve_lis_quick(q,pas):
    if not q['pas'] or q['pas'] not in pas or len(q['opts'])<2: return None,None
    sc=pas[q['pas']].replace('\n','')[-60:]
    v=[pll(sc+o) for o in q['opts']]
    return int(np.argmax(v))+1,'BERT-PLL'

def solve_info(q,pas):
    if not q['pas'] or q['pas'] not in pas or len(q['opts'])<2: return None,None
    s=[x for x in sents(pas[q['pas']]) if re.search(r'(上限|まで|以内|以上|以下|未満|必ず|ただし|のみ|無料|割引|不要|円|日|時)',x)]
    if len(s)<2: return None,None
    sb=sbert()
    E=sb.encode(s,convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False)
    O=sb.encode(q['opts'],convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False)
    return int(np.argmax((O@E.T).max(1)))+1,'嵌入·约束条款'

def dai_no(d): 
    m=re.search(r'\d+',d or ''); return int(m.group()) if m else 0

def run(fp):
    qs,pas=parse(fp)
    out=[]
    for q in qs:
        if len(q['opts'])<2: out.append((q,None,'选项缺失')); continue
        d=dai_no(q['dai']); s=q['sec'] or ''
        pick=meth=None
        if '言語知識' in s:
            if d==1:
                m=re.search(r'＜(.+?)＞',q['stem'])
                pick=onyomi.solve(m.group(1),q['opts']) if m else None
                meth='规则·音A/B/C'
            elif d in (2,3,5,7): pick,meth=solve_cloze(q,pas)
            elif d==4: pick,meth=solve_usage(q)
            elif d==6: pick,meth=solve_star(q)
        elif '読解' in s:
            if d==13: pick,meth=solve_info(q,pas)
            elif d==8: pick,meth=None,'短文-无有效方法'   # 实测16.7%, 低于基线, 主动弃权
            else: pick,meth=solve_reading(q,pas)
        elif '聴解' in s:
            if d in (1,2): pick,meth=solve_lis_lean(q,pas)
            elif d==4: pick,meth=solve_lis_quick(q,pas)
            else: pick,meth=None,'无有效方法'
        out.append((q,pick,meth))
    return out

if __name__=='__main__':
    files=sys.argv[1:] or sorted(glob.glob('../converted/*.txt'))
    G=collections.defaultdict(lambda:[0,0,0])
    ROUTE=collections.defaultdict(lambda:[0,0])
    for fp in files:
        for q,pick,meth in run(fp):
            k=(q['sec'] or '?')+'|'+(q['dai'] or '?')
            g=G[k]; g[2]+=1
            if pick:
                g[1]+=1
                ok = bool(q['ans'] and pick==q['ans'])
                if ok: g[0]+=1
                r=ROUTE[meth or '?']; r[1]+=1; r[0]+=ok
    print(f"{'科目|大題':<26}{'出手':>8}{'正确率':>10}   期望分(未出手按蒙)")
    T=[0.0,0]
    for k in sorted(G):
        a,f,n=G[k]
        acc=a/f if f else 0
        exp=a + (n-f)*0.25
        T[0]+=exp; T[1]+=n
        print(f"{k:<26}{f}/{n:>3}   {100*acc:>6.1f}%   {exp:>6.1f}/{n}")
    print(f"{'合计':<26}{'':>8}{'':>10}   {T[0]:.1f}/{T[1]} = {100*T[0]/T[1]:.1f}%")
    print(f"\n{'路线':<22}{'出手':>8}{'正确':>8}{'正确率':>9}{'比蒙多拿':>10}")
    for m,(a,n) in sorted(ROUTE.items(),key=lambda kv:-kv[1][0]):
        gain=a-n*0.25
        print(f"{m:<22}{n:>8}{a:>8}{100*a/n:>8.1f}%{gain:>9.1f}题")
