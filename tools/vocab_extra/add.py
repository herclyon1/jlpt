import json,collections,fugashi,re,sys
DP='/Users/herclyon/JLPT/repo/docs/vocab/data.js'
s=open(DP,encoding='utf-8').read(); D=json.loads(s[s.index('{'):s.rindex('}')+1])
V=D['vocab']; G=D['gram']
W={v['w']:i for i,v in enumerate(V)}
text=open(sys.argv[1] if len(sys.argv)>1 else 'text.txt',encoding='utf-8').read().rstrip('\n')
T=fugashi.Tagger()
PMAP={'名詞':'名','動詞':'動','形容詞':'形','形状詞':'形状','副詞':'副','連体詞':'連体','接続詞':'接続','感動詞':'感動','接頭辞':'接辞','接尾辞':'接辞'}
toks=[];pos=0
for w in T(text):
    a=text.index(w.surface,pos); b=a+len(w.surface); pos=b
    toks.append((a,b,w))
starts={a for a,b,w in toks}; ends={b for a,b,w in toks}
# grammar blocks: longest first, token-aligned, non-overlapping
gs=sorted(range(len(G)),key=lambda i:-len(G[i]['w']))
taken=[None]*len(text); blocks=[]
for gi in gs:
    g=G[gi]['w']
    for m in re.finditer(re.escape(g),text):
        a,b=m.start(),m.end()
        if a in starts and b in ends and all(x is None for x in taken[a:b]):
            for x in range(a,b): taken[x]=gi
            blocks.append((a,b,-1-gi))
spans=list(blocks); new=collections.OrderedDict()
for a,b,w in toks:
    if taken[a] is not None: continue
    f=w.feature; p=PMAP.get(f.pos1)
    if not p or f.pos2 in ('固有名詞','数詞'): continue
    key=f.orthBase or w.surface
    if key in W: spans.append((a,b,W[key]))
    else:
        new.setdefault(key,{'w':key,'r':f.kanaBase,'p':p,'g':{'和':'和','漢':'漢','外':'外','混':'混'}.get(f.goshu,f.goshu),'lemma':f.lemma,'surf':[]})['surf'].append(w.surface)
        spans.append((a,b,'NEW:'+key))
spans.sort()
json.dump({'spans':spans,'new':new},open('stage.json','w'),ensure_ascii=False,indent=0)
for a,b,v in spans:
    lab = G[-1-v]['w']+'〔文法〕' if isinstance(v,int) and v<0 else (V[v]['w']+('·fn' if V[v].get('x') else '')+(f"·{V[v]['t']}" if V[v]['t'] else '')+(f"·#{V[v]['k']}" if 'k' in V[v] else '') if isinstance(v,int) else v)
    print(text[a:b],'→',lab)
print('NEW',len(new)); 
for k,v in new.items(): print(k,v['r'],v['p'],v['g'],v['surf'])
