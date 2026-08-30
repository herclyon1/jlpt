"""音读规则 V6 (音A送り仮名闸门 / 音B禁止音训混搭 / 音C漢語連濁限ん・っ后)"""
import json,re,os
YOMI=json.load(open(os.path.join(os.path.dirname(__file__),'..','engine','kanji_yomi.json'),encoding='utf-8'))
DAKU={"が":"か","ぎ":"き","ぐ":"く","げ":"け","ご":"こ","ざ":"さ","じ":"し","ず":"す","ぜ":"せ","ぞ":"そ",
"だ":"た","ぢ":"ち","づ":"つ","で":"て","ど":"と","ば":"は","び":"ひ","ぶ":"ふ","べ":"へ","ぼ":"ほ",
"ぱ":"は","ぴ":"ひ","ぷ":"ふ","ぺ":"へ","ぽ":"ほ"}
def unvoice(s): return (DAKU.get(s[0],s[0])+s[1:]) if s else s
SMALL="ゃゅょ"
def morae(k):
    m=[]
    for c in k:
        if c in SMALL and m: m[-1]+=c
        else: m.append(c)
    return m
def splits(kana,n):
    M=morae(kana); res=[]
    def rec(st,parts):
        if len(parts)==n:
            if st==len(M): res.append(list(parts))
            return
        rem=len(M)-st; need=n-len(parts)
        for L in range(1,min(6,rem)+1):
            if rem-L < need-1 or rem-L > (need-1)*6: continue
            parts.append(''.join(M[st:st+L])); rec(st+L,parts); parts.pop()
    rec(0,[]); return res
def seg_ok(seg,pool,pos,is_kun,prev):
    if not pool: return False
    cands={seg}
    allow = is_kun or (prev and prev[-1] in "んっ")
    if pos>0 and allow: cands.add(unvoice(seg))
    if seg.endswith("っ"):
        for t in "つちくき":
            cands.add(seg[:-1]+t)
            if pos>0 and allow: cands.add(unvoice(seg[:-1]+t))
    for c in cands:
        if c in pool: return True
        if is_kun:
            for r in pool:
                if r.startswith(c) and 0 < len(r)-len(c) <= 2: return True
    return False
def solve(word,options):
    kanji=[c for c in word if re.match(r'[一-鿿]',c)]
    if not kanji or any(c not in YOMI for c in kanji): return None
    oku=re.sub(r'[一-鿿]','',word)
    surv=[]
    for i,o in enumerate(options):
        kana=re.sub(r'[^ぁ-ゖー]','',o)
        base=kana[:-len(oku)] if oku and kana.endswith(oku) else kana
        ok=False
        for sp in splits(base,len(kanji)):
            if all(seg_ok(sp[j],YOMI[kanji[j]][0],j,False,sp[j-1] if j else None) for j in range(len(kanji))): ok=True;break
            if all(seg_ok(sp[j],YOMI[kanji[j]][1],j,True, sp[j-1] if j else None) for j in range(len(kanji))): ok=True;break
        if ok: surv.append(i)
    return surv[0]+1 if len(surv)==1 else None
