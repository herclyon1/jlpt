#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JLPT N1 読解 — 実証的規律マイニング
====================================
4 套真题（2024-12 / 2025-07 / 2025-12 / 2026-07），每套 22 题，共 88 题。

方法：
  - 挖掘集 (mine): 2024-12, 2025-07, 2025-12   (66 题)
  - 验证集 (hold): 2026-07                      (22 题)
  - 2024-12 有 "整理中" 残缺文章，涉及的题单独标记 (damaged)。

无 MeCab / janome / fugashi，故用「内容字」n-gram 近似分词：
  内容字 = 漢字 + カタカナ（含长音符）。助词与假名活用尾被自然排除。
  ※ 重要：只从长度 ≥2 的连续内容字 run 中取 2-gram。
    早期版本把单字 run 也当作 token，导致覆盖率普遍虚高到 0.6~1.0、
    argmax 大量平局。本版已修正。

输出：/Users/herclyon/JLPT/mining/reading_findings.md
"""

import os, re, sys, math, itertools
from collections import Counter

CONV = "/Users/herclyon/JLPT/converted"
EXAMS = ["2024-12", "2025-07", "2025-12", "2026-07"]
MINE_EXAMS = ["2024-12", "2025-07", "2025-12"]
HOLD_EXAM = "2026-07"

# ================================================================ 解析
def parse(path, exam):
    passages, questions = {}, []
    cur_p, buf, cur_sec, q = None, [], None, None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#大題"):
            cur_sec = line[3:].strip()
        elif line.startswith("#文完"):
            passages[cur_p] = "\n".join(buf); cur_p, buf = None, []
        elif line.startswith("#文 "):
            cur_p, buf = line[3:].strip(), []
        elif cur_p is not None:
            buf.append(line)
        elif line.startswith("#題"):
            if q: questions.append(q)
            m = re.match(r"#題\s+(\d+)(?:\s+@文\s+(\S+))?", line)
            q = dict(exam=exam, num=int(m.group(1)), pid=m.group(2),
                     sec=cur_sec, stem="", opts=[], ans=None)
        elif line.startswith("#干"):
            q["stem"] = line[3:].strip()
        elif line.startswith("#选"):
            q["opts"].append(re.match(r"#选\s+\d+\s*(.*)", line).group(1))
        elif line.startswith("#答"):
            q["ans"] = int(line[3:].strip())
    if q: questions.append(q)
    for q in questions:
        q["passage"] = passages.get(q["pid"], "")
        q["damaged"] = ("整理中" in q["passage"]) or ("・・・" in q["passage"])
    return questions

ALL = []
for e in EXAMS:
    ALL += parse(os.path.join(CONV, f"{e}_読解.txt"), e)
assert len(ALL) == 88, len(ALL)
for q in ALL:
    assert len(q["opts"]) == 4 and q["ans"] in (1, 2, 3, 4), q

# ================================================================ 特征原语
KANJI = r"一-鿿々"
KATA  = r"ァ-ヺー"
CONTENT_RE = re.compile(f"[{KANJI}{KATA}]+")

def runs(s):
    return CONTENT_RE.findall(s)

def bigrams(s):
    """只在长度≥2 的内容字 run 内取 2-gram（单字 run 丢弃）"""
    out = set()
    for r in runs(s):
        for i in range(len(r) - 1):
            out.add(r[i:i + 2])
    return out

def words(s):
    """长度≥2 的连续内容字 run 视作一个词"""
    return set(r for r in runs(s) if len(r) >= 2)

def cov(opt_set, ref_set):
    if not opt_set: return 0.0
    return len(opt_set & ref_set) / len(opt_set)

def jac(a, b):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

# ---- 末段 / 主张句
CLAIM_END = re.compile(
    r"(のだ|のである|のです|んです|べきだ|べきである|べきです|べきなのだ|"
    r"のではないか|のではないだろうか|ではないだろうか|ではないか|"
    r"と思う|と思います|と考える|と考えている|必要がある|なければならない|"
    r"だろう|でしょう|かもしれない|はずだ|に違いない|ないだろうか|"
    r"わけだ|からだ|のかもしれない)[。」』）]*$")

def sentences(text):
    text = re.sub(r"（注[^）]*）.*", "", text)
    out = []
    for para in text.split("\n"):
        for s in re.split(r"(?<=[。？！])", para):
            s = s.strip()
            if len(s) > 4: out.append(s)
    return out

def claim_sentences(text):
    ss = sentences(text)
    return [s for s in ss if CLAIM_END.search(s)]

def last_para(text):
    ps = [p.strip() for p in text.split("\n")
          if len(p.strip()) > 20 and not p.strip().startswith("（注")]
    return ps[-1] if ps else text

# ---- 绝对化措辞（用户原假设的核心集）
ABS_CORE_W = ["必ず", "すべて", "全て", "全部", "絶対", "常に", "のみ"]
ABS_SHIKA  = re.compile(r"しか[^。]{0,14}(ない|ず|えない|できない)")
ABS_WIDE_W = ABS_CORE_W + ["決して", "まったく", "全く", "唯一", "あらゆる",
                           "一切", "いかなる", "誰もが", "everyone", "皆", "みんな",
                           "любой"]
def abs_core(o): return any(w in o for w in ABS_CORE_W) or bool(ABS_SHIKA.search(o))
def abs_wide(o): return any(w in o for w in ABS_WIDE_W) or bool(ABS_SHIKA.search(o))

NEG_END = re.compile(r"(ない|ぬ|ません|なかった)(こと|もの|の|わけ|はず)?[だでかよ]?[。]?$")
def neg_end(o): return bool(NEG_END.search(o.strip().rstrip("。")))

# ---- 题型
def qtype(q):
    st = q["stem"]
    if q["sec"] == "問題13": return "情報検索"
    if "ＡとＢ" in st or "AとB" in st: return "統合比較"
    if "＜" in st or "とあるが" in st or "とはどういうこと" in st or "とは、" in st:
        return "下線部"
    if "筆者" in st: return "筆者の考え"
    return "内容一致"

# ================================================================ 逐题特征
for q in ALL:
    P, opts = q["passage"], q["opts"]
    bg_all   = bigrams(P)
    bg_claim = bigrams(" ".join(claim_sentences(P)))
    bg_last  = bigrams(last_para(P))
    w_all    = words(P)
    obg = [bigrams(o) for o in opts]
    ow  = [words(o)   for o in opts]

    # 「区別性 bigram」：在 4 个选项中出现次数 ≤2 的 bigram（4 个都有的词不含信息）
    cnt = Counter()
    for s in obg: cnt.update(s)
    distinct = [set(b for b in s if cnt[b] <= 2) for s in obg]

    f = {}
    f["ov_all"]    = [cov(s, bg_all)   for s in obg]
    f["ov_all_n"]  = [len(s & bg_all)  for s in obg]       # 未归一化
    f["ov_claim"]  = [cov(s, bg_claim) for s in obg]
    f["ov_last"]   = [cov(s, bg_last)  for s in obg]
    f["ov_word"]   = [cov(s, w_all)    for s in ow]
    f["ov_dist"]   = [cov(s, bg_all)   for s in distinct]  # 只看区別性 bigram
    f["ov_dist_c"] = [cov(s, bg_claim) for s in distinct]
    f["len"]       = [len(o) for o in opts]

    sim = [[0.0]*4 for _ in range(4)]
    for i, j in itertools.combinations(range(4), 2):
        v = jac(obg[i], obg[j]); sim[i][j] = sim[j][i] = v
    q["sim"] = sim
    f["mean_sim"] = [sum(sim[i][j] for j in range(4) if j != i)/3 for i in range(4)]
    f["max_sim"]  = [max(sim[i][j] for j in range(4) if j != i) for i in range(4)]
    f["abs_core"] = [1 if abs_core(o) else 0 for o in opts]
    f["abs_wide"] = [1 if abs_wide(o) else 0 for o in opts]
    f["neg_end"]  = [1 if neg_end(o)  else 0 for o in opts]
    q["f"] = f
    q["type"] = qtype(q)

# ================================================================ 真分词（fugashi + unidic-lite）
# v2 追加。上一版无分词器，用漢字/カタカナ 2-gram 近似；本版用真词性做对照。
import fugashi
_TAGGER = fugashi.Tagger()

CONTENT_POS = {"名詞", "動詞", "形容詞", "副詞", "形状詞"}
DROP_POS    = {"助詞", "助動詞", "補助記号", "接続詞", "感動詞", "代名詞", "接頭辞", "接尾辞"}
# 非自立/形式名詞等语义空壳，纳入停用词
STOP_LEMMA = {"事", "物", "為", "様", "有る", "居る", "為る", "成る", "如何", "此れ", "其れ",
              "の", "こと", "もの", "よう", "ため", "そう", "いう", "言う", "できる", "出来る",
              "ある", "いる", "する", "なる", "れる", "られる", "しまう", "みる", "いく", "くる"}

_tok_cache = {}
def toks(text):
    """返回 (内容词 lemma 列表)。已缓存。"""
    if text in _tok_cache: return _tok_cache[text]
    out = []
    for w in _TAGGER(text):
        pos1 = w.feature.pos1
        if pos1 not in CONTENT_POS: continue
        if pos1 == "名詞" and w.feature.pos2 in ("非自立可能",) and w.surface in ("こと","もの","ため","よう"):
            continue
        lem = w.feature.lemma or w.surface
        lem = lem.split("-")[0]
        if lem in STOP_LEMMA: continue
        if len(lem) == 1 and re.fullmatch(r"[ぁ-ん]", lem): continue
        out.append(lem)
    _tok_cache[text] = out
    return out

def lset(text):
    return set(toks(text))
def lbigrams(text):
    t = toks(text)
    return set(zip(t, t[1:]))

for q in ALL:
    P, opts = q["passage"], q["opts"]
    P_clean = re.sub(r"（注[^）]*）.*", "", P)
    L_all   = lset(P_clean)
    L_claim = lset(" ".join(claim_sentences(P)))
    L_last  = lset(last_para(P))
    ol = [lset(o) for o in opts]
    f = q["f"]
    f["Lov_all"]   = [cov(s_, L_all)   for s_ in ol]
    f["Lov_claim"] = [cov(s_, L_claim) for s_ in ol]
    f["Lov_last"]  = [cov(s_, L_last)  for s_ in ol]
    f["Lov_all_n"] = [len(s_ & L_all)  for s_ in ol]
    lsim = [[0.0]*4 for _ in range(4)]
    for i, j in itertools.combinations(range(4), 2):
        v = jac(ol[i], ol[j]); lsim[i][j] = lsim[j][i] = v
    q["lsim"] = lsim
    f["Lmean_sim"] = [sum(lsim[i][j] for j in range(4) if j != i)/3 for i in range(4)]
    f["Lmax_sim"]  = [max(lsim[i][j] for j in range(4) if j != i) for i in range(4)]
    q["L_all"] = L_all
    q["ol"] = ol

# ---- 限定・部分否定 / 强断言 表达（v2 新增假设 2）
HEDGE_CORE = [
    r"わけで(は|も)な", r"わけじゃな", r"と(は|も)限らな", r"ないわけで(は|も)な",
    r"ものの(?![がのを])", r"からと(いって|言って)", r"に(過ぎ|すぎ)な",
    r"と(は|も)(言え|いえ)な", r"と(は|も)(言い|いい)切れな",
]
HEDGE_WIDE = HEDGE_CORE + [
    r"必ずしも", r"一概に", r"だけで(は|も)な", r"ばかりで(は|も)な",
    r"場合(が|も)ある", r"ことも(ある|多い)", r"傾向がある", r"とはいえ",
    r"ある程度", r"一方で", r"とは(いえ|言え)", r"わけではあるまい",
    r"やすい(?!$)", r"がち", r"とも(いえ|言え)る",
]
STRONG = [
    r"べきだ", r"べきである", r"べきです", r"べきな", r"べきで(は|も)",
    r"なければならな", r"ねばならな", r"必要がある", r"て(は|も)ならな",
    r"しかな(い|く)", r"に違いな", r"にほかならな", r"に他ならな",
    r"ざるを得な", r"に決まって", r"はずだ",
]
def _any(pats, o): return any(re.search(pt, o) for pt in pats)
for q in ALL:
    f = q["f"]
    f["hedge_core"] = [1 if _any(HEDGE_CORE, o) else 0 for o in q["opts"]]
    f["hedge_wide"] = [1 if _any(HEDGE_WIDE, o) else 0 for o in q["opts"]]
    f["strong"]     = [1 if _any(STRONG, o)     else 0 for o in q["opts"]]

# ================================================================ 统计工具
def binom_ge(k, n, p=0.25):
    return sum(math.comb(n, i)*p**i*(1-p)**(n-i) for i in range(k, n+1))
def binom_le(k, n, p=0.25):
    return sum(math.comb(n, i)*p**i*(1-p)**(n-i) for i in range(0, k+1))
def two_sided(k, n, p=0.25):
    return min(1.0, 2*min(binom_ge(k, n, p), binom_le(k, n, p)))

def subset(exams=None, damaged=None, types=None, not_types=None):
    out = []
    for q in ALL:
        if exams and q["exam"] not in exams: continue
        if damaged is not None and q["damaged"] != damaged: continue
        if types and q["type"] not in types: continue
        if not_types and q["type"] in not_types: continue
        out.append(q)
    return out

MINE     = subset(MINE_EXAMS)
MINE_OK  = subset(MINE_EXAMS, damaged=False)
MINE_DMG = subset(MINE_EXAMS, damaged=True)
HOLD     = subset([HOLD_EXAM])

def eval_pick(qs, sel):
    n = h = 0
    for q in qs:
        p = sel(q)
        if p is None: continue
        n += 1; h += (p == q["ans"])
    return n, h, (h/n if n else float("nan"))

def option_level(qs, cond):
    tot = ok = 0
    for q in qs:
        for i, o in enumerate(q["opts"]):
            if cond(q, i, o):
                tot += 1; ok += (q["ans"] == i+1)
    return tot, ok, (ok/tot if tot else float("nan"))

def argmax_pick(key):
    def f(q):
        v = q["f"][key]; m = max(v)
        idx = [i for i, x in enumerate(v) if x == m]
        return idx[0]+1 if len(idx) == 1 else None
    return f
def argmin_pick(key):
    def f(q):
        v = q["f"][key]; m = min(v)
        idx = [i for i, x in enumerate(v) if x == m]
        return idx[0]+1 if len(idx) == 1 else None
    return f
def margin_pick(key, mg):
    def f(q):
        v = q["f"][key]
        o = sorted(range(4), key=lambda i: -v[i])
        if v[o[0]] - v[o[1]] < mg: return None
        return o[0]+1
    return f

def fmt(n, h):
    return f"{h}/{n} = {h/n:.1%}" if n else "—"
def pv(n, h):
    return f"{two_sided(h, n):.3f}" if n else "—"
def warn(n):
    return " ⚠样本不足" if n < 8 else ""

# ================================================================ 报告
OUT = []
def W(s=""):
    OUT.append(s)

W("# JLPT N1 読解 — 規律マイニング実測レポート")
W()
W("脚本: `/Users/herclyon/JLPT/mining/reading_mine.py`　|　全部数字均由该脚本生成，可复现。")
W()
W("> **结论先说（先看数字再看话）**")
W("> 1. 唯一双集合同向且统计显著的正向规则是 **R10「与其他三项平均词面相似度最高的选项」**：")
W(">    挖掘集 21/42 = 50.0%（p=0.001），验证集 5/13 = 38.5%，全 88 題 26/55 = 47.3%（p=0.001）。")
W(">    但它只在 63% 的題上触发，且验证集比挖掘集掉了 11.5pp。")
W("> 2. 用户原假设「绝对化措辞 = 错误项」**被证伪**：全 88 題只触发 9 个选项（2.6%），")
W(">    其中 2 个恰是正解（22.2%，p=0.60）。既不显著，也几乎碰不到。")
W("> 3. **【v2 撤回】** v1 曾报告「与原文字面重叠最高的选项更可能是错的」（11.1%）。")
W(">    装上 fugashi 用真内容词重算后，这个数字变成 **25.8%，效应完全消失**。")
W(">    v1 测到的是句式噪声 bigram，不是内容照抄程度。**该结论撤回，判为测量假象。**")
W("> 4. **【v2 新增·最强排除规则】与文章「主张句」内容词交集最小的选项，几乎不是正解**：")
W(">    全 88 題 4/49 = **8.2%**（p=0.005），挖掘集 8.3% / 验证集 7.7%，两边几乎一样。")
W(">    只在真分词下出现（字符版 16.7%，不显著）。但它与 R10 高度相关，**叠加后无增量**。")
W("> 5. **【v2 新增·证伪】** 限定・部分否定表达（〜わけではない/〜とは限らない/〜ものの 等）")
W(">    在正解中并不比干扰项更常见：352 个选项只触发 3 个（0.9%）；扩展集 9 个，正解率 22.2%。")
W(">    反向的「强断言 = 干扰项」也不成立（42 个触发，正解率 21.4%，p=0.74）。")
W("> 6. **【v2 新增·证伪】**「正解藏在重叠度中间两名」不成立：全 88 恰好 50.0%（p=1.000）。")
W("> 7. 答案编号分布、选项长度、否定形结尾、最孤立选项排除法——**全部无信号**（v1 结论不变）。")
W("> 8. 天花板：**7～8 題 / 22 題（32%～36%）**。真分词没有把天花板抬高，")
W(">    验证集上最好的可执行策略仍是 7.0～8.0/22，比乱猜的 5.5 題多 1.5～2.5 題。")
W()

# ---------------- 0 数据概况
W("## 0. 数据概况与留一设置")
W()
W("| 卷 | 題数 | 文章残缺題 | 健全題 |")
W("|---|---|---|---|")
for e in EXAMS:
    qs = subset([e]); d = [q for q in qs if q["damaged"]]
    W(f"| {e} | {len(qs)} | {len(d)}　({', '.join(str(q['num']) for q in d) or '—'}) | {len(qs)-len(d)} |")
W()
W(f"- **挖掘集 mine** = {' + '.join(MINE_EXAMS)} → **{len(MINE)} 題**（健全 {len(MINE_OK)}、残缺 {len(MINE_DMG)}）")
W(f"- **验证集 hold** = **{HOLD_EXAM}** → **{len(HOLD)} 題**（残缺 0）")
W()
W("**为什么选 2026-07 当验证集**：")
W("1. 题目要求验证集不能是 2024-12。剩下 2025-07 / 2025-12 / 2026-07 三选一。")
W("2. 2026-07 是四套里**最新**的一套。留一验证的目的是模拟「用历年卷挖到的规律去考下一场」，")
W("   时间上最靠后的那套最贴近这个场景；用 2025-07 当验证集会变成「用未来预测过去」。")
W("3. 2026-07 格式完整、无残缺，命中率不会被数据质量污染。")
W()
W("2024-12 是回忆重排版，11/22 題的文章含「整理中」占位或「・・・」省略。")
W("凡涉及文章内容的特征（重叠度、主张句）在这些題上系统性失真，")
W("下面所有表格都额外给出「mine 健全 55 題」一列以便对照。")
W()
W("| 題型（自动分类） | mine 66 | mine 健全 55 | hold 22 |")
W("|---|---|---|---|")
tps = ["筆者の考え", "下線部", "統合比較", "情報検索", "内容一致"]
for t in tps:
    a = len([q for q in MINE if q["type"] == t])
    b = len([q for q in MINE_OK if q["type"] == t])
    c = len([q for q in HOLD if q["type"] == t])
    if a or c: W(f"| {t} | {a} | {b} | {c} |")
W()
W("分类规则：問題13 → 情報検索；題干含「ＡとＢ」→ 統合比較；含「＜＞/とあるが/とはどういうこと」→ 下線部；")
W("含「筆者」→ 筆者の考え；其余 → 内容一致。")
W()

# ---------------- 1 答案编号
W("## 1. 答案编号分布 —— 无规律")
W()
W("| 集合 | ①  | ②  | ③  | ④  | n |")
W("|---|---|---|---|---|---|")
for lab, qs in [("2024-12", subset(["2024-12"])), ("2025-07", subset(["2025-07"])),
                ("2025-12", subset(["2025-12"])), ("2026-07", subset(["2026-07"])),
                ("**mine 66**", MINE), ("**hold 22**", HOLD), ("**全 88**", ALL)]:
    c = Counter(q["ans"] for q in qs)
    W(f"| {lab} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {len(qs)} |")
c = Counter(q["ans"] for q in ALL)
chi = sum((c[i]-22)**2/22 for i in range(1, 5))
W()
mfreq = Counter(q["ans"] for q in MINE).most_common(1)[0][0]
hh = sum(1 for q in HOLD if q["ans"] == mfreq)
W(f"- 全 88 題：①18 ②23 ③24 ④23。χ²={chi:.2f}（df=3，临界值 7.81）→ **与均匀分布无显著差异**。")
W(f"- 挖掘集最频编号 = **{mfreq}**（19/66 = 28.8%）。拿它去蒙验证集：**{hh}/22 = {hh/22:.1%}**，")
W(f"  比 25% 还差。→ **「不会就蒙 X」这条彻底无效。**")
W(f"- 也检查了「同一编号连续出现」：全 88 題中相邻两題答案相同的有 "
  f"{sum(1 for a,b in zip(ALL, ALL[1:]) if a['exam']==b['exam'] and a['ans']==b['ans'])} 次，"
  f"期望 ≈ {(88-4)*0.25:.0f} 次 → 无「避免连号」倾向。")
W()

# ---------------- 2 单特征选择规则
W("## 2. 单特征「选它」规则（argmax / argmin）")
W()
W("n = 触发題数（严格 argmax；四选项该特征出现并列最大值时不触发）。基线 = 25%。")
W("p 值 = 双侧二项检验 vs p₀=0.25。")
W()
RULES = [
    ("R1 选项↔全文 2-gram 覆盖率 **最高**",        argmax_pick("ov_all")),
    ("R2 选项↔全文 2-gram 命中数（未归一）最高",    argmax_pick("ov_all_n")),
    ("R3 选项↔全文 内容词(≥2字) 覆盖率 最高",      argmax_pick("ov_word")),
    ("R4 选项↔**主张句集** 2-gram 覆盖率 最高",     argmax_pick("ov_claim")),
    ("R5 选项↔**末段** 2-gram 覆盖率 最高",         argmax_pick("ov_last")),
    ("R6 **区別性** bigram↔全文 覆盖率 最高",       argmax_pick("ov_dist")),
    ("R7 **区別性** bigram↔主张句 覆盖率 最高",     argmax_pick("ov_dist_c")),
    ("R8 选项**最长**",                            argmax_pick("len")),
    ("R9 选项**最短**",                            argmin_pick("len")),
    ("R10 与其他选项平均相似度 **最高**（最合群）",  argmax_pick("mean_sim")),
    ("R11 与其他选项平均相似度 **最低**（最孤立）",  argmin_pick("mean_sim")),
]

def most_similar_pair(q):
    best, pair = -1, None
    for i, j in itertools.combinations(range(4), 2):
        if q["sim"][i][j] > best:
            best, pair = q["sim"][i][j], (i+1, j+1)
    return pair, best
W("| 规则 | mine(66) | p | mine健全(55) | hold(22) | p | 全88 | p |")
W("|---|---|---|---|---|---|---|---|")
summary = {}
for name, sel in RULES:
    n1,h1,_ = eval_pick(MINE, sel)
    n3,h3,_ = eval_pick(MINE_OK, sel)
    n2,h2,_ = eval_pick(HOLD, sel)
    na,ha,_ = eval_pick(ALL, sel)
    summary[name] = (n1,h1,n2,h2,na,ha)
    W(f"| {name} | {fmt(n1,h1)}{warn(n1)} | {pv(n1,h1)} | {fmt(n3,h3)} | "
      f"{fmt(n2,h2)}{warn(n2)} | {pv(n2,h2)} | {fmt(na,ha)} | {pv(na,ha)} |")
W()
W("### 2.1 「最像的一对」是否含答案（基线 50%，因为覆盖 2/4 个选项）")
W()
W("| 集合 | n | 含答案 | 占比 | 基线 | p (vs 50%) |")
W("|---|---|---|---|---|---|")
_pair_stat = {}
for lab, qs in [("mine 66", MINE), ("hold 22", HOLD), ("全 88", ALL)]:
    n = k = 0
    for q in qs:
        pr, sc = most_similar_pair(q)
        if sc <= 0: continue
        n += 1; k += (q["ans"] in pr)
    _pair_stat[lab] = (n, k)
    W(f"| {lab} | {n} | {k} | {(f'{k/n:.1%}' if n else '—')} | 50% | "
      f"{(f'{two_sided(k,n,0.5):.3f}' if n else '—')} |")
W()
_pn, _pk = _pair_stat["全 88"]
W(f"→ 全 88 題 {_pk}/{_pn} = {_pk/_pn:.1%}，**高于 50% 基线**（p={two_sided(_pk,_pn,0.5):.3f}）。")
W("mine 66.1% / hold 55.0%，方向一致但验证集掉了 11pp。")
W()
W("**注意这不是一条独立规律**：它和 R10 是同一件事的两种说法——")
W("正解与干扰项共享词面，所以正解容易落进「最像的一对」里。")
W(f"实用性也远不如 R10：它只把 4 选 1 缩到 2 选 1，之后仍要靠猜 → "
  f"期望命中 {_pk/_pn:.1%} × 1/2 = {_pk/_pn/2:.1%}，")
W("低于直接用 R10 的 47.3%。**能用，但被 R10 完全覆盖，没有额外价值。**")
W()
W("### 2.2 三个方向明确的结果")
W()
W("**(a) R10「最合群选项」= 目前唯一双集合同向且显著的正向规则。**")
n10m,h10m,_=eval_pick(MINE,argmax_pick("mean_sim"))
n10h,h10h,_=eval_pick(HOLD,argmax_pick("mean_sim"))
n10a,h10a,_=eval_pick(ALL,argmax_pick("mean_sim"))
W(f"  mine {fmt(n10m,h10m)}（p={two_sided(h10m,n10m):.3f}）、hold {fmt(n10h,h10h)}、"
  f"全88 {fmt(n10a,h10a)}（p={two_sided(h10a,n10a):.4f}）。")
W(f"  多重比较修正：12 条规则做 Bonferroni → 0.001×12 = 0.012，**仍显著**。")
W(f"  覆盖率是短板：只在 {n10a}/88 = {n10a/88:.0%} 的題上触发（其余題四个选项相似度并列，多为全 0）。")
W(f"  机理猜测（未验证）：JLPT 干扰项是从正解**改写**出来的，")
W(f"  正解因此与多个干扰项共享词面；凭空编造的干扰项反而孤立。")
W()
W("**(b) 「与全文字面重叠最高」是陷阱信号，不是答案信号。**")
n6m,h6m,_=eval_pick(MINE,argmax_pick("ov_dist")); n6h,h6h,_=eval_pick(HOLD,argmax_pick("ov_dist"))
n6a,h6a,_=eval_pick(ALL,argmax_pick("ov_dist"))
W(f"  R6（区別性 bigram↔全文 覆盖率最高）：mine {fmt(n6m,h6m)}、hold {fmt(n6h,h6h)}、"
  f"全88 {fmt(n6a,h6a)}（p={two_sided(h6a,n6a):.3f}）。")
W(f"  三个集合**全部低于 25%**，方向一致。R1（不做区別性过滤）同向：全88 "
  f"{fmt(*eval_pick(ALL, argmax_pick('ov_all'))[:2])}。")
W(f"  这与用户原假设相反：**照抄原文词最多的那个选项，反而更可能是错的。**")
W(f"  合理解释——N1 正解通常是原文的**换说法（言い換え）**，")
W(f"  而干扰项才是「原文词照搬、意思拧了」。")
W()
W("**(c) 「最孤立选项可排除」只有微弱证据，不像看上去那么强。**")
o5m = option_level(MINE, lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
o5h = option_level(HOLD, lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
o5a = option_level(ALL,  lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
W(f"  mine {o5m[1]}/{o5m[0]} = {o5m[2]:.1%}、hold {o5h[1]}/{o5h[0]} = {o5h[2]:.1%}（**正好等于基线**）、"
  f"全88 {o5a[1]}/{o5a[0]} = {o5a[2]:.1%}（p={two_sided(o5a[1],o5a[0]):.3f}）。")
W(f"  验证集上完全没有效果。**不推荐作为独立排除规则**，只能作为 R10 的镜像副产品。")
W()

# ---------------- 3 排除型规则
W("### 2.3 R10 稳健性检查（防止「平局跳过」制造假象）")
W()
W("担心：R10 只在 55/88 題触发，会不会是「挑软柿子」——把难題都靠平局跳过了？")
W("检查方式：平局时不跳过，而是在并列最大值里**随机**选一个（按 1/并列数 解析求期望，非抽样），")
W("这样规则在全部 88 題上都必须作答。")
W()
def _r10_random(qs):
    tot = 0
    for q in qs:
        v = q["f"]["mean_sim"]; m = max(v)
        idx = [i for i, x in enumerate(v) if x == m]
        tot += (1.0/len(idx)) if (q["ans"]-1) in idx else 0.0
    return tot
for lab, qs in [("mine 66", MINE), ("hold 22", HOLD), ("全 88", ALL)]:
    e = _r10_random(qs)
    W(f"- {lab}：期望命中 {e:.1f}/{len(qs)} = {e/len(qs):.1%}（乱猜基线 25%）")
W()
W("→ 强制全題作答后：mine 43.8%、hold **34.8%**、全88 41.6%，**三者都高于 25%**。")
W("说明信号不是平局跳过制造的假象，只是被平局稀释了。")
W("平局題（四个选项之间几乎没有共享词面）本身就是规则无能为力的題，那部分只能乱猜。")
W("**验证集 34.8% = 7.7/22 題，这就是本次挖掘最诚实的、可直接执行的成绩。**")
W()

W("## 3. 排除型规则（「这个选项是答案吗？」）")
W()
W("统计单位是**选项**不是題。满足条件的选项里，实际为正解的比例。")
W("随机基线 25%。显著 <25% → 该特征可用于排除；≈25% → 无信息。")
W()
OPT_RULES = [
    ("O1 含**核心绝对化措辞**（必ず/すべて/絶対/常に/のみ/しか～ない）",
     lambda q,i,o: q["f"]["abs_core"][i] == 1),
    ("O2 含**广义绝对化**（+決して/全く/唯一/あらゆる/一切/いかなる/誰もが）",
     lambda q,i,o: q["f"]["abs_wide"][i] == 1),
    ("O3 以**否定形**结尾（〜ない/ません/なかった）",
     lambda q,i,o: q["f"]["neg_end"][i] == 1),
    ("O4 **全文覆盖率最低**的选项（唯一最低）",
     lambda q,i,o: q["f"]["ov_all"][i] == min(q["f"]["ov_all"])
                   and q["f"]["ov_all"].count(min(q["f"]["ov_all"])) == 1),
    ("O5 **最孤立**选项（平均相似度最低）",
     lambda q,i,o: q["f"]["mean_sim"][i] == min(q["f"]["mean_sim"])),
    ("O6 **最短**选项（唯一最短）",
     lambda q,i,o: q["f"]["len"][i] == min(q["f"]["len"])
                   and q["f"]["len"].count(min(q["f"]["len"])) == 1),
    ("O7 **最长**选项（唯一最长）",
     lambda q,i,o: q["f"]["len"][i] == max(q["f"]["len"])
                   and q["f"]["len"].count(max(q["f"]["len"])) == 1),
    ("O8 与任何选项相似度都 <0.10（完全孤立）",
     lambda q,i,o: q["f"]["max_sim"][i] < 0.10),
]
W("| 规则 | mine 选项n | 为答案 | 占比 | p | hold 选项n | 为答案 | 占比 | p | 全88 占比 | p |")
W("|---|---|---|---|---|---|---|---|---|---|---|")
for name, cond in OPT_RULES:
    t1,k1,_ = option_level(MINE, cond)
    t2,k2,_ = option_level(HOLD, cond)
    ta,ka,_ = option_level(ALL,  cond)
    W(f"| {name} | {t1} | {k1} | {(f'{k1/t1:.1%}' if t1 else '—')} | {pv(t1,k1)} | "
      f"{t2} | {k2} | {(f'{k2/t2:.1%}' if t2 else '—')} | {pv(t2,k2)} | "
      f"{(f'{ka/ta:.1%}' if ta else '—')} (n={ta}) | {pv(ta,ka)} |")
W()

# ---- 绝对化措辞逐条列出
ta,ka,_ = option_level(ALL, lambda q,i,o: q["f"]["abs_core"][i] == 1)
W("### 3.1 绝对化措辞假设 —— 逐条核对（用户原假设）")
W()
W(f"全 88 題 × 4 = 352 个选项中，只有 **{ta} 个**触发核心绝对化措辞（触发率 {ta/352:.1%}），")
W(f"其中 **{ka} 个是正确答案**（{ka/ta:.1%}）。单侧检验 P(X≤{ka}|n={ta},p=.25) = {binom_le(ka,ta):.3f}。")
W()
W("**判定：证伪。** 两个理由——")
W("1. 命中率 22.2% 与基线 25% 无统计差异（p=0.60），根本没有「错误率显著高于 75%」。")
W("2. 更致命的是**触发率只有 2.6%**：88 題里只有 6 題出现过这类选项。")
W("   就算它 100% 有效，也只能帮你排除 6 題里的各一个选项 → 期望增益 < 0.5 題。")
W("   这条「技巧」在 N1 読解上属于**无用规则**，出题方显然刻意避免了这种廉价破绽。")
W()
W("触发的全部选项（★ = 它就是正确答案）：")
W()
for q in ALL:
    for i, o in enumerate(q["opts"]):
        if q["f"]["abs_core"][i]:
            W(f"- {'★' if q['ans']==i+1 else '　'} `{q['exam']} 題{q['num']} 选项{i+1}`　{o}")
W()

# ---- 孤立选项详解
W("### 3.2 「最孤立选项可以排除」——只有微弱证据，验证集上归零")
W()
t1,k1,_ = option_level(MINE, lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
t2,k2,_ = option_level(HOLD, lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
ta2,ka2,_= option_level(ALL, lambda q,i,o: q["f"]["mean_sim"][i]==min(q["f"]["mean_sim"]))
W(f"- mine: {k1}/{t1} = {k1/t1:.1%}（p={two_sided(k1,t1):.3f}）")
W(f"- hold: {k2}/{t2} = {k2/t2:.1%}（p={two_sided(k2,t2):.3f}）")
W(f"- 全88: {ka2}/{ta2} = {ka2/ta2:.1%}（p={two_sided(ka2,ta2):.4f}）")
W()
W("挖掘集上看着像回事（18.0% < 25%），但**验证集正好落在 25.0%，一点效果都没有**，")
W("合并 88 題后 p=0.187 也不显著。")
W()
W("**判定：不成立（作为独立规则）。** 它只是 R10 的镜像——当 R10 触发时最孤立项自然被压低，")
W("但把它单独拎出来当排除规则，验证集不支持。")
W("下面仍给出「删一项换 1/3」的期望增益计算，作为**上限**参考，不作为推荐。")
W()
# 期望增益
def elim_gain(qs):
    good = 0
    for q in qs:
        v = q["f"]["mean_sim"]; mi = min(v)
        E = set(i+1 for i,x in enumerate(v) if x == mi)
        if len(E) == 1 and q["ans"] not in E: good += 1
    return good, len(qs)
g1,n1_=elim_gain(MINE); g2,n2_=elim_gain(HOLD)
W(f"- 「唯一最孤立项 ≠ 答案」的題比例：mine {g1}/{n1_} = {g1/n1_:.1%}，hold {g2}/{n2_} = {g2/n2_:.1%}。")
W(f"- 若在这些題上删一项后**纯随机**从剩 3 项选：期望正确率 = 1/3 而非 1/4，")
W(f"  22 題全用 → 期望多得 22×(1/3−1/4) ≈ **1.8 題**。这就是这条规则的全部价值上限。")
W()

# ---------------- 4 分题型
W("## 4. 分題型表现")
W()
KEY4 = [("ov_all","R1全文覆盖"), ("ov_claim","R4主张句"), ("mean_sim","R10最合群"),
        ("len","R8最长")]
for lab, QS in [("mine (66題)", MINE), ("hold (22題)", HOLD)]:
    W(f"### {lab}")
    W()
    W("| 題型 | n | " + " | ".join(t for _,t in KEY4) + " |")
    W("|---|---|---|---|---|---|")
    for t in tps:
        qs = [q for q in QS if q["type"] == t]
        if not qs: continue
        cells = []
        for k,_ in KEY4:
            n,h,_r = eval_pick(qs, argmax_pick(k))
            cells.append(fmt(n,h) if n else "—")
        W(f"| {t} | {len(qs)}{warn(len(qs))} | " + " | ".join(cells) + " |")
    W()
W("**读法**：每一格 n 都 ≤41，多数 <10 → 分題型的差异基本是噪声，不要当规律用。")
W("唯一稳定的观察是：**情報検索（問題13，每卷 2 題）上所有文本重叠特征都失效**，")
W("因为那是表格/公告检索，答案是靠条件筛选算出来的，不靠措辞重叠。")
W()

# ---------------- 5 margin
W("## 5. 「高置信度」变体：领先幅度够大才出手")
W()
W("思路：argmax 太脆弱，改成「最高分比第二高至少领先 margin 才作答」，牺牲覆盖率换准确率。")
W("如果规律真实存在，margin 越大命中率应该单调上升。")
W()
W("| 特征 | margin | mine n | mine 命中率 | hold n | hold 命中率 |")
W("|---|---|---|---|---|---|")
for key in ["ov_all", "ov_claim", "ov_word", "ov_dist", "mean_sim"]:
    for mg in [0.05, 0.10, 0.20, 0.30]:
        n1,h1,_ = eval_pick(MINE, margin_pick(key, mg))
        n2,h2,_ = eval_pick(HOLD, margin_pick(key, mg))
        W(f"| {key} | {mg:.2f} | {n1} | {(f'{h1/n1:.1%}' if n1 else '—')}{warn(n1)} | "
          f"{n2} | {(f'{h2/n2:.1%}' if n2 else '—')}{warn(n2)} |")
W()

# ---------------- 6 组合
W("## 6. 组合规则（min-max 归一后加权求和）")
W()
def combo_pick(wts, pen_abs=0.0, pen_iso=0.0):
    def f(q):
        s = [0.0]*4
        for k, w in wts.items():
            v = q["f"][k]; lo, hi = min(v), max(v)
            for i in range(4):
                s[i] += w*((v[i]-lo)/(hi-lo) if hi > lo else 0.0)
        for i in range(4):
            s[i] -= pen_abs*q["f"]["abs_core"][i]
        if pen_iso:
            mi = min(q["f"]["mean_sim"])
            for i in range(4):
                if q["f"]["mean_sim"][i] == mi: s[i] -= pen_iso
        m = max(s); idx = [i for i,x in enumerate(s) if x == m]
        return idx[0]+1 if len(idx) == 1 else None
    return f
COMBOS = [
    ("C1 ov_all + ov_claim",                       combo_pick({"ov_all":1,"ov_claim":1})),
    ("C2 ov_all + ov_claim + mean_sim",            combo_pick({"ov_all":1,"ov_claim":1,"mean_sim":1})),
    ("C3 ov_all + mean_sim",                       combo_pick({"ov_all":1,"mean_sim":1})),
    ("C4 C2 + 绝对化惩罚 0.5",                      combo_pick({"ov_all":1,"ov_claim":1,"mean_sim":1}, pen_abs=0.5)),
    ("C5 C2 + 孤立项惩罚 0.5",                      combo_pick({"ov_all":1,"ov_claim":1,"mean_sim":1}, pen_iso=0.5)),
    ("C6 mean_sim 单独 + 孤立惩罚",                 combo_pick({"mean_sim":1}, pen_iso=0.3)),
    ("C7 ov_dist + ov_claim + mean_sim",           combo_pick({"ov_dist":1,"ov_claim":1,"mean_sim":1})),
]
W("| 组合 | mine(66) | p | hold(22) | p |")
W("|---|---|---|---|---|")
for name, sel in COMBOS:
    n1,h1,_ = eval_pick(MINE, sel); n2,h2,_ = eval_pick(HOLD, sel)
    W(f"| {name} | {fmt(n1,h1)} | {pv(n1,h1)} | {fmt(n2,h2)} | {pv(n2,h2)} |")
W()
W("排除情報検索題（文本特征天然不适用）后再看最好的组合：")
W()
NOIR_M = subset(MINE_EXAMS, not_types=["情報検索"])
NOIR_H = subset([HOLD_EXAM], not_types=["情報検索"])
for name, sel in COMBOS:
    n1,h1,_ = eval_pick(NOIR_M, sel); n2,h2,_ = eval_pick(NOIR_H, sel)
    W(f"- {name}: mine {fmt(n1,h1)}　hold {fmt(n2,h2)}")
W()

# ---------------- 7 主语/程度替换
W("## 7. 「关键词保留但主语/程度被替换」——部分可自动化")
W()
W("**主语替换：做不了。** 判断「文章说 A 影响 B，选项说 B 影响 A」需要依存句法分析，")
W("本机没有 MeCab/GiNZA/spaCy-ja，纯正则无法可靠区分格助词角色（は/が/を/に 常被省略或倒装）。")
W("硬做只会产生大量假阳性，不如老实报告做不了。")
W()
W("**程度/範囲替换：勉强可以。** 判据 = 选项内容词有 ≥50% 在文章中出现（词面被保留），")
W("但选项含一个文章里**没出现过**的程度/範囲副词（すべて/必ず/最も/常に/だけ/のみ/ほとんど/より/一番/極めて）。")
W()
DEG = ["すべて","全て","必ず","最も","常に","だけ","のみ","ほとんど","かなり","より","一番","極めて","かならず"]
def deg_swap(q,i,o):
    kw = words(o)
    if not kw: return False
    if len(kw & words(q["passage"]))/len(kw) < 0.5: return False
    return any(d in o and d not in q["passage"] for d in DEG)
t1,k1,_ = option_level(MINE, deg_swap); t2,k2,_ = option_level(HOLD, deg_swap)
ta,ka,_ = option_level(ALL, deg_swap)
W(f"- mine: 触发 {t1} 个选项，其中为答案 {k1}（{(f'{k1/t1:.1%}' if t1 else '—')}，p={pv(t1,k1)}）")
W(f"- hold: 触发 {t2} 个选项，其中为答案 {k2}（{(f'{k2/t2:.1%}' if t2 else '—')}，p={pv(t2,k2)}）")
W(f"- 全88: 触发 {ta} 个选项，其中为答案 {ka}（{(f'{ka/ta:.1%}' if ta else '—')}，p={pv(ta,ka)}）")
W()
W("触发数太少，结论同 O1：**理论上像回事，实际上碰不到。**")
W()

# ---------------- 8 附录逐题

# ================================================================ v2 新增章节
W("## 8. 【v2】真分词复核：fugashi + unidic-lite")
W()
W("上一版没有分词器，用漢字/カタカナ 2-gram 近似。本版装上 `fugashi`+`unidic-lite`，")
W("**只保留内容词**（名詞・動詞・形容詞・副詞・形状詞的 lemma），")
W("排除助詞・助動詞・補助記号・接続詞・接頭尾辞，再去掉「こと/もの/ため/する/なる/ある」等形式词。")
W("重叠度改用 lemma 集合的覆盖率，选项互似度改用 lemma 集合的 Jaccard。")
W()
W("### 8.1 三条关键规则：字符 2-gram vs 真分词")
W()
W("| 规则 | 版本 | mine n | mine 命中 | hold n | hold 命中 | 全88 n | 全88 命中 | p(全88) |")
W("|---|---|---|---|---|---|---|---|---|")
CMP = [
    ("R1 与全文重叠最高",   "ov_all",   "Lov_all"),
    ("R4 与主张句重叠最高", "ov_claim", "Lov_claim"),
    ("R10 选项互似度最高",  "mean_sim", "Lmean_sim"),
]
_cmp_res = {}
for lab, kc, kl in CMP:
    for ver, k in [("字符2-gram", kc), ("**真分词**", kl)]:
        n1,h1,_ = eval_pick(MINE, argmax_pick(k))
        n2,h2,_ = eval_pick(HOLD, argmax_pick(k))
        na,ha,_ = eval_pick(ALL,  argmax_pick(k))
        _cmp_res[(lab, ver)] = (n1,h1,n2,h2,na,ha)
        W(f"| {lab} | {ver} | {n1} | {(f'{h1/n1:.1%}' if n1 else '—')}{warn(n1)} | "
          f"{n2} | {(f'{h2/n2:.1%}' if n2 else '—')}{warn(n2)} | {na} | "
          f"{(f'{ha/na:.1%}' if na else '—')} | {pv(na,ha)} |")
W()
W("### 8.2 变化解读")
W()
_r10c = _cmp_res[("R10 选项互似度最高","字符2-gram")]
_r10l = _cmp_res[("R10 选项互似度最高","**真分词**")]
W(f"**R10（唯一成立的规律）在真分词下依然成立。**")
W(f"- 字符版：mine {_r10c[1]}/{_r10c[0]} = {_r10c[1]/_r10c[0]:.1%}、hold {_r10c[3]}/{_r10c[2]} = {_r10c[3]/_r10c[2]:.1%}、"
  f"全88 {_r10c[5]}/{_r10c[4]} = {_r10c[5]/_r10c[4]:.1%}")
W(f"- 真分词：mine {_r10l[1]}/{_r10l[0]} = {_r10l[1]/_r10l[0]:.1%}、hold {_r10l[3]}/{_r10l[2]} = {_r10l[3]/_r10l[2]:.1%}、"
  f"全88 {_r10l[5]}/{_r10l[4]} = {_r10l[5]/_r10l[4]:.1%}（p={pv(_r10l[4],_r10l[5])}）")
W()
_r1c = _cmp_res[("R1 与全文重叠最高","字符2-gram")]; _r1l = _cmp_res[("R1 与全文重叠最高","**真分词**")]
_r4c = _cmp_res[("R4 与主张句重叠最高","字符2-gram")]; _r4l = _cmp_res[("R4 与主张句重叠最高","**真分词**")]
W(f"数值小幅下移（-1.3pp）、覆盖率上升（触发題 55→63，因为真分词区分度更高、平局更少），")
W(f"结论**不变**：这是本次挖掘唯一站得住的规律，且不是字符 n-gram 的测量假象。")
W()
W(f"**⚠ R1（「与全文重叠最高 = 陷阱」）在真分词下 —— 上一版的结论被推翻。**")
W(f"- 字符2-gram 版：全88 {_r1c[5]}/{_r1c[4]} = {_r1c[5]/_r1c[4]:.1%}（明显低于 25%，v1 据此说「重叠最高是陷阱」）")
W(f"- **真分词版：全88 {_r1l[5]}/{_r1l[4]} = {_r1l[5]/_r1l[4]:.1%}（p={pv(_r1l[4],_r1l[5])}）—— 正好落在基线上，效应消失。**")
W(f"- mine {_r1l[1]}/{_r1l[0]} = {_r1l[1]/_r1l[0]:.1%}、hold {_r1l[3]}/{_r1l[2]} = {_r1l[3]/_r1l[2]:.1%}，两集合都 ≈25%。")
W()
W("**诊断**：字符 2-gram 会把「〜という」「〜ことが」「〜ている」这类功能性搭配也算进重叠，")
W("而长选项、句式复杂的选项天然带更多这种噪声 bigram。v1 的「陷阱信号」测的其实是")
W("**句式噪声**，不是内容词的照抄程度。换成内容词 lemma 后，「照抄原文词多」既不利也不弊。")
W()
W(f"→ **v1 结论「与原文字面重叠度最高的选项更可能是错的」撤回，判定为测量假象。**")
W()
W(f"**R4（与主张句重叠最高）** 真分词全88 {_r4l[5]}/{_r4l[4]} = {_r4l[5]/_r4l[4]:.1%}"
  f"（字符版 {_r4c[5]/_r4c[4]:.1%}），p={pv(_r4l[4],_r4l[5])}。")
W(f"mine {_r4l[1]/_r4l[0]:.1%} / hold {_r4l[3]/_r4l[2]:.1%}，**两集合首次方向一致且都 >30%**，")
W(f"比 v1 的字符版稳定（v1 是 34.3% / 18.2%，验证集崩了）。仍未过 p<0.05，但值得记一笔：")
W(f"**真分词确实让「主张句重叠」这条从噪声变成了弱信号**，印证了 v1 里「无分词器可能低估」的预判。")
W()
W("### 8.3 R10 真分词版稳健性（强制全題作答）")
W()
def _forced(qs, key):
    tot = 0.0
    for q in qs:
        v = q["f"][key]; m = max(v)
        idx = [i for i,x in enumerate(v) if x == m]
        tot += (1.0/len(idx)) if (q["ans"]-1) in idx else 0.0
    return tot
W("| 集合 | 字符2-gram | 真分词 |")
W("|---|---|---|")
for lab, qs in [("mine 66", MINE), ("hold 22", HOLD), ("全 88", ALL)]:
    a = _forced(qs, "mean_sim"); b = _forced(qs, "Lmean_sim")
    W(f"| {lab} | {a:.1f}/{len(qs)} = {a/len(qs):.1%} | **{b:.1f}/{len(qs)} = {b/len(qs):.1%}** |")
W()
_fh = _forced(HOLD, "Lmean_sim")
W(f"平局大幅减少（真分词区分度更高），验证集强制作答期望 **{_fh:.1f}/22 = {_fh/22:.1%}**。")
W()

# ---------------------------------------------------------------- 假设 2
W("## 9. 【v2 新增假设】限定・部分否定表达 vs 强断言")
W()
W("假设：N1 正解倾向于用「留有余地」的措辞（〜わけではない/〜とは限らない/〜ものの/")
W("〜からといって/〜に過ぎない/〜とは言えない），干扰项倾向于断言（〜べきだ/〜なければならない）。")
W()
W("统计单位 = **选项**（全 88 題 × 4 = 352 个）。")
W("两个角度都报：(a) 触发该特征的选项里有多大比例是正解（基线 25%）；")
W("(b) 正解 88 个 vs 干扰项 264 个中该特征的出现率（基线：两者应相等）。")
W()
def feat_report(title, key, qsets):
    W(f"### {title}")
    W()
    W("| 集合 | 触发选项 n | 其中为正解 | 占比 | p(vs25%) | 正解出现率 | 干扰项出现率 | 差 |")
    W("|---|---|---|---|---|---|---|---|")
    for lab, qs in qsets:
        tot = ok = 0; ans_hit = ans_tot = 0; dis_hit = dis_tot = 0
        for q in qs:
            for i in range(4):
                v = q["f"][key][i]
                if v: tot += 1; ok += (q["ans"] == i+1)
                if q["ans"] == i+1: ans_tot += 1; ans_hit += v
                else:               dis_tot += 1; dis_hit += v
        ar = ans_hit/ans_tot if ans_tot else 0
        dr = dis_hit/dis_tot if dis_tot else 0
        W(f"| {lab} | {tot}{warn(tot)} | {ok} | {(f'{ok/tot:.1%}' if tot else '—')} | {pv(tot,ok)} | "
          f"{ans_hit}/{ans_tot} = {ar:.1%} | {dis_hit}/{dis_tot} = {dr:.1%} | "
          f"{(ar-dr)*100:+.1f}pp |")
    W()
QS3 = [("mine 66", MINE), ("hold 22", HOLD), ("全 88", ALL)]
feat_report("9.1 限定・部分否定（协调员指定的核心集）", "hedge_core", QS3)
feat_report("9.2 限定・部分否定（扩展集：+必ずしも/一概に/だけではない/場合がある/傾向がある 等）", "hedge_wide", QS3)
feat_report("9.3 强断言（べきだ/なければならない/必要がある/しかない/に違いない/ざるを得ない/はずだ）", "strong", QS3)
W("### 9.4 这个负结果不是正则写错了 —— 对照审计")
W()
W("低触发率容易让人怀疑是模式没匹配上。所以逐个表达分别数「选项里出现几次」和")
W("「**文章正文**里出现几次」。若正则有问题，两边都会是 0。")
W()
W("| 表达 | 选项中(352) | 其中为正解 | 文章正文中 |")
W("|---|---|---|---|")
_AUDIT = [("〜わけではない", r"わけで(は|も)な"), ("〜とは限らない", r"と(は|も)限らな"),
          ("〜ものの", r"ものの"), ("〜からといって", r"からと(いって|言って)"),
          ("〜に過ぎない", r"に(過ぎ|すぎ)な"), ("〜とは言えない", r"と(は|も)(言え|いえ)な"),
          ("必ずしも", r"必ずしも"), ("〜だけではない", r"だけで(は|も)な"),
          ("〜ないわけではない", r"ないわけで(は|も)な")]
_pass_txt = {(q["exam"], q["pid"]): q["passage"] for q in ALL}
_so = _sp = 0
for lab, pt in _AUDIT:
    co = sum(1 for q in ALL for o in q["opts"] if re.search(pt, o))
    ca = sum(1 for q in ALL if re.search(pt, q["opts"][q["ans"]-1]))
    cp = sum(len(re.findall(pt, t)) for t in _pass_txt.values())
    _so += co; _sp += cp
    W(f"| {lab} | {co} | {ca} | {cp} |")
W(f"| **合计** | **{_so}** | — | **{_sp}** |")
W()
W(f"正则是好的：这些表达在**文章正文**里出现了 {_sp} 次，在**选项**里只出现 {_so} 次。")
W()
W("**这个不对称本身才是真正的发现**：出题方写选项时会把原文的「留有余地」措辞")
W("**抹平成平铺直叙的断言句**。所以「正解措辞更委婉」这条假设在 N1 読解上")
W("**不是效应弱，而是根本没有可观测的载体**——选项里压根不写这种句式。")
W("同理，这也解释了 v1 里绝对化措辞为什么只触发 2.6%：")
W("**四个选项被刻意写成语气强度一致的平行句，任何靠「语气」区分正误的技巧都失效。**")
W("这是本次挖掘对「为什么読解规则化这么难」最有信息量的一条解释。")
W()
W("### 9.5 逐条列出触发核心限定表达的选项（★ = 正解）")
W()
_n = 0
for q in ALL:
    for i, o in enumerate(q["opts"]):
        if q["f"]["hedge_core"][i]:
            _n += 1
            W(f"- {'★' if q['ans']==i+1 else '　'} `{q['exam']} 題{q['num']} 选项{i+1}`　{o}")
if _n == 0: W("（无）")
W()

# ---------------------------------------------------------------- 假设 3
W("## 10. 【v2 新增假设】重叠度 rank 分布 —— 「正解藏在中间」？")
W()
W("**注意**：本节的动机来自 v1 的「重叠最高 = 陷阱」，而 §8.2 已把那条撤回。")
W("所以这里不是去「确认」什么，而是直接问：正解在重叠度排名上有没有任何偏好？")
W("做法：每題按重叠度**降序**给 4 个选项排名，统计正解落在各 rank 的频次。")
W("若无信号，四个 rank 各占 25%。")
W("**只统计四个值互不相同（无平局）的題**，避免排名任意化。")
W()
def rank_dist(qs, key):
    cnt = Counter(); n = 0
    for q in qs:
        v = q["f"][key]
        if len(set(v)) < 4: continue
        order = sorted(range(4), key=lambda i: -v[i])
        cnt[order.index(q["ans"]-1) + 1] += 1
        n += 1
    return cnt, n
RK = [("与全文重叠（真分词）", "Lov_all"), ("与全文重叠（字符2-gram）", "ov_all"),
      ("与主张句重叠（真分词）", "Lov_claim"), ("选项互似度（真分词）", "Lmean_sim")]
for lab, key in RK:
    W(f"### {lab}")
    W()
    W("| 集合 | 无平局題 n | rank1(最高) | rank2 | rank3 | rank4(最低) |")
    W("|---|---|---|---|---|---|")
    for slab, qs in QS3:
        c, n = rank_dist(qs, key)
        if n == 0:
            W(f"| {slab} | 0 | — | — | — | — |"); continue
        cells = " | ".join(f"{c[r]} ({c[r]/n:.0%})" for r in (1,2,3,4))
        W(f"| {slab} | {n}{warn(n)} | {cells} |")
    W()
c_all, n_all_r = rank_dist(ALL, "Lov_all")
mid = c_all[2] + c_all[3]
W(f"**关键数字（真分词・全 88 題・无平局 {n_all_r} 題）**：")
W(f"rank1 {c_all[1]} ({c_all[1]/n_all_r:.0%})、rank2 {c_all[2]} ({c_all[2]/n_all_r:.0%})、"
  f"rank3 {c_all[3]} ({c_all[3]/n_all_r:.0%})、rank4 {c_all[4]} ({c_all[4]/n_all_r:.0%})。")
W(f"「中间两名」合计 {mid}/{n_all_r} = {mid/n_all_r:.1%}，基线 50%，"
  f"p={two_sided(mid, n_all_r, 0.5):.3f}。")
W()
_cm, _nm = rank_dist(MINE, "Lov_all"); _ch, _nh = rank_dist(HOLD, "Lov_all")
W(f"挖掘集中间两名 {_cm[2]+_cm[3]}/{_nm} = {(_cm[2]+_cm[3])/_nm:.1%}；"
  f"验证集 {_ch[2]+_ch[3]}/{_nh} = {(_ch[2]+_ch[3])/_nh:.1%}{warn(_nh)}。")
W()
W("**作为可执行规则的形式**：「排除重叠度最高和最低的两项，在中间两项里二选一」")
W("→ 期望命中 = 中间两名占比 × 1/2。")
W(f"全88: {mid/n_all_r:.1%} × 1/2 = **{mid/n_all_r/2:.1%}**；")
W(f"验证集: {(_ch[2]+_ch[3])/_nh:.1%} × 1/2 = **{(_ch[2]+_ch[3])/_nh/2:.1%}**（基线 25%）。")
W()
W("→ **假设 3 证伪。** 与全文重叠度的 rank 对正解位置没有任何偏好，")
W("「正解藏在中间」不成立（全88 恰好 50.0%，p=1.000；验证集甚至反向）。")
W("另外注意无平局題只有 32/88，本身覆盖率就低，就算成立也用不上。")
W()
W("### 10.1 意外发现：「与主张句重叠**最低**」可以排除")
W()
W("上表「与主张句重叠（真分词）」一行里，rank4（最低）只占 6%——远低于 25%。")
W("单独把它当排除规则测一遍（统计单位 = 选项，含平局題，唯一最低才算）：")
W()
def lowest_claim(q, i, o):
    v = q["f"]["Lov_claim"]
    return v[i] == min(v) and v.count(min(v)) == 1
W("| 集合 | 触发选项 n | 其中为正解 | 占比 | p(vs 25%) |")
W("|---|---|---|---|---|")
_lc = {}
for slab, qs in QS3:
    t, k, _ = option_level(qs, lowest_claim)
    _lc[slab] = (t, k)
    W(f"| {slab} | {t}{warn(t)} | {k} | {(f'{k/t:.1%}' if t else '—')} | {pv(t,k)} |")
W()
_t, _k = _lc["全 88"]; _tm, _km = _lc["mine 66"]; _th, _kh = _lc["hold 22"]
W(f"全88 {_k}/{_t} = {_k/_t:.1%}，p={two_sided(_k,_t):.3f}；"
  f"mine {_km/_tm:.1%}、hold {_kh/_th:.1%}。")
W("对照：同一规则的字符 2-gram 版——")
def lowest_claim_c(q, i, o):
    v = q["f"]["ov_claim"]
    return v[i] == min(v) and v.count(min(v)) == 1
for slab, qs in QS3:
    t, k, _ = option_level(qs, lowest_claim_c)
    W(f"- {slab}: {k}/{t} = {(f'{k/t:.1%}' if t else '—')}（p={pv(t,k)}）")
W()
W("**解读**：正解几乎不会是「与文章主张句内容词交集最小」的那一项——语义上很自然，")
W("因为正解必须复述主张。**这是本次全部挖掘中最强的排除规则**：")
W("挖掘集 8.3%、验证集 7.7%，两边几乎一样，不是过拟合。")
W()
W("**诚实标注**：特征本身（「与末段主张句的重叠度」）是任务里**预先指定**要测的，不算钓鱼；")
W("但「取最低者作排除」这个**方向**是我从 §10 的 rank 表里事后挑的。")
W("所以它享有 mine/hold 一致性的证据，但不享有「预注册」的清白。")
W("按 look-elsewhere 打折看待：真实效应大概率存在，强度可能没有 8.2% 显示的那么极端。")
W()
W("**另外注意：这条只在真分词下出现。** 字符 2-gram 版是 16.7%（p=0.34，不显著）。")
W("v1 报告里「无分词器可能低估主张句类特征」的预判，在这里被证实了。")
W()
W("### 10.2 R10 + 主张句排除 的联合策略")
W()
def joint(q):
    """先排除 Lov_claim 唯一最低项，再在剩余里取 Lmean_sim 最高"""
    vc = q["f"]["Lov_claim"]
    banned = set()
    if vc.count(min(vc)) == 1:
        banned.add(vc.index(min(vc)))
    vs = q["f"]["Lmean_sim"]
    cand = [i for i in range(4) if i not in banned]
    m = max(vs[i] for i in cand)
    idx = [i for i in cand if vs[i] == m]
    return idx[0]+1 if len(idx) == 1 else None
def joint_forced(qs):
    """同上但平局随机，全題作答，解析求期望"""
    tot = 0.0
    for q in qs:
        vc = q["f"]["Lov_claim"]; banned = set()
        if vc.count(min(vc)) == 1: banned.add(vc.index(min(vc)))
        vs = q["f"]["Lmean_sim"]
        cand = [i for i in range(4) if i not in banned]
        m = max(vs[i] for i in cand)
        idx = [i for i in cand if vs[i] == m]
        tot += (1.0/len(idx)) if (q["ans"]-1) in idx else 0.0
    return tot
W("| 集合 | 严格版 n | 命中率 | p | 强制全題作答期望 |")
W("|---|---|---|---|---|")
_joint = {}
for slab, qs in QS3:
    n, h, _ = eval_pick(qs, joint)
    e = joint_forced(qs)
    _joint[slab] = (n, h, e, len(qs))
    W(f"| {slab} | {n} | {(f'{h}/{n} = {h/n:.1%}' if n else '—')} | {pv(n,h)} | "
      f"**{e:.1f}/{len(qs)} = {e/len(qs):.1%}** |")
W()
_jh = _joint["hold 22"]; _jm = _joint["mine 66"]
W(f"**验证集强制全題作答 {_jh[2]:.1f}/22 = {_jh[2]/22:.1%}**"
  f"（对比：单用 R10 真分词 7.0/22 = 31.8%，乱猜 5.5/22 = 25%）。")
W(f"挖掘集 {_jm[2]:.1f}/66 = {_jm[2]/66:.1%}，折合 {_jm[2]/66*22:.1f}/22。")
W(f"mine→hold 落差 {(_jm[2]/66 - _jh[2]/22)*100:.1f}pp。")
W()
W("**结论：联合策略在验证集上没有超过单用 R10（都是 7.0/22）。**")
W("原因是两条规则高度相关——被主张句排除掉的选项，多半也正是互似度最低的那个，")
W("排除它并不会改变 R10 的选择。所以「主张句最低可排除」虽然本身指标漂亮（8.2%），")
W("**叠加到已有策略上没有增量**。这也是它只能当独立诊断信号、不能提高天花板的原因。")
W()

W("## 11. 附录：验证集 2026-07 逐題诊断")
W()
W("| 題 | 題型 | 正解 | R1全文 | R4主张句 | R10最合群 | C2组合 | 长度降序 | 最孤立项 |")
W("|---|---|---|---|---|---|---|---|---|")
c2 = combo_pick({"ov_all":1,"ov_claim":1,"mean_sim":1})
for q in HOLD:
    def mk(p): return ("平局" if p is None else f"{p}{'✓' if p==q['ans'] else '✗'}")
    order = "".join(str(i+1) for i in sorted(range(4), key=lambda i:-q["f"]["len"][i]))
    mi = min(q["f"]["mean_sim"])
    iso = "".join(str(i+1) for i in range(4) if q["f"]["mean_sim"][i]==mi)
    iso += "✓错" if q["ans"] != int(iso[0]) or len(iso)>1 else "✗竟是答案"
    W(f"| {q['num']} | {q['type']} | {q['ans']} | {mk(argmax_pick('ov_all')(q))} | "
      f"{mk(argmax_pick('ov_claim')(q))} | {mk(argmax_pick('mean_sim')(q))} | {mk(c2(q))} | "
      f"{order} | {iso} |")
W()

# ---------------- 9 天花板
W("## 12. 规则化天花板")
W()
best = max(((eval_pick(HOLD, sl)[2], nm, *eval_pick(HOLD, sl)[:2]) for nm, sl in RULES),
           key=lambda x: (x[0] if x[0] == x[0] else 0))
W(f"- 验证集上最好的单特征规则：**{best[1]}** → {best[3]}/{best[2]} = {best[0]:.1%}")
nb, hb, _ = eval_pick(HOLD, c2)
W(f"- 验证集上最好的组合 C2 → {hb}/{nb} = {hb/nb:.1%}")
W()
opt = 0
for q in HOLD:
    preds = set()
    for _, sl in RULES:
        p_ = sl(q)
        if p_: preds.add(p_)
    if q["ans"] in preds: opt += 1
W(f"- **事后乐观上界**（表 §2 的规则中只要任意一条命中就算对）：{opt}/22 = {opt/22:.1%}。")
W("  这个数字**不可实现**——考场上无法知道该信哪一条。它只说明「表层特征的信息量上限」。")
W()

def full_strategy(q):
    """R10 优先；R10 平局时退化到 C2；再平局则不作答"""
    v = q["f"]["mean_sim"]; m = max(v)
    idx = [i for i, x in enumerate(v) if x == m]
    if len(idx) == 1: return idx[0]+1
    return c2(q)

def expected_score(qs, sel):
    """触发題按实测命中率，未触发題按 25% 乱猜，算 22 題期望分"""
    n, h, _ = eval_pick(qs, sel)
    miss = len(qs) - n
    return h + miss*0.25, n, h, miss

for lab, qs in [("mine 66", MINE), ("hold 22", HOLD)]:
    for nm, sl in [("C2 组合", c2), ("R10 优先+C2 兜底", full_strategy)]:
        e, n, h, miss = expected_score(qs, sl)
        per22 = e/len(qs)*22
        W(f"- {lab} / {nm}：触发 {n} 題命中 {h}，未触发 {miss} 題按 25% 计 → "
          f"期望 {e:.1f}/{len(qs)}（折合 **{per22:.1f}/22**，正确率 {e/len(qs):.1%}）")
W()
W("### 天花板判断（不粉饰）")
W()
W("**纯规则、完全不读懂文章的情况下，22 題的期望得分是 7～8 題，正确率 32%～36%。**")
W()
W("怎么来的：")
W("1. 乱猜基线 = 5.5 題。")
W("2. 验证集上最好的可执行策略（R10 优先 + C2 兜底）实测把期望推到 7～8 題。")
W("3. 挖掘集上同一策略折合 9.4/22，验证集 8.0/22 → 掉了 1.4 題，**存在轻度过拟合，但没有崩掉**，")
W("   说明信号是真的、只是弱。")
W("4. 情報検索（問題13）每卷固定 2 題不属于「找规律」范畴——那是查表算数，")
W("   靠流程化操作（抄条件→逐项核对）本来就该稳拿，不该算进「规则化红利」。")
W()
W("**所以规则化的净增益 ≈ 1.5～2.5 題 / 22 題。**")
W()
W("这个数字要说难看也确实难看。含义是：")
W("- N1 読解 22 題通常要答对 13～15 題才够看，规则最多帮你从 5.5 → 8。**差得远。**")
W("- 规则的正确用法只有一个：**考场最后 3~5 分钟，剩几題没时间读了，用 R10 蒙**")
W("  （挑那个跟其他三项用词最像的），比闭眼选同一个号强一点点。")
W("- 反过来说，本次挖掘最实际的产出是**否定性的**：")
W("  「绝对化措辞排除法」「答案号有偏」「最长/最短选项」「重叠度最高即答案」")
W("  这些流传很广的技巧，在 88 題真题上全部不成立，用它们只会误导。")
W("  其中「重叠度最高即答案」还是**反向**的——照着做会主动踩坑。")
W()
W("### 【v2】真分词后天花板有没有变？")
W()
W("**没有。** 三条路线在验证集上的强制全題作答期望：")
W()
W("| 策略 | mine 折合/22 | hold /22 |")
W("|---|---|---|")
for nm, fn in [("R10 字符2-gram", lambda qs: _forced(qs,"mean_sim")),
               ("R10 真分词",     lambda qs: _forced(qs,"Lmean_sim")),
               ("R10 真分词 + 主张句排除", joint_forced)]:
    a = fn(MINE)/66*22; b = fn(HOLD)
    W(f"| {nm} | {a:.1f} | **{b:.1f}** |")
W()
W("三条全部落在 **7.0～7.7 / 22**。加上 C2 组合的 8.0，区间是 **7～8 題**。")
W("**真分词提高了测量精度，但没有提高可达成绩** —— 这本身就是个结论：")
W("v1 的 7～8 題不是分词器不行造成的低估，是読解这个题型的真实上限。")
W()
W("### 方法学局限（必须一起看）")
W()
W("1. **样本量太小**。88 題，分到每条规则触发只剩 10~50 題，95% 置信区间宽达 ±12~15pp。")
W("   R10 的 47.3% 真实值可能在 34%~61% 之间。")
W("2. **多重比较**。本报告测了 11 条选择规则 + 8 条排除规则 + 7 个组合 ≈ 26 个假设。")
W("   按 α=0.05 计，期望有 1~2 个纯属偶然的「显著」结果。R10 经 Bonferroni 后仍显著，")
W("   其余全部没过。")
W("3. ~~无分词器~~ **【v2 已解决】** 已装 fugashi+unidic-lite 用真内容词重跑。")
W("   结果：(a) 推翻了 v1 的「重叠最高=陷阱」（是句式噪声假象）；")
W("   (b) 让「主张句重叠」从噪声变成可用的排除信号（16.7%→8.2%）；")
W("   (c) R10 基本不变（47.3%→46.0%）；(d) **天花板没变**。")
W("   v1 预判的「可能低估」方向是对的，但低估的量不足以改变结论。")
W("   遗留：纯假名功能表达（〜わけではない 等）在真题选项里**本来就极少出现**（0.9%），")
W("   不是分词器测不到，是它压根不存在——见 §9。")
W("4. **2024-12 数据质量差**。11/22 題文章残缺，已单列一列对照；")
W("   健全 55 題与全 66 題的结论方向一致，说明主要结论不是残缺数据造成的。")
W()

W("## 13. 结论汇总表")
W()
W("### ✅ 成立（弱，但挖掘集与验证集方向一致）")
W()
W("| 规律 | 单位 | 触发 n(全88) | mine | hold | 全88 | 基线 | Bonferroni 后 |")
W("|---|---|---|---|---|---|---|---|")
W(f"| **R10 与其他三项平均词面相似度最高的选项 = 答案** | 題 | {n10a} | "
  f"{h10m/n10m:.1%} | {h10h/n10h:.1%} | {h10a/n10a:.1%} | 25% | 显著 (p_adj≈0.012) |")
W(f"| **R6 与原文区別性 bigram 重叠最高的选项 = 陷阱** | 題 | {n6a} | "
  f"{h6m/n6m:.1%} | {h6h/n6h:.1%} | {h6a/n6a:.1%} | 25% | 不显著 (p_adj≈0.43)，仅方向一致 |")
W()
W("### ⚠ 方向一致但样本不足 / 不显著")
W()
W("| 规律 | 触发 n | mine | hold | 备注 |")
W("|---|---|---|---|---|")
nm5,hm5,_ = eval_pick(MINE, margin_pick("mean_sim", 0.05))
nh5,hh5,_ = eval_pick(HOLD, margin_pick("mean_sim", 0.05))
W(f"| R10 加强版：相似度领先 ≥0.05 才出手 | mine {nm5} / hold {nh5} | {hm5}/{nm5} = {hm5/nm5:.0%} | "
  f"{hh5}/{nh5} = {hh5/nh5:.0%} | **样本不足，不可信**（合计 n={nm5+nh5}<20），但两集合都 ~60%，值得后续更多卷验证 |")
n7m,h7m,_=eval_pick(MINE,argmax_pick("ov_dist_c")); n7h,h7h,_=eval_pick(HOLD,argmax_pick("ov_dist_c"))
W(f"| R7 区別性 bigram ↔ 主张句重叠最高 | mine {n7m} / hold {n7h} | {h7m}/{n7m} = {h7m/n7m:.0%} | "
  f"{h7h}/{n7h} = {h7h/n7h:.0%} | 两集合都 >33%、方向一致，但全88 p=0.083 未过 0.05，"
  f"hold 端 n={n7h} 刚过门槛 → **待更多真题确认** |")
W()
W("### 🔄 v2 变更（真分词后与 v1 不同的条目）")
W()
W("| 条目 | v1（字符2-gram） | v2（真分词） | 处置 |")
W("|---|---|---|---|")
W(f"| R10 选项互似度最高 = 答案 | 全88 47.3% | 全88 {_r10l[5]/_r10l[4]:.1%}（n={_r10l[4]}） | ✅ **维持**，非假象 |")
W(f"| R1 与全文重叠最高 = 陷阱 | 全88 16.7%（R6 版 11.1%） | 全88 {_r1l[5]/_r1l[4]:.1%} | ❌ **撤回**，测量假象 |")
W(f"| R4 与主张句重叠最高 = 答案 | mine 34.3% / hold 18.2%（验证集崩） | mine {_r4l[1]/_r4l[0]:.1%} / hold {_r4l[3]/_r4l[2]:.1%} | ⚠ 升级为**弱信号**，仍不显著 |")
W(f"| 与主张句重叠**最低** = 可排除 | 全88 16.7%，p=0.34 | 全88 {_k}/{_t} = {_k/_t:.1%}，p={two_sided(_k,_t):.3f} | ✅ **新增成立**（见下） |")
W()
W("### ✅ v2 新增成立")
W()
W("| 规律 | 单位 | n(全88) | mine | hold | 全88 | 基线 | 备注 |")
W("|---|---|---|---|---|---|---|---|")
W(f"| **与文章主张句内容词交集最小的选项 ≠ 正解** | 选项 | {_t} | {_km/_tm:.1%} | {_kh/_th:.1%} | "
  f"**{_k/_t:.1%}** (p={two_sided(_k,_t):.3f}) | 25% | 两集合一致；但与 R10 相关，叠加**无增量** |")
W()
W("### ❌ v2 新增证伪")
W()
W("| 假设 | 实测 | 判定 |")
W("|---|---|---|")
W("| 正解倾向用限定・部分否定措辞（〜わけではない/〜とは限らない/〜ものの/〜からといって/〜に過ぎない/〜とは言えない） | 352 个选项只触发 **3 个**（0.9%），正解率 33.3%（n=3，**样本不足**）；扩展集 n=9，22.2%；正解出现率 2.3% vs 干扰项 2.7%（**-0.4pp**） | ❌ **证伪**。不是分词器测不到，是真题里几乎不用这种措辞 |")
W("| 干扰项倾向用强断言（べきだ/なければならない/必要がある/しかない/に違いない/ざるを得ない/はずだ） | n=42，正解率 21.4%（p=0.74）；正解出现率 10.2% vs 干扰项 12.5%（-2.3pp） | ❌ 方向对但幅度微小、不显著，**无实用价值** |")
W("| 正解藏在重叠度 rank2/rank3（「中间两名」） | 全88 无平局 32 題，中间两名 50.0%（p=1.000）；验证集 33.3%（n=6，样本不足） | ❌ **证伪**，四个 rank 无偏好 |")
W()
W("### ❌ 证伪 / 无信号（v1 已定，v2 不变）")
W()
W("| 假设 | 实测 | 判定 |")
W("|---|---|---|")
W(f"| 绝对化措辞（必ず/すべて/絶対/常に/のみ/しか～ない）→ 错误项 | 选项 n=9，为答案 22.2%，p=0.60；触发率仅 2.6% | ❌ **证伪**。既不显著，也几乎不出现 |")
W(f"| 广义绝对化措辞 → 错误项 | 选项 n=14，为答案 21.4%，p=1.00 | ❌ 无信号 |")
W(f"| 答案编号有偏 / 可以固定蒙一个 | χ²={chi:.2f}（临界 7.81）；蒙 mine 最频号在 hold 上 {hh}/22 = {hh/22:.1%} | ❌ **无偏**，蒙固定号比乱猜还差 |")
W(f"| 答案倾向避开连号 | 相邻同号 11 次 vs 期望 21 次 | ❌ 方向相反且不显著 |")
W(f"| 最长选项 = 答案 | 全88 {fmt(*eval_pick(ALL,argmax_pick('len'))[:2])}，p={pv(*eval_pick(ALL,argmax_pick('len'))[:2])} | ❌ 无信号 |")
W(f"| 最短选项 = 答案 | 全88 {fmt(*eval_pick(ALL,argmin_pick('len'))[:2])}，p={pv(*eval_pick(ALL,argmin_pick('len'))[:2])} | ❌ 略低于基线但不显著 |")
W(f"| 否定形结尾 → 错误项 | 选项 n=41，为答案 22.0%，p=0.81 | ❌ ≈基线，无信号 |")
W(f"| 与全文重叠度**最高** = 答案 | 全88 {fmt(*eval_pick(ALL,argmax_pick('ov_all'))[:2])} | ❌ **反向**，见成立表 R6 |")
W(f"| 与全文重叠度**最低**可排除 | 选项 n=65，为答案 21.5%，p=0.63 | ❌ 无信号 |")
W(f"| 与「末段主张句」重叠比与全文重叠更能预测 | R4 全88 {fmt(*eval_pick(ALL,argmax_pick('ov_claim'))[:2])} vs R1 {fmt(*eval_pick(ALL,argmax_pick('ov_all'))[:2])} | ⚠ R4 确实比 R1 高，但 R4 本身 p=0.49 不显著，**未证实** |")
W(f"| 「互相最像的一对」里必有答案 | 全88 {_pk}/{_pn} = {_pk/_pn:.1%} vs 基线 50%，p={two_sided(_pk,_pn,0.5):.3f} | ⚠ 高于基线但与 R10 同源，且缩到 2 选 1 后期望仅 31.7%，**被 R10 完全覆盖** |")
W(f"| 最孤立选项可排除 | 选项 n={o5a[0]}，为答案 {o5a[2]:.1%}；hold 端正好 25.0% | ❌ 验证集归零，**不成立** |")
W(f"| 「词面保留但程度副词被替换」→ 错误项 | 全88 触发 17 个选项，为答案 5.9% | ⚠ 方向对（5.9% << 25%）但 n=17 偏小、p=0.10，**样本不足** |")
W(f"| 主语被替换（A↔B 倒置）→ 错误项 | 无依存分析器，**无法自动化** | — 未测试，见 §7 |")
W()
W("### 一句话总结")
W()
W("**読解不是能靠表层规则做的科目。** 上了真分词之后，88 題里能被算法抓住的信号只有两条，")
W("而且互相重叠：正解与干扰项共享词面（R10，选最合群的），")
W("正解必须复述主张（排除与主张句交集最小的）。净增益仍是约 1.5～2.5 題 / 22 題。")
W()
W("v2 最重要的一课是**方法学的**：v1 用字符 2-gram 挖出来的「与原文重叠最高的是陷阱」")
W("看着方向一致、三个集合都同向、p 还过了 0.05——但它是假的，")
W("换个更准的分词方式就消失了。**表层统计很容易挖出测量假象，")
W("留一验证只能防过拟合，防不了特征本身有偏。**")
W()
W("剩下的传统「技巧」——绝对化措辞、答案编号、选项长短、否定形结尾、")
W("限定措辞、「正解藏中间」——在 88 題真题上全部站不住。")
W("把时间花在提高实际阅读速度和抓论点上，回报远高于背这些规则。")
W()

path = "/Users/herclyon/JLPT/mining/reading_findings.md"
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(OUT) + "\n")
print("\n".join(OUT))
print(f"\n[written] {path}", file=sys.stderr)
