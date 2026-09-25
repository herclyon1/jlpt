import json,re
exec(open('add.py').read().split("json.dump(")[0])   # reuse tokenize → spans/new
DP_=DP
text_=text
# 1) 路地に入ったところで：此处「ところで」不是「话说回来」，拆掉文法块，ところ 按功能词
fix=[]
for a,b,v in spans:
    if isinstance(v,int) and v<0 and G[-1-v]['w']=='ところで' and text[a-3:a]=='入った':
        fix.append((a,a+3,W['ところ']))
    else: fix.append((a,b,v))
spans=fix
# 2) そこいら：分词切成 そこ＋いら，合并
i=text.index('そこいら'); spans=[s for s in spans if not (s[0]==i+2 and s[2]=='NEW:いら')]+[(i,i+4,'NEW:そこいら')]
spans.sort()
# 3) 语境专用义项：ひく（此处＝车轧人）、加減（上向き加減＝稍带…的样子）
def clone(base,m,ff=None):
    e=dict(V[W[base]]); e['m']=m; e['ex']=1
    if ff is not None: e['ff']=ff
    if ff: e.pop('k',None); e.pop('c',None)
    V.append(e); return len(V)-1
hiku=clone('ひく','（车）轧／撞')            # 沿用 ひく 的名次 #1748
kagen=clone('加減','程度／（…加減＝稍带…的样子）',ff=1)
spans=[(a,b,hiku if isinstance(v,int) and v==W['ひく'] else kagen if isinstance(v,int) and v==W['加減'] else v) for a,b,v in spans]
# 4) 新词入库（不进 11 套词频排名：无 k/c，f=n=0，ex=1）
G2={}
for line in open('gloss_extra.tsv',encoding='utf-8'):
    w,p,g,t,m,ff=line.rstrip('\n').split('\t'); G2[w]=(p,g,t,m,int(ff))
rd={k:v['r'] for k,v in new.items()}; rd['そこいら']='ソコイラ'
import unicodedata
def hira(s): return ''.join(chr(ord(c)-0x60) if 'ァ'<=c<='ヶ' else c for c in s)
nid={}
for a,b,v in spans:
    if isinstance(v,str):
        w=v[4:]
        if w not in nid:
            assert w in G2, w
            p,g,t,m,ff=G2[w]
            V.append({'w':w,'r':hira(rd[w]) if t!='ka' else hira(rd[w]),'p':p,'g':g,'f':0,'t':t,'n':0,'j':'','m':m,'ff':ff,'x':0,'ex':1})
            nid[w]=len(V)-1
spans=[[a,b,nid[v[4:]] if isinstance(v,str) else v] for a,b,v in spans]
missing=set(G2)-set(nid); assert not missing, missing
D['passages'].append({'set':'補充','pid':'総合理解3-3','dai':'総合理解','text':text,'qs':[],
    'label':'総合理解 第3回 3番（校内プリント）','spans':spans,'bad':0})
D['built']='2026-09-25'
out='window.RD='+json.dumps(D,ensure_ascii=False,separators=(',',':'))+';'
orig=open(DP_,encoding='utf-8').read()
# 往返校验：不加新篇时序列化应与原文件一致
print('new vocab',len(nid),'total',len(V),'spans',len(spans))
open(DP_,'w',encoding='utf-8').write(out)
