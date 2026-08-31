#!/usr/bin/env python3
"""调用 DeepSeek API 把 OCR 文本转成标准卷面格式

用法:
  export DEEPSEEK_API_KEY=sk-xxxx        # 或写进 ocr/.ds_key
  python3 ocr/ds_convert.py 2023-07 言語知識
  python3 ocr/ds_convert.py --all        # 批量处理所有缺失的场次×科目

产物写入 converted/<场次>_<科目>.txt，随后自动跑 check_format.py 校验。
校验不过会把报错回灌给模型重试（最多 3 轮）。
"""
import os,sys,re,json,glob,time,subprocess,urllib.request

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API="https://api.deepseek.com/chat/completions"
MODEL=os.environ.get("DEEPSEEK_MODEL","deepseek-v4-flash")

def key():
    k=os.environ.get("DEEPSEEK_API_KEY")
    if k: return k.strip()
    p=os.path.join(ROOT,'ocr','.ds_key')
    if os.path.exists(p): return open(p).read().strip()
    sys.exit("缺少 API key: export DEEPSEEK_API_KEY=sk-xxx  或写入 ocr/.ds_key")

def call(msgs,max_tokens=16384,temp=0.0,model=None):
    body=json.dumps({"model":model or MODEL,"messages":msgs,"temperature":temp,
                     "max_tokens":max_tokens,"stream":False,
                     "reasoning_effort":"none"}).encode()   # v4 是推理模型, 不关会把token全烧在思维链上
    req=urllib.request.Request(API,data=body,headers={
        "Content-Type":"application/json","Authorization":"Bearer "+key()})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req,timeout=600) as r:
                d=json.loads(r.read())
            return d["choices"][0]["message"]["content"], d.get("usage",{})
        except Exception as e:
            if attempt==3: raise
            print(f"    重试 {attempt+1}/3 ({e})",file=sys.stderr); time.sleep(5*(attempt+1))

RULES={
"言語知識":"""#科 言語知識
規則:
1. 只输出标记格式,不要解释,不要 markdown 代码块。
2. 問題1(漢字読み): 题干里被考察的词用 ＜＞ 括起来。OCR 丢了下划线,
   你要根据四个选项的读音反推是哪个词。例: 选项 ぼぜん/そぜん/ぼうぜん/そうぜん → 考的是「騒然」。
3. 問題2/3/5: 空格写成 （　）(全角括号+全角空格)。問題3 的被考词用 ＜＞ 括起来。
4. 問題4(用法): #干 只写被考察的词本身, 四个 #选 是四个完整句子。
5. 問題6(組句★): 题干四个空写成 ＿＿ ＿＿ ＿★＿ ＿＿, ★位置照原文。
6. 問題7(文章文法): 先输出
   #文 G7
   (文章正文, 空格处写 【41】【42】…, 编号=题号)
   #文完
   然后每题 "#題 41 @文 G7" + 四个 #选, 不写 #干。
7. 題数: 問題1=6 問題2=7 問題3=6 問題4=6 問題5=10 問題6=5 問題7=4, 共44题。一题都不能少。""",
"読解":"""#科 読解
規則:
1. 只输出标记格式,不要解释,不要 markdown 代码块。
2. 每篇文章输出为:
   #文 A1
   (正文,保留段落。文末的(注1)…照抄)
   #文完
   然后 "#題 45 @文 A1"。文章块名自定(A1/B2/C1…),每篇一个。
3. 有下線部的题, 题干里的下線部用 ＜＞ 括起来。
4. 問題13(情報検索): 表格/通知按行线性化, 保留全部数字与条件。
5. 題数: 問題8=4 問題9=8 問題10=3 問題11=2 問題12=3 問題13=2, 共22题。""",
"聴解":"""#科 聴解
規則:
1. 只输出标记格式,不要解释,不要 markdown 代码块。
2. 每题格式:
   #題 1
   #文 T1-1
   (该题完整台本: 情境句 + 対話 + 設問句)
   #文完
   #选 1 …
   #选 2 …
   #选 3 …
   #选 4 …
   #答 2
3. 選項来自「真题」文本的听力段(格式「1.番」后跟四个选项)。
4. 台本来自「答案解析+听力原文」文本(男：/女： 的対話)。
5. 問題3(概要理解)与問題4(即時応答)试卷不印选项, 选项从台本里取。問題4 每题只有3个选项。
6. 台本里的「4.2」这类是题号标记(問題4第2题), 不要输出它。
7. 題数: 問題1=5 問題2=6 問題3=5 問題4=11 問題5=3, 共30题。""",
}
COMMON="""你是日语试卷格式转换员。把下面的 OCR 文本转成指定的标记格式。

【格式】严格按下面的示例, 一个字符都不能变。注意 #选 后面必须跟选项编号和空格。

完整示例(照抄这个结构):
#卷 {exam} N1
#科 言語知識
#大題 問題1
#題 1
#干 事件の＜真相＞を究明する。
#选 1 しんそう
#选 2 しんしょう
#选 3 まそう
#选 4 まっそう
#答 1
#題 2
#干 ...
#选 1 ...

标记只有这几个, 不要自创: #卷 #科 #大題 #題 #干 #选 #答 #文 #文完
禁止写成 #問1 / #選 / #题 / #答:2 这类变体。

{rules}

【答案】OCR 文本末尾有答案表, 格式如「問題8 / 45番 46番 47番 48番 / 1 3 2 2」,
番号与答案按顺序对应。OCR 可能把 46番 识成 6番, 按顺序递推即可。每题都要有 #答。

【保真】日文逐字保真。OCR 有丢字(如「潜している」实为「潜伏している」、
「らかな声」实为「朗らかな声」), 你能确认的补全, 不确认的原样保留并在行末加 〔?〕。
"""

NORM_RULES=[
 (r'^#\s*問\s*題?\s*(\d+)\s*$', r'#大題 問題\1'),      # #問1 / #問題1 → #大題 問題1
 (r'^#\s*大\s*題\s*問?題?\s*(\d+)', r'#大題 問題\1'),
 (r'^#\s*選\s', '#选 '), (r'^#\s*选\s', '#选 '),
 (r'^#\s*题\s', '#題 '), (r'^#\s*幹\s', '#干 '),
 (r'^#\s*答案?\s*[:：]?\s*', '#答 '),
]
def normalize(txt):
    """把模型常见的格式变体纠正成标准格式"""
    out=[]; optn=0; dai=None; seen_dai=False
    for raw in txt.split('\n'):
        l=raw.rstrip()
        for pat,rep in NORM_RULES:
            l2=re.sub(pat,rep,l)
            if l2!=l: l=l2; break
        if l.startswith('#大題'): seen_dai=True; optn=0
        elif l.startswith('#題'): optn=0
            # 没有 #大題 就按题号推断
        elif l.startswith('#选'):
            m=re.match(r'^#选\s+(\d)\s+(.*)$',l)
            if m: optn=int(m.group(1))
            else:                                   # 漏了编号 → 按顺序补
                body=re.sub(r'^#选\s*','',l).strip()
                optn+=1; l=f'#选 {optn} {body}'
        out.append(l)
    txt='\n'.join(out)
    # 补 #大題: 按题号区间推断
    if not seen_dai:
        RANGE=[(1,6,1),(7,13,2),(14,19,3),(20,25,4),(26,35,5),(36,40,6),(41,45,7),
               (45,48,8),(49,56,9),(57,59,10),(60,61,11),(62,64,12),(65,66,13)]
        res=[];cur=None
        for l in txt.split('\n'):
            m=re.match(r'^#題 (\d+)',l)
            if m:
                n=int(m.group(1))
                d=next((d for a,b,d in RANGE if a<=n<=b),None)
                if d and d!=cur: res.append(f'#大題 問題{d}'); cur=d
            res.append(l)
        txt='\n'.join(res)
    # 删掉引用了不存在文章块的 @文
    pas=set(re.findall(r'^#文 (\S+)',txt,re.M))
    txt=re.sub(r'(^#題 \d+)\s*[@＠]文\s*(\S+)',
               lambda m: m.group(1) if m.group(2) not in pas else m.group(0), txt, flags=re.M)
    return txt

def pick_files(sess):
    d=os.path.join(ROOT,'exams','ocr',sess)
    if not os.path.isdir(d): return None,None
    fs=glob.glob(d+'/*.txt')
    paper=None; script=None
    for f in sorted(fs,key=lambda x:-os.path.getsize(x)):
        n=os.path.basename(f)
        if '译文' in n: continue
        if ('真题' in n or '试题' in n or '試験' in n) and paper is None: paper=f
        if ('听力原文' in n or '解析' in n) and script is None: script=f
    if paper is None and fs: paper=sorted(fs,key=lambda x:-os.path.getsize(x))[0]
    return paper,script

def convert(sess,sec,maxround=3,model=None):
    paper,script=pick_files(sess)
    if not paper: print(f"  {sess}: 找不到 OCR 文件"); return False
    src=open(paper,encoding='utf-8',errors='ignore').read()
    if sec=='聴解' and script:
        src+="\n\n===== 以下是听力原文(台本) =====\n"+open(script,encoding='utf-8',errors='ignore').read()
    # 控制长度: 聴解只保留后半, 其余保留前部
    LIM=110000
    if len(src)>LIM: src=src[:LIM//2]+"\n…(略)…\n"+src[-LIM//2:]
    sysmsg=COMMON.format(exam=sess,rules=RULES[sec])
    msgs=[{"role":"system","content":sysmsg},{"role":"user","content":"【OCR 文本】\n"+src}]
    out=os.path.join(ROOT,'converted',f'{sess}_{sec}.txt')
    if model and model!=MODEL: out=os.path.join(ROOT,'converted',f'{sess}_{sec}.{model}.txt')
    for rd in range(maxround):
        t0=time.time(); txt,usage=call(msgs,model=model)
        txt=re.sub(r'^```[a-z]*\n?|```$','',txt.strip(),flags=re.M)
        txt=normalize(txt)
        os.makedirs(os.path.dirname(out),exist_ok=True)
        open(out,'w',encoding='utf-8').write(txt if txt.endswith('\n') else txt+'\n')
        r=subprocess.run([sys.executable,os.path.join(ROOT,'ocr','check_format.py'),out],
                         capture_output=True,text=True)
        tok=usage.get('total_tokens','?')
        if '✅ 通过' in r.stdout:
            print(f"  {sess}_{sec}: ✅ 通过 (第{rd+1}轮, {tok} tokens, {time.time()-t0:.0f}s)")
            return True
        prob='\n'.join(l for l in r.stdout.split('\n')
                       if any(k in l for k in ('⚠','选项不全','缺答案','格式错误','L')))[:2500]
        print(f"  {sess}_{sec}: 第{rd+1}轮未通过 ({tok} tokens) → 回灌报错重试")
        msgs=msgs[:2]+[{"role":"assistant","content":txt[:60000]},
                       {"role":"user","content":"校验未通过, 报错如下。请只输出修正后的完整文件, 不要解释:\n"+prob}]
    print(f"  {sess}_{sec}: ❌ {maxround}轮后仍未通过, 保留最后一版")
    return False

if __name__=='__main__':
    a=sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0]=='--all':
        todo=[]
        for s in ('2021-07','2021-12','2022-07','2022-12','2023-07','2023-12','2024-07'):
            for sec in ('言語知識','読解','聴解'): todo.append((s,sec))
    else:
        todo=[(a[0],a[1])] if len(a)>1 else [(a[0],x) for x in ('言語知識','読解','聴解')]
    ok=0
    for s,sec in todo:
        try:
            ok+=convert(s,sec)
        except Exception as e:
            print(f"  {s}_{sec}: 异常 {e}")
    print(f"\n完成 {ok}/{len(todo)}")
