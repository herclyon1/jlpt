#!/usr/bin/env python3
"""从真题 OCR 文本末尾的答案表提取答案
格式: 問題N → 一串「X番」→ 一串单数字(与番号顺序对应)
输出 JSON: {"言語知識":{"1":3,...},"読解":{...},"聴解":{"1-1":2,...}}
"""
import re,sys,json,collections
FW=str.maketrans('０１２３４５６７８９','0123456789')
NUM=re.compile(r'^(\d{1,2})\s*番$')
ANS=re.compile(r'^([1-4])$')
HEAD=re.compile(r'^(?:問題|聴解)\s*(\d+)$')
SEC=re.compile(r'N1\s*[.．]\s*(言語知識|聴解|読解)')
def run(path):
    lines=[l.translate(FW).replace('．','.').replace(' ','').strip()
           for l in open(path,encoding='utf-8',errors='ignore')]
    lines=[l for l in lines if l and not l.startswith('===PAGE')]
    out=collections.defaultdict(dict); sec='言語知識'; dai=None
    i=0
    while i<len(lines):
        l=lines[i]
        m=SEC.search(l)
        if m:
            sec='聴解' if '聴解' in m.group(1) else ('読解' if '読解' in l or '文法.読解' in l else '言語知識')
            i+=1; continue
        h=HEAD.match(l)
        if h:
            dai=int(h.group(1))
            if l.startswith('聴解'): sec='聴解'
            elif dai>=8: sec='読解'
            # 收番号
            j=i+1; nums=[]
            while j<len(lines) and NUM.match(lines[j]):
                nums.append(int(NUM.match(lines[j]).group(1))); j+=1
            # 收答案
            ans=[]
            while j<len(lines) and ANS.match(lines[j]):
                ans.append(int(lines[j])); j+=1
            if nums and ans:
                # 番号可能被OCR吞位(如 46→6), 用序号修正: 以首个番号为基准递增
                if sec=='聴解':
                    keys=[f"{dai}-{k+1}" for k in range(len(nums))]
                else:
                    base=nums[0]
                    keys=[str(base+k) for k in range(len(nums))]
                for k,a in zip(keys,ans): out[sec][k]=a
                i=j; continue
        i+=1
    return {k:v for k,v in out.items() if v}
if __name__=='__main__':
    r=run(sys.argv[1])
    for s,d in r.items():
        ks=sorted(d,key=lambda x:[int(y) for y in x.split('-')])
        print(f"# {s}: {len(d)} 个答案  {ks[0]}..{ks[-1]}",file=sys.stderr)
    print(json.dumps(r,ensure_ascii=False,indent=1))
