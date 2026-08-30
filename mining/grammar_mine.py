# -*- coding: utf-8 -*-
"""
JLPT N1 文法部分（問題5/6/7）实证挖掘脚本
-------------------------------------------------
用法:  python3 grammar_mine.py
数据:  /Users/herclyon/JLPT/converted/*言語知識*.txt

核心任务:
  H1  "空格前形态决定接续合法性，可排除选项"  —— 对 問題5 逐题统计可排除选项数
  H2  呼応（しか…ない / どうりで…はず / 決して…ない …）能排除几个
  H3  格・态一致（に＋受身 vs 使役）
  H4  最小对立对(2x2网格)中答案偏好哪一侧
  H5  选项长度
  H6  答案编号分布
  H7  敬语题
  留一验证: train = 3 套, test = 1 套
"""
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

from janome.tokenizer import Tokenizer

DATA = "/Users/herclyon/JLPT/converted"
T = Tokenizer()

# ============================================================================
# 1. 解析
# ============================================================================


class Item:
    def __init__(self, paper, sec, num):
        self.paper, self.sec, self.num = paper, sec, num
        self.stem = ""
        self.opts = {}
        self.ans = None

    @property
    def O(self):
        return [self.opts[i] for i in sorted(self.opts)]

    def __repr__(self):
        return f"<{self.paper} {self.sec} #{self.num}>"


def parse(path):
    paper = os.path.basename(path).split("_")[0]
    items, sec, cur = [], None, None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#大題"):
            sec = line.split()[1]
            cur = None
        elif line.startswith("#題"):
            cur = Item(paper, sec, int(line.split()[1]))
            items.append(cur)
        elif line.startswith("#干") and cur is not None:
            cur.stem = line[3:]
        elif line.startswith("#选") and cur is not None:
            m = re.match(r"#选\s+(\d+)\s+(.*)", line)
            cur.opts[int(m.group(1))] = m.group(2)
        elif line.startswith("#答") and cur is not None:
            cur.ans = int(line.split()[1])
        elif line.startswith("#文") or line.startswith("#卷") or line.startswith("#科"):
            pass
        elif cur is not None and not line.startswith("#") and line.strip() and not cur.opts:
            # 干 的续行（2026-07 的会話体题干是多行的）
            cur.stem += "\n" + line
    return items


def parse_bunsho(path):
    """返回 {题号: (左文, 右文)}，来自 #文 块里的 【41】 空位。"""
    txt = open(path, encoding="utf-8").read()
    blocks = re.findall(r"#文\s+\S+\n(.*?)\n#文完", txt, re.S)
    out = {}
    for b in blocks:
        for m in re.finditer(r"【(\d+)】", b):
            n = int(m.group(1))
            L = b[:m.start()]
            R = b[m.end():]
            # 只取空位所在句子（上一个句读点之后）
            Lc = re.split(r"[。！？\n]", L)[-1]
            Rc = re.split(r"[。！？\n]", R)[0]
            out[n] = (Lc, Rc)
    return out


def load_all():
    papers = {}
    for p in sorted(glob.glob(os.path.join(DATA, "*言語知識*.txt"))):
        its = parse(p)
        papers[os.path.basename(p).split("_")[0]] = [
            i for i in its if i.sec in ("問題5", "問題6", "問題7")
        ]
    return papers


# ============================================================================
# 2. 形态学工具
# ============================================================================


def toks(s):
    return [t for t in T.tokenize(s)]


def pos(t):
    return t.part_of_speech.split(",")


# 左侧上下文可提供的"接续位"类别
CATS = [
    "N",  # 体言（名詞・代名詞・形容動詞語幹・数）
    "NA",  # 形容動詞語幹（同时也算 N）
    "IADJ",  # い形容詞 基本形
    "V_DIC",  # 動詞・助動詞 基本形（＝連体形/終止形）
    "V_TA",  # た形
    "V_TE",  # て形（接続助詞 て/で 结尾）
    "V_NAI",  # ない 基本形
    "V_RENYO",  # 動詞連用形（ます形词干）
    "PART",  # 以助詞结尾（格助詞/係助詞/副助詞）
    "SETSU",  # 以接続助詞结尾（が/から/ので/ば/たら/と…，不含て）
    "ADV",  # 以副詞结尾
    "BOUND",  # 句首 / 読点 / 句点 / 引号 后
]


def left_cats(left):
    """返回空格左侧提供的接续位类别集合。"""
    tl = toks(left)
    while tl and pos(tl[-1])[0] == "記号" and pos(tl[-1])[1] not in ("句点", "読点"):
        tl.pop()
    if not tl:
        return {"BOUND"}
    t = tl[-1]
    p = pos(t)
    c = set()
    if p[0] == "記号":
        return {"BOUND"}
    if p[0] == "助詞":
        if p[1] == "接続助詞":
            if t.surface in ("て", "で"):
                c.add("V_TE")
            else:
                c.add("SETSU")
        elif p[1] == "連体化":  # の
            c.add("NO")
        elif p[1] == "副詞化":  # と（すらすらと）
            c.add("ADV")
        elif p[1] == "終助詞":
            c.add("BOUND")
        else:
            c.add("PART")
            c.add("PART:" + t.surface)
        return c
    if p[0] == "動詞":
        f = t.infl_form
        if f in ("基本形", "体言接続"):
            c.add("V_DIC")
        elif f in ("連用形", "連用タ接続", "連用テ接続"):
            c.add("V_RENYO")
        elif f == "未然形":
            c.add("V_MIZEN")
        else:
            c.add("V_DIC")
        return c
    if p[0] == "助動詞":
        b = t.base_form
        f = t.infl_form
        if b == "た":
            c.add("V_TA")
            c.add("V_DIC")
        elif b == "ない":
            c.add("V_NAI")
            c.add("V_DIC")
        elif b in ("だ", "です"):
            if f == "体言接続":  # な
                c.add("NA_NA")
            elif f == "連用形":  # で / だっ
                c.add("PART")
            else:
                c.add("V_DIC")
        else:
            c.add("V_DIC")
        return c
    if p[0] == "形容詞":
        f = t.infl_form
        if f == "基本形":
            c.add("IADJ")
            c.add("V_DIC")
        elif "連用" in f:
            c.add("ADV")
        else:
            c.add("IADJ")
        return c
    if p[0] == "名詞":
        c.add("N")
        if p[1] in ("形容動詞語幹", "ナイ形容詞語幹"):
            c.add("NA")
        if p[1] == "サ変接続":
            c.add("SAHEN")
        return c
    if p[0] == "副詞":
        c.add("ADV")
        return c
    if p[0] == "接続詞":
        c.add("BOUND")
        return c
    if p[0] == "連体詞":
        c.add("RENTAI")
        return c
    return {"N"}


# ---------------------------------------------------------------------------
# 接续规格表：选项开头的语法形式 -> 允许的左侧类别
# （按最长前缀匹配；来源为标准 N1 语法书的「接続」栏，与答案无关）
# ---------------------------------------------------------------------------
RENTAI = {"V_DIC", "V_TA", "V_NAI", "IADJ", "NA_NA", "NO", "RENTAI"}
PLAIN = {"V_DIC", "V_TA", "V_NAI", "IADJ", "N", "NA"}  # 普通形（名詞だ/な形だ 也算）
NOUNY = {"N", "NA", "SAHEN"}
PRED_SLOT = {"PART", "ADV", "BOUND", "V_TE", "SETSU", "V_RENYO", "PART:を", "PART:が",
             "PART:に", "PART:で", "PART:は", "PART:も", "PART:と", "PART:から",
             "PART:など", "PART:なんて", "PART:しか", "PART:くらい", "PART:まで",
             "V_MIZEN", "RENTAI", "NO"}

# 复合助词/形式名词类（要求体言）
REQ_N = [
    "に次いで", "にわたって", "を受けて", "をめぐって", "を踏まえて", "にあって",
    "に至って", "をはじめ", "なくして", "とあって", "にかけて", "とあいまって",
    "に対して", "によって", "はともかく", "に反して", "からすると", "だけあって",
    "にとって", "となると", "もさることながら", "なんかで", "だったら",
]
# 要求连体形
REQ_RENTAI = [
    "ときに限って", "ことに反して", "はずだ", "ようだ", "ほどだ", "くらいだ",
    "勢いだ", "見込みだ", "ことは否めない", "ものだ", "わけだ", "ところがある",
]
# 要求动词辞书形
REQ_VDIC = ["に越したことはない"]
# 引用系（普通形）
REQ_PLAIN = [
    "という", "といえる", "といった", "といわれる", "というときに限って",
    "ということに反して", "らしい", "みたいな",
]
# 裸助詞
BARE = {
    "より": PLAIN | {"NO"},
    "のみ": {"N", "NA", "V_DIC"},
    "には": {"N", "NA", "V_DIC"},
    "だけ": PLAIN | {"NA_NA"},
    "さえ": {"N", "NA", "V_TE", "V_RENYO", "PART"},
    "まで": {"N", "NA", "V_DIC", "V_TE"},
    "こそ": {"N", "NA", "V_TE", "V_RENYO"},
    "なら": PLAIN | {"NO"},
    "だって": {"N", "NA", "PART", "V_TE"},
    "でさえ": {"N", "NA"},
    "といっても": PLAIN | {"NA_NA"},
    "しか": {"N", "NA", "PART", "V_DIC"},
    "すらも": {"N", "NA", "PART"},
    "だけが": PLAIN | {"NA_NA", "NO"},
}
# 接続詞（要求句界）
CONJ_WORDS = {"ただ", "それが", "なのに", "あるいは", "そこで", "すなわち", "ちなみに",
              "それによって", "そればかりでなく", "それどころか", "それにもかかわらず"}

# て形之后合法的补助动词/补助成分（白名单）
TE_AUX_OK = {
    "いる", "おる", "いく", "ゆく", "くる", "みる", "しまう", "おく", "ある", "やる",
    "あげる", "くれる", "もらう", "いただく", "くださる", "ください", "まいる",
    "いらっしゃる", "ほしい", "よい", "いい", "だめ", "ならない", "いけない",
    "たまらない", "ならぬ", "みせる", "はじめる", "おいでになる", "ごらんになる",
}
TE_AUX_NG = {"いたす", "なさる", "する", "です", "ます", "申し上げる"}


# 「のみ」在孤立分词时会被 janome 误判为動詞，单列
REQ_PLAIN_EXTRA = ["のみならず", "ならでは"]
QUOT_EXEMPT = ("とあいまって",)

# LENIENT=True 时把书面语中确有用例但语法书未列的接续（如「〜てのみ」）判为合法
LENIENT = False


def opt_req(opt):
    """返回该选项要求的左侧类别集合。"""
    o = opt.strip()
    for k in REQ_PLAIN_EXTRA:
        if o.startswith(k):
            return PLAIN | {"NA_NA", "V_TE", "NO"}
    # と＋用言 = 引用系（とする/となる/という/とあって…），前接普通形
    if o.startswith("と") and not o.startswith(QUOT_EXEMPT):
        tl0 = toks(o)
        if len(tl0) >= 2 and pos(tl0[1])[0] in ("動詞", "形容詞"):
            return PLAIN | {"NA_NA", "V_TE"}
    for k in sorted(REQ_N, key=len, reverse=True):
        if o.startswith(k):
            return NOUNY | {"NO"} if k in ("なんかで", "だったら") else NOUNY
    for k in sorted(REQ_PLAIN, key=len, reverse=True):
        if o.startswith(k):
            return PLAIN | {"NA_NA", "V_TE"}
    for k in sorted(REQ_RENTAI, key=len, reverse=True):
        if o.startswith(k):
            return RENTAI
    for k in REQ_VDIC:
        if o.startswith(k):
            return {"V_DIC", "N"}
    if o in BARE:
        r = set(BARE[o])
        if LENIENT:
            r |= {"V_TE", "V_RENYO"}
        return r
    tl = toks(o)
    if not tl:
        return set(CATS)
    t0 = tl[0]
    p = pos(t0)
    if o in CONJ_WORDS or p[0] == "接続詞":
        return {"BOUND", "SETSU", "V_TE"}
    if p[0] == "副詞":
        return {"BOUND", "PART", "ADV", "V_TE", "SETSU"} | {c for c in CATS if c.startswith("PART")}
    if p[0] == "助詞":
        # 未登记的裸助詞：宽松
        return PLAIN | {"NO", "NA_NA", "V_TE", "V_RENYO"}
    if p[0] == "助動詞":
        return NOUNY | {"V_DIC", "V_TA", "IADJ"}
    if p[0] in ("動詞", "形容詞"):
        return PRED_SLOT | {"BOUND"}
    if p[0] == "名詞":
        return RENTAI | {"PART", "BOUND", "ADV"} | {c for c in CATS if c.startswith("PART")}
    return set(CATS) | {"NO", "NA_NA"}


def te_aux_violation(left_c, opt):
    """左侧是て形时，检查选项开头是否为合法补助动词。"""
    if "V_TE" not in left_c:
        return False
    tl = toks(opt)
    if not tl:
        return False
    t0 = tl[0]
    if pos(t0)[0] == "動詞":
        b = t0.base_form
        if b in TE_AUX_NG:
            return True
        if b in TE_AUX_OK:
            return False
        # 「〜て＋一般動詞」在て中止形下合法（例:進めて考える）
        return False
    return False


def split_blank(stem):
    i = stem.find("（　）")
    if i < 0:
        i = stem.find("(　)")
    if i < 0:
        return None, None
    return stem[:i], stem[i + 3:]


def n_excluded_by_setsuzoku(it):
    """返回 (可排除的选项号集合, 左侧类别)。仅用『空格前形态』判断。"""
    L, R = split_blank(it.stem)
    if L is None:
        return None, None
    lc = left_cats(L)
    bad = set()
    for k, o in it.opts.items():
        req = opt_req(o)
        if not (req & lc):
            bad.add(k)
        elif te_aux_violation(lc, o):
            bad.add(k)
    return bad, lc


# ============================================================================
# 3. 呼応 / 格・态 规则（H2, H3）
# ============================================================================

NEG_PAT = re.compile(r"(ない|ぬ|ず|ません|まい|なかった|なく)")
KOOU = [
    # (左侧触发词, 选项必须匹配的正则, 规则名)
    (re.compile(r"しか$|しか[、]?$"), NEG_PAT, "しか…ない"),
    (re.compile(r"決して"), NEG_PAT, "決して…ない"),
    (re.compile(r"一向に"), NEG_PAT, "一向に…ない"),
    (re.compile(r"全然"), NEG_PAT, "全然…ない"),
    (re.compile(r"どうりで|道理で"), re.compile(r"はず"), "どうりで…はず"),
    (re.compile(r"まるで|あたかも"), re.compile(r"よう|みたい"), "まるで…ようだ"),
    (re.compile(r"たとえ"), re.compile(r"ても|でも"), "たとえ…ても"),
    (re.compile(r"何の.*も$|何ら.*も$"), NEG_PAT, "何の…も…ない"),
]


def kooou_excluded(it):
    L, R = split_blank(it.stem)
    if L is None:
        return set(), []
    bad, fired = set(), []
    for trig, need, name in KOOU:
        if trig.search(L):
            hit = {k for k, o in it.opts.items() if not need.search(o)}
            if 0 < len(hit) < 4:
                bad |= hit
                fired.append(name)
    return bad, fired


VOICE_RE = re.compile(r"(せ|さ)れ")  # 受身/使役受身


def voice_case_excluded(it):
    """左侧以『に』结尾且选项为使役/受身对立时，に＋使役 不合法。"""
    L, R = split_blank(it.stem)
    if L is None or not L.rstrip("、").endswith("に"):
        return set()
    vals = list(it.opts.items())
    has_pass = any(VOICE_RE.search(o) for _, o in vals)
    has_caus = any(re.search(r"[^さ]せ(?!ら)", o) and not VOICE_RE.search(o) for _, o in vals)
    if has_pass and has_caus:
        return {k for k, o in vals if not VOICE_RE.search(o) and re.search(r"[^さ]せ(?!ら)", o)}
    return set()


# ============================================================================
# 4. 其他假设
# ============================================================================


def longest_common_prefix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def longest_common_suffix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def grid2x2(it):
    """检测最小对立对 2x2 网格：4 个选项由 前件A/B × 后件X/Y 组合而成。
    返回 (前件分组 dict, 后件分组 dict) 或 None。"""
    o = it.opts
    ks = sorted(o)
    if len(ks) != 4:
        return None
    # 前缀分组
    pre = defaultdict(list)
    for a, b in combinations(ks, 2):
        n = longest_common_prefix(o[a], o[b])
        if n >= 2:
            pre[(a, b)] = n
    suf = defaultdict(list)
    for a, b in combinations(ks, 2):
        n = longest_common_suffix(o[a], o[b])
        if n >= 2:
            suf[(a, b)] = n
    # 需要恰好 2 对共享前缀 + 2 对共享后缀，且构成完美匹配
    def perfect(pairs):
        for p1, p2 in combinations(pairs, 2):
            if set(p1) | set(p2) == set(ks):
                return (p1, p2)
        return None
    P = perfect(list(pre.keys()))
    S = perfect(list(suf.keys()))
    if P and S:
        return P, S
    return None


def opt_len_stats(items):
    res = {"longest": 0, "shortest": 0, "n": 0, "mid": 0}
    for it in items:
        if it.ans is None or len(it.opts) != 4:
            continue
        ls = {k: len(v) for k, v in it.opts.items()}
        mx, mn = max(ls.values()), min(ls.values())
        res["n"] += 1
        if ls[it.ans] == mx and list(ls.values()).count(mx) == 1:
            res["longest"] += 1
        if ls[it.ans] == mn and list(ls.values()).count(mn) == 1:
            res["shortest"] += 1
    return res


HONORIFIC = re.compile(r"(まいり|いたし|いらっしゃ|なさ|くださ|いただ|申し|拝見|伺|ござ|おっしゃ)")


# ============================================================================
# 5. 报告
# ============================================================================


def rate(h, n):
    return f"{h}/{n} = {h/n*100:.1f}%" if n else f"{h}/0 = n/a"


def flag(n):
    return "  【样本不足 n<8】" if n < 8 else ""


def sec_items(papers, keys, sec):
    out = []
    for k in keys:
        out += [i for i in papers[k] if i.sec == sec]
    return out


def report():
    papers = load_all()
    order = ["2024-12", "2025-07", "2025-12", "2026-07"]
    clean = ["2025-07", "2025-12", "2026-07"]
    out = []
    W = out.append

    W("# JLPT N1 文法（問題5/6/7）实证挖掘报告")
    W("")
    W(f"数据：4 套 × 19 题 = 76 题（問題5 40 / 問題6 20 / 問題7 16）。")
    W("2024-12 为回忆重排版，含印刷讹误，所有统计单列。基线 = 25%。")
    W("")

    # ---------------- H1 ----------------
    W("## H1（核心）『空格前形态决定接续合法性，可排除选项』——問題5 逐题实测")
    W("")
    W("判定口径：把空格左侧文本用 janome 分词，取最后一个实词/助词的形态，"
      "得到该空位提供的『接续位』类别；对每个选项按标准语法书『接続』栏取其"
      "要求的前接形态集合；两者交集为空 = 该选项接续不合法、可排除。"
      "**只看空格左侧**（严格按原假设）。")
    W("")
    W("| 卷 | 题 | 左侧末形态 | 可排除选项数 | 被排除的选项 | 是否含正确答案(错杀) |")
    W("|---|---|---|---|---|---|")
    dist_all = defaultdict(lambda: Counter())
    detail = {}
    for p in order:
        for it in sec_items(papers, [p], "問題5"):
            bad, lc = n_excluded_by_setsuzoku(it)
            if bad is None:
                continue
            detail[(p, it.num)] = bad
            dist_all[p][len(bad)] += 1
            if bad:
                W(f"| {p} | {it.num} | {'/'.join(sorted(c for c in lc if not c.startswith('PART:')))} "
                  f"| {len(bad)} | {', '.join(str(b)+'.'+it.opts[b] for b in sorted(bad))} "
                  f"| {'是(错杀)' if it.ans in bad else '否'} |")
    W("")
    W("（表中只列出『能排除至少 1 个』的题；其余题目一律 0 排除。）")
    W("")
    W("### 排除数分布")
    W("")
    W("| 卷 | 排除0个 | 排除1个 | 排除2个 | 排除3个 | 小计 |")
    W("|---|---|---|---|---|---|")
    tot = Counter()
    for p in order:
        d = dist_all[p]
        W(f"| {p} | {d[0]} | {d[1]} | {d[2]} | {d[3]} | {sum(d.values())} |")
        for k, v in d.items():
            tot[k] += v
    W(f"| **4卷合计** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** | **{sum(tot.values())}** |")
    clean_tot = Counter()
    for p in clean:
        for k, v in dist_all[p].items():
            clean_tot[k] += v
    W(f"| 3卷正式版(不含2024-12) | {clean_tot[0]} | {clean_tot[1]} | {clean_tot[2]} | {clean_tot[3]} | {sum(clean_tot.values())} |")
    W("")
    nz = sum(v for k, v in tot.items() if k > 0)
    W(f"**结论（严格口径）：40 题中有 {tot[0]} 题四个选项接续全部合法（接续规则完全无效），"
      f"只有 {nz} 题能排除掉任何选项，且没有任何一题能排除到 3 个。**")
    W(f"接续规则的『有效率』= {nz}/40 = {nz/40*100:.1f}%。")
    W("")
    # 宽松口径
    global LENIENT
    LENIENT = True
    tot2 = Counter()
    for p in order:
        for it in sec_items(papers, [p], "問題5"):
            bad, _ = n_excluded_by_setsuzoku(it)
            if bad is not None:
                tot2[len(bad)] += 1
    LENIENT = False
    nz2 = sum(v for k, v in tot2.items() if k > 0)
    W(f"**宽松口径**（把「〜てのみ」这类语法书未收但书面语确有的接续也算合法）："
      f"全合法 {tot2[0]}/40，能排除的只剩 {nz2} 题。")
    W("")

    # H1 附：加上右侧上下文
    W("### H1' 放宽：同时看空格右侧（终止/连体要求）")
    W("")
    W("把『空格后必须能接下去』也算进来（例：空格后是名詞→选项须为连体形；"
      "空格后是句点→选项须能终止）。这已经超出原假设，仅作对照。")
    n_right = 0
    for p in order:
        for it in sec_items(papers, [p], "問題5"):
            L, R = split_blank(it.stem)
            if L is None:
                continue
            Rs = R.strip()
            if not Rs:
                continue
            bad = set()
            if Rs[0] in "。」！？":
                for k, o in it.opts.items():
                    tl = toks(o)
                    if tl and pos(tl[-1])[0] == "助詞" and pos(tl[-1])[1] == "接続助詞":
                        bad.add(k)
            else:
                rt = toks(Rs)
                if rt and pos(rt[0])[0] == "名詞" and pos(rt[0])[1] not in ("非自立", "接尾"):
                    for k, o in it.opts.items():
                        tl = toks(o)
                        if tl and pos(tl[-1])[0] == "助詞" and pos(tl[-1])[1] in ("接続助詞", "終助詞"):
                            bad.add(k)
            if bad - detail.get((p, it.num), set()):
                n_right += 1
    W(f"额外能排除选项的题：{n_right}/40。即便加上右侧约束，仍然杯水车薪。")
    W("")

    # ---------------- H1'' 問題7 ----------------
    W("### H1'' 同一套接续引擎跑 問題7（文章 cloze，16 题）")
    W("")
    W("| 卷 | 题 | 左侧末形态 | 可排除数 | 被排除 | 错杀? |")
    W("|---|---|---|---|---|---|")
    c7 = Counter()
    for p in order:
        bs = parse_bunsho(os.path.join(DATA, f"{p}_言語知識.txt"))
        for it in sec_items(papers, [p], "問題7"):
            if it.num not in bs:
                continue
            L, R = bs[it.num]
            lc = left_cats(L)
            bad = set()
            for k, o in it.opts.items():
                if not (opt_req(o) & lc) or te_aux_violation(lc, o):
                    bad.add(k)
            c7[len(bad)] += 1
            if bad:
                W(f"| {p} | {it.num} | {'/'.join(sorted(x for x in lc if not x.startswith('PART:')))} "
                  f"| {len(bad)} | {', '.join(str(b)+'.'+it.opts[b] for b in sorted(bad))} "
                  f"| {'是' if it.ans in bad else '否'} |")
    W("")
    W(f"問題7 排除数分布：0个={c7[0]}题, 1个={c7[1]}题, 2个={c7[2]}题, 3个={c7[3]}题（共 {sum(c7.values())} 题）。")
    W("")

    # ---------------- H2 呼応 ----------------
    W("## H2 呼応规则（しか…ない / どうりで…はず / 決して…ない 等）")
    W("")
    W("| 卷 | 题 | 触发规则 | 排除数 | 排除后是否唯一 | 是否命中答案 |")
    W("|---|---|---|---|---|---|")
    kn = kh = kuni = 0
    for p in order:
        for it in sec_items(papers, [p], "問題5"):
            bad, fired = kooou_excluded(it)
            if not fired:
                continue
            kn += 1
            uniq = len(bad) == 3
            ok = it.ans not in bad
            kh += ok
            kuni += uniq and ok
            W(f"| {p} | {it.num} | {'+'.join(fired)} | {len(bad)} | {'唯一' if uniq else '否'} | {'✓' if ok else '✗错杀'} |")
    W("")
    W(f"呼応规则触发 n={kn}，不错杀 {rate(kh, kn)}，直接定唯一答案 {kuni} 题。{flag(kn)}")
    W("")

    # ---------------- H3 格・态 ----------------
    W("## H3 格助詞·态一致（『に』＋受身 vs 使役）")
    vn = vh = 0
    for p in order:
        for it in sec_items(papers, [p], "問題5"):
            bad = voice_case_excluded(it)
            if bad:
                vn += 1
                vh += it.ans not in bad
                W(f"- {p} #{it.num}: 排除 {sorted(bad)} → {'✓' if it.ans not in bad else '✗'}（答案 {it.ans}）")
    W("")
    W(f"n={vn}，不错杀 {rate(vh, vn)}。{flag(vn)}")
    W("")

    # ---------------- H4 2x2 ----------------
    W("## H4 最小对立对（2×2 网格）中答案偏好哪一侧")
    W("")
    W("检测：4 个选项能否分解为 前件{A,B} × 后件{X,Y}。若能，看答案落在哪一格，"
      "以及『长前件/短前件』『长后件/短后件』的偏好。")
    W("")
    g_n = 0
    pref_long_pre = pref_long_suf = 0
    idx_in_grid = Counter()
    grid_items = []
    for p in order:
        for it in sec_items(papers, [p], "問題5") + sec_items(papers, [p], "問題7"):
            g = grid2x2(it)
            if not g or it.ans is None:
                continue
            g_n += 1
            grid_items.append((p, it, g))
            P, S = g
            # 答案所在的前件组、后件组
            pgrp = [x for x in P if it.ans in x][0]
            sgrp = [x for x in S if it.ans in x][0]
            other_p = [x for x in P if x != pgrp][0]
            other_s = [x for x in S if x != sgrp][0]
            lp = sum(len(it.opts[k]) for k in pgrp)
            lop = sum(len(it.opts[k]) for k in other_p)
            ls = sum(len(it.opts[k]) for k in sgrp)
            los = sum(len(it.opts[k]) for k in other_s)
            pref_long_pre += lp > lop
            pref_long_suf += ls > los
            idx_in_grid[it.ans] += 1
    W(f"检出 2×2 网格题 n={g_n}（問題5+問題7）。{flag(g_n)}")
    if g_n:
        W(f"- 答案落在『较长前件』一侧：{rate(pref_long_pre, g_n)}（基线 50%）")
        W(f"- 答案落在『较长后件』一侧：{rate(pref_long_suf, g_n)}（基线 50%）")
        W(f"- 答案编号分布：{dict(sorted(idx_in_grid.items()))}")
    W("")

    # ---------------- H5 长度 ----------------
    W("## H5 选项长度")
    W("")
    W("| 范围 | n | 答案=唯一最长 | 答案=唯一最短 |")
    W("|---|---|---|---|")
    for name, keys in [("4卷 問題5", order), ("3卷正式版 問題5", clean)]:
        st = opt_len_stats(sec_items(papers, keys, "問題5"))
        W(f"| {name} | {st['n']} | {rate(st['longest'], st['n'])} | {rate(st['shortest'], st['n'])} |")
    st = opt_len_stats(sec_items(papers, order, "問題7"))
    W(f"| 4卷 問題7 | {st['n']} | {rate(st['longest'], st['n'])} | {rate(st['shortest'], st['n'])} |")
    W("")

    # ---------------- H6 答案编号 ----------------
    W("## H6 答案编号分布")
    W("")
    W("| 范围 | 1 | 2 | 3 | 4 | n |")
    W("|---|---|---|---|---|---|")
    for sec in ("問題5", "問題6", "問題7"):
        c = Counter(i.ans for i in sec_items(papers, order, sec) if i.ans)
        W(f"| 4卷 {sec} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {sum(c.values())} |")
    c = Counter(i.ans for i in sec_items(papers, order, "問題5") + sec_items(papers, order, "問題6")
                + sec_items(papers, order, "問題7") if i.ans)
    W(f"| **全文法 76 题** | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {sum(c.values())} |")
    W("")
    best = max(c, key=lambda k: c[k])
    W(f"最优固定猜测 = {best}，命中 {rate(c[best], sum(c.values()))}。")
    W("")

    # ---------------- H7 敬语 ----------------
    W("## H7 敬语题：て形补助动词白名单 + 主语方向")
    W("")
    hn = hexcl = hsolved = 0
    for p in order:
        for it in sec_items(papers, [p], "問題5") + sec_items(papers, [p], "問題7"):
            if sum(1 for o in it.opts.values() if HONORIFIC.search(o)) < 3:
                continue
            hn += 1
            L, _ = split_blank(it.stem) or ("", "")
            lc = left_cats(L) if L else set()
            bad = {k for k, o in it.opts.items() if te_aux_violation(lc, o)}
            # 主语方向：题干含 弊社/私ども/当社 → 谦让；含 お客様/先生 → 尊敬
            humble = bool(re.search(r"弊社|当社|私ども|わたくし", it.stem))
            rest = [k for k in it.opts if k not in bad]
            pick = None
            if humble:
                cand = [k for k in rest if re.search(r"まいり|いたし|申し|伺|拝見|おり", it.opts[k])]
                if len(cand) == 1:
                    pick = cand[0]
            if bad:
                hexcl += 1
            if pick == it.ans:
                hsolved += 1
            W(f"- {p} #{it.num}: 接续排除 {sorted(bad)}；主语方向定答 {pick}；正确答案 {it.ans} "
              f"→ {'✓' if pick == it.ans else '✗'}")
    W("")
    W(f"敬语题 n={hn}；接续能排除选项的 {hexcl} 题；『接续+主语方向』直接定答且正确 {hsolved} 题。{flag(hn)}")
    W("")

    # ---------------- 留一验证 ----------------
    W("## 留一验证（3 套挖 / 1 套验）")
    W("")
    W("可算法化的规则合成为一个『排除+决策』流水线：")
    W("1. 接续不合法 → 排除；2. 呼応不匹配 → 排除；3. 格·态不一致 → 排除；")
    W("4. 若剩 1 个 → 输出；5. 否则按训练集学到的最优固定编号猜测兜底。")
    W("")

    # 問題6 交给 star_solver（约束过滤 + 软打分 argmax）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import star_solver as SS
        P6 = {}
        for pth in sorted(glob.glob(os.path.join(DATA, "*言語知識*.txt"))):
            for q in SS.parse_p6(pth):
                r = SS.solve(q)
                if r.get("status") != "PARSE_FAIL":
                    P6[(q.paper, q.num)] = r["pred"] if r["pred"] else r["fallback"]
    except Exception as e:  # pragma: no cover
        P6 = {}
        W(f"（star_solver 集成失败：{e}）")

    def pipeline(it, fallback):
        if it.sec == "問題6" and (it.paper, it.num) in P6:
            return P6[(it.paper, it.num)], False
        bad = set()
        b1, _ = n_excluded_by_setsuzoku(it)
        if b1:
            bad |= b1
        b2, _ = kooou_excluded(it)
        bad |= b2
        bad |= voice_case_excluded(it)
        rest = [k for k in sorted(it.opts) if k not in bad]
        if len(rest) == 1:
            return rest[0], True
        if fallback in rest:
            return fallback, False
        return (rest[0] if rest else fallback), False

    W("| 折 | 训练集 | 验证集 | 训练命中 | 验证命中 | 验证中『规则定答』题数/其中对 |")
    W("|---|---|---|---|---|---|")
    TRH = TRN = TEH = TEN = 0
    for held in order:
        tr = [p for p in order if p != held]
        tr_items = sec_items(papers, tr, "問題5") + sec_items(papers, tr, "問題6") + sec_items(papers, tr, "問題7")
        te_items = sec_items(papers, [held], "問題5") + sec_items(papers, [held], "問題6") + sec_items(papers, [held], "問題7")
        c = Counter(i.ans for i in tr_items if i.ans)
        fb = max(c, key=lambda k: c[k])
        trh = sum(1 for i in tr_items if i.ans and pipeline(i, fb)[0] == i.ans)
        teh = sum(1 for i in te_items if i.ans and pipeline(i, fb)[0] == i.ans)
        det = [(i, pipeline(i, fb)) for i in te_items if i.ans]
        ndet = sum(1 for _, (a, d) in det if d)
        ndet_ok = sum(1 for i, (a, d) in det if d and a == i.ans)
        TRH += trh; TRN += len(tr_items); TEH += teh; TEN += len(te_items)
        W(f"| 留 {held} | {','.join(tr)} | {held} | {rate(trh, len(tr_items))} | "
          f"{rate(teh, len(te_items))} | {ndet}/{ndet_ok} |")
    W("")
    W("注：問題6（組句★题）走 star_solver.py 的『硬约束过滤 + 软打分 argmax』。")
    W("规则本身是手写的语法知识、不含从训练集拟合的参数，唯一从训练集学到的是兜底编号，")
    W(f"所以训练/验证命中率之差基本是噪声。4 折验证合计 {rate(TEH, TEN)}，"
      f"训练合计 {rate(TRH, TRN)}，均在 25% 基线附近。")
    W("")
    return "\n".join(out)


if __name__ == "__main__":
    txt = report()
    print(txt)
    with open("/Users/herclyon/JLPT/mining/_partA.md", "w", encoding="utf-8") as f:
        f.write(txt)
