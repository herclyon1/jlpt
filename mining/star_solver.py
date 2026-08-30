# -*- coding: utf-8 -*-
"""
JLPT N1 問題6（組句★题）约束满足求解器
--------------------------------------------------
用法: python3 star_solver.py [-v]

思路:
  1. 把题干拆成 prefix / 4 个空 / suffix，记录 ★ 落在第几个空。
  2. 每个碎片用 janome 分词，抽出 head(首词) / tail(尾词) 的词性·活用特征。
  3. 对 24 种排列，逐个检查 5 处接缝（prefix|f0, f0|f1, f1|f2, f2|f3, f3|suffix）
     是否违反硬性句法约束；全部通过 = 合法排列。
  4. 判定:
       合法排列恰好 1 个                       -> 确答
       合法排列 >1 但 ★ 位上的碎片编号一致     -> 仍是确答
       合法排列 >1 且 ★ 位编号不一致           -> 多解（再用软打分取 argmax 作兜底）
       合法排列 0 个                           -> 无解（用软打分取 argmax 作兜底）
  硬约束只写"日语里绝对不成立"的接缝，软打分只用来在多解时排序，不参与确答判定。
"""
import glob
import os
import re
import sys
from itertools import permutations

from janome.tokenizer import Tokenizer

DATA = "/Users/herclyon/JLPT/converted"
T = Tokenizer()
VERBOSE = "-v" in sys.argv


# ============================================================================
# 解析
# ============================================================================
class Q:
    def __init__(self, paper, num):
        self.paper, self.num = paper, num
        self.stem = ""
        self.opts = {}
        self.ans = None


BLANK_RE = re.compile(r"[＿_]+(?:★[＿_]*)?")
SLOT_RE = re.compile(r"[＿_]*★[＿_]*|[＿_]+")


def parse_p6(path):
    paper = os.path.basename(path).split("_")[0]
    out, sec, cur = [], None, None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#大題"):
            sec = line.split()[1]
            cur = None
        elif line.startswith("#題") and sec == "問題6":
            cur = Q(paper, int(line.split()[1]))
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("#干"):
            cur.stem = line[3:]
        elif line.startswith("#选"):
            m = re.match(r"#选\s+(\d+)\s+(.*)", line)
            cur.opts[int(m.group(1))] = m.group(2)
        elif line.startswith("#答"):
            cur.ans = int(line.split()[1])
    return out


def split_slots(stem):
    """返回 (prefix, suffix, star_slot_index 0-based)"""
    spans = [m.span() for m in SLOT_RE.finditer(stem)]
    # 合并被空格隔开的连续下划线块 -> 4 个 slot
    slots = []
    for s, e in spans:
        if slots and stem[slots[-1][1]:s].strip() == "":
            slots.append((s, e))
        else:
            slots.append((s, e))
    if len(slots) != 4:
        return None
    star = [i for i, (s, e) in enumerate(slots) if "★" in stem[s:e]]
    if len(star) != 1:
        return None
    prefix = stem[:slots[0][0]]
    suffix = stem[slots[-1][1]:]
    return prefix.strip(), suffix.strip(), star[0]


# ============================================================================
# 形态特征
# ============================================================================
def toks(s):
    return list(T.tokenize(s))


def pz(t):
    return t.part_of_speech.split(",")


def tail_feat(tl):
    """(大类, 细类, 表层, 活用形)"""
    i = len(tl) - 1
    while i > 0 and pz(tl[i])[0] == "記号":
        i -= 1
    t = tl[i]
    p = pz(t)
    return (p[0], p[1], t.surface, t.infl_form, t.base_form)


def head_feat(tl):
    i = 0
    while i < len(tl) - 1 and pz(tl[i])[0] == "記号":
        i += 1
    t = tl[i]
    p = pz(t)
    return (p[0], p[1], t.surface, t.infl_form, t.base_form)


# ============================================================================
# 接続規格：左侧能提供什么形态 / 右侧要求什么形态
# ============================================================================
RENTAI = {"V_DIC", "V_TA", "V_NAI", "IADJ", "NA_NA", "NO", "RENTAI"}
PLAIN = {"V_DIC", "V_TA", "V_NAI", "IADJ", "N", "NA_NA", "NO"}
PRED_SLOT = {"PART", "ADV", "BOUND", "V_TE", "SETSU", "V_RENYO", "RENTAI", "NO", "N"}
ANY = None

# 碎片尾部的形态覆盖（janome 孤立分词会把这些复合辞误判）
LEFT_OVERRIDE = [
    ("ところで", {"SETSU"}),
    ("ならでは", {"N"}),
    ("がゆえに", {"SETSU", "ADV"}),
    ("ゆえに", {"SETSU", "ADV"}),
    ("ように", {"ADV", "SETSU"}),
    ("ことなく", {"ADV", "SETSU"}),
    ("なくして", {"SETSU", "V_TE"}),
    ("について", {"SETSU", "V_TE"}),
    ("によって", {"SETSU", "V_TE"}),
    ("により", {"V_RENYO", "ADV"}),
    ("として", {"SETSU", "V_TE"}),
    ("に対して", {"SETSU", "V_TE"}),
    ("である", {"V_DIC"}),
    ("であり", {"V_RENYO", "ADV"}),
    ("といって", {"SETSU", "V_TE"}),
    ("と思って", {"SETSU", "V_TE"}),
]

# 右侧开头要求的左侧形态（最长前缀匹配）
RIGHT_REQ = [
    # 形似复合辞但实为自立词的例外（None = 不加约束）
    ("限りある", None),
    ("ようやく", None),
    ("ように", RENTAI | {"N"}),
    ("ことなく", {"V_DIC"}),
    ("ことには", RENTAI),
    ("ことが", RENTAI),
    ("ことは", RENTAI),
    ("ことも", RENTAI),
    ("ところで", {"V_TA"}),
    ("ところが", RENTAI),
    ("ならでは", {"N"}),
    ("がゆえに", RENTAI | {"N"}),
    ("ゆえに", RENTAI | {"N"}),
    ("ままに", RENTAI),
    ("まま", RENTAI),
    ("なり、", {"V_DIC"}),
    ("なり,", {"V_DIC"}),
    ("限り", RENTAI | {"N"}),
    ("かぎり", RENTAI | {"N"}),
    ("次第", {"V_RENYO", "N"}),
    ("あげく", {"V_TA", "NO"}),
    ("とたん", {"V_TA"}),
    ("以上", {"V_DIC", "V_TA", "V_NAI", "N"}),
    ("うえで", {"V_TA", "NO"}),
    ("べく", {"V_DIC"}),
    ("ずにはいられない", {"V_MIZEN"}),
    ("といった", PLAIN),
    ("という", PLAIN),
    ("といえる", PLAIN),
    ("とあって", PLAIN),
    ("ように", RENTAI | {"N"}),
    ("ような", RENTAI | {"N"}),
    ("よう", RENTAI | {"N", "V_RENYO", "V_MIZEN"}),
    ("はず", RENTAI),
    ("わけ", RENTAI),
    ("つもり", RENTAI),
    ("ため", RENTAI),
    ("とき", RENTAI),
    ("ほど", RENTAI | {"N"}),
    ("くらい", RENTAI | {"N"}),
    ("ばかり", RENTAI | {"N", "V_TE"}),
    ("のに", RENTAI),
    ("ので", RENTAI),
    ("のか", RENTAI),
    ("のが", RENTAI),
    ("のは", RENTAI),
    ("のだ", RENTAI),
    ("んだ", RENTAI),
    ("こそ", {"N", "V_TE", "V_RENYO", "PART"}),
    ("さえ", {"N", "V_TE", "V_RENYO", "PART"}),
    ("でも", {"N", "V_TE", "V_RENYO", "PART", "NA_NA"}),
    ("しか", {"N", "PART", "V_DIC"}),
    ("だけ", RENTAI | {"N"}),
    ("なら", PLAIN),
    ("ならば", PLAIN),
]

# 允许直接跟在格助詞后面的助詞（は/も 等叠加）
JOSHI_AFTER_KAKU = {"は", "も", "こそ", "さえ", "しか", "だけ", "でも", "ばかり",
                    "など", "なり", "やら", "か", "の", "すら", "って", "とも"}
# 允许跟在て形后的助詞
JOSHI_AFTER_TE = {"は", "も", "から", "こそ", "さえ", "まで", "ばかり", "など"}
# 终止形之后允许的接续（否则句子中途结束 = 非法）
AFTER_SHUUSHI = {"が", "けど", "けれど", "けれども", "から", "ので", "のに", "し",
                 "と", "か", "な", "よ", "ね", "って", "とも", "の", "し"}
FINAL_AUX = {"だ", "です", "ます", "た"}


def is_shuushi_only(f):
    """尾部是否是只能句末出现的形式（です/ます/だ 的基本形）"""
    return f[0] == "助動詞" and f[4] in ("です", "ます") and f[3] == "基本形"


def lcats(text, tl):
    """左侧文本能提供的接续位类别集合。"""
    t = text.rstrip("　 ")
    for suf, cs in LEFT_OVERRIDE:
        if t.endswith(suf):
            return set(cs)
    if not tl:
        return {"BOUND"}
    f = tail_feat(tl)
    p, sub, s, form, base = f
    c = set()
    if p == "記号":
        return {"BOUND"}
    if p == "助詞":
        if sub == "接続助詞":
            c.add("V_TE" if s in ("て", "で") else "SETSU")
        elif sub == "連体化":
            c.add("NO")
        elif sub == "副詞化":
            c.add("ADV")
        elif sub == "終助詞":
            c.add("BOUND")
        else:
            c.add("PART")
            c.add("PART:" + s)
        return c
    if p == "動詞":
        if form in ("基本形", "体言接続"):
            c.add("V_DIC")
        elif form.startswith("連用"):
            c.add("V_RENYO")
        elif form.startswith("未然"):
            c.add("V_MIZEN")
        elif form.startswith("仮定"):
            c.add("SETSU")
        else:
            c.add("V_DIC")
        return c
    if p == "助動詞":
        if base == "た":
            c.add("V_TA")
        elif base == "ない":
            c.add("V_NAI")
        elif base in ("だ", "です"):
            if form == "体言接続":
                c.add("NA_NA")
            elif form == "連用形":
                c.add("PART")
            elif form == "仮定形":
                c.add("SETSU")
            else:
                c.add("V_DIC")
        else:
            c.add("V_DIC")
        return c
    if p == "形容詞":
        if form == "基本形":
            c.add("IADJ")
        elif "連用" in form:
            c.add("ADV")
        elif form.startswith("仮定"):
            c.add("SETSU")
        else:
            c.add("IADJ")
        return c
    if p == "名詞":
        c.add("N")
        if sub in ("形容動詞語幹", "ナイ形容詞語幹"):
            c.add("NA")
        if sub == "サ変接続":
            c.add("SAHEN")
        return c
    if p == "副詞":
        return {"ADV"}
    if p == "接続詞":
        return {"SETSU", "ADV"}
    if p == "連体詞":
        return {"RENTAI"}
    return {"N"}


def rreq(text, tl, with_flag=False):
    """右侧开头要求的左侧类别集合；None = 无词汇级约束。"""
    t = text.lstrip("　 ")
    # 只在词边界上匹配复合辞，避免「ようやく」被当成「よう」
    bounds, acc = set(), 0
    for tk in tl:
        acc += len(tk.surface)
        bounds.add(acc)
    for pre, cs in sorted(RIGHT_REQ, key=lambda x: -len(x[0])):
        if t.startswith(pre) and (len(pre) in bounds or not bounds):
            r = set(cs) if cs is not None else None
            return (r, True) if with_flag else r
    if not tl:
        return (None, False) if with_flag else None
    p, sub, s, form, base = head_feat(tl)
    def ret(v):
        return (v, False) if with_flag else v
    # 形式名詞（非自立）必须有连体修饰
    if p == "名詞" and sub == "非自立" and s not in ("うち",):
        return ret(set(RENTAI))
    # 格助詞 を/が/へ 必须接体言
    if p == "助詞" and sub == "格助詞" and s in ("を", "が", "へ"):
        return ret({"N", "NA", "SAHEN", "NO", "BOUND"})
    # 係助詞 は/も 不能接用言终止形
    if p == "助詞" and sub == "係助詞":
        return ret({"N", "NA", "SAHEN", "PART", "V_TE", "V_RENYO", "SETSU", "ADV", "BOUND"})
    # 補助動詞
    if p == "動詞" and sub == "非自立":
        return ret({"V_TE", "V_RENYO", "N", "PART"})
    return ret(None)


def junction_ok(ltl, rtl, at_prefix=False, at_suffix=False, ltext="", rtext=""):
    """判断接缝是否合法。ltl/rtl 为左右两侧的 token 列表。"""
    if not ltl or not rtl:
        return True
    # --- 词汇级接続規格 ---
    req, matched = rreq(rtext, rtl, with_flag=True)
    cs = lcats(ltext, ltl)
    base = {c.split(":")[0] for c in cs}
    if req is not None:
        if not (base & req):
            return False
    if matched:
        return True  # 复合辞已由词汇表判定，不再套用泛化词性规则

    L = tail_feat(ltl)
    R = head_feat(rtl)

    # A. 連体形/終止形 之后不能直接跟自立動詞（两个连体节无法直接堆叠）
    if base and base <= {"V_DIC", "V_TA", "V_NAI", "IADJ", "NA_NA"}:
        if R[0] == "動詞" and R[1] == "自立":
            return False
        if R[0] == "接続詞":
            return False
    # B. 副詞之后不能直接跟助詞
    if L[0] == "副詞" and R[0] == "助詞" and R[1] in ("格助詞", "係助詞", "連体化", "副助詞"):
        return False
    # C. 連体詞之后必须是体言性成分
    if L[0] == "連体詞" and R[0] not in ("名詞", "接頭詞", "連体詞", "形容詞", "副詞"):
        return False
    lp, lsub, ls, lf, lb = L
    rp, rsub, rs, rf, rb = R

    # 0. 句读点后基本自由
    if lp == "記号":
        return True

    # 1. 助動詞 です/ます 基本形只能结句
    if is_shuushi_only(L) and not at_suffix:
        if not (rp == "助詞" and rs in AFTER_SHUUSHI):
            return False

    # 2. 左尾是格助詞
    if lp == "助詞" and lsub == "格助詞":
        if rp == "助詞":
            if rs not in JOSHI_AFTER_KAKU:
                return False
            # を/が 后不能再叠 は/も
            if ls in ("を", "が") and rs in ("は", "も", "が", "を"):
                return False
        if rp == "助動詞" and rb in ("だ", "です"):
            return False
    # 3. 左尾是連体化「の」
    if lp == "助詞" and lsub == "連体化":
        if rp not in ("名詞", "接頭詞", "連体詞", "形容詞", "副詞"):
            return False
        if rp == "名詞" and rsub in ("接続詞的",):
            return False
    # 4. 左尾是係助詞/副助詞
    if lp == "助詞" and lsub in ("係助詞", "副助詞", "副助詞／並立助詞／終助詞"):
        if rp == "助詞" and rsub in ("格助詞", "係助詞", "連体化"):
            return False
    # 5. 左尾是接続助詞
    if lp == "助詞" and lsub == "接続助詞":
        if ls in ("て", "で"):
            if rp == "助詞" and rs not in JOSHI_AFTER_TE:
                return False
        else:
            if rp == "助詞" and rsub in ("格助詞", "連体化"):
                return False
    # 6. 左尾是終助詞 -> 只能结句
    if lp == "助詞" and lsub == "終助詞" and not at_suffix:
        if rp != "記号":
            return False
    # 7. 左尾是名詞，右头是動詞：缺格助詞（サ変名詞＋する 除外）
    if lp == "名詞" and rp == "動詞":
        if not (lsub == "サ変接続" and rb in ("する", "できる", "なさる", "いたす")):
            if rsub != "非自立":
                return False
    # 8. 左尾是動詞連用形（ます形词干），右头是格助詞 -> 非法
    if lp == "動詞" and lf in ("連用形",) and rp == "助詞" and rsub == "格助詞":
        return False
    # 9. 左尾是未然形 -> 右侧必须是助動詞/接尾
    if lp == "動詞" and lf.startswith("未然"):
        if not (rp in ("助動詞",) or (rp == "動詞" and rsub == "接尾")):
            return False
    # 10. 左尾是形容動詞語幹（な形），右头不能是格助詞
    if lp == "名詞" and lsub == "形容動詞語幹" and rp == "助詞" and rsub == "格助詞":
        if rs not in ("に", "で", "と"):
            return False
    # 11. 右头是格助詞，左尾必须是体言性成分
    if rp == "助詞" and rsub == "格助詞" and rs in ("を", "が", "へ"):
        if lp in ("副詞", "接続詞", "連体詞"):
            return False
        if lp == "動詞" and lf in ("基本形",) and rs in ("を",):
            return False  # 動詞基本形＋を（除去形式名詞）
    # 12. 右头是助動詞 な/だ（体言接続），左尾必须是体言
    if rp == "助動詞" and rb == "だ" and rf in ("体言接続",) and lp not in ("名詞",):
        return False
    return True


# ============================================================================
# 呼応（跨碎片，硬约束）
# ============================================================================
KOOU_ADJ = [
    (re.compile(r"(いくら|どんなに|いかに|たとえ|仮に)\s*$"),
     re.compile(r"ても|でも|たって|からといって|うと|ところで|ようが")),
    (re.compile(r"(まるで|あたかも)\s*$"), re.compile(r"よう|みたい|ごとく")),
]


def kooou_adj_ok(ltext, rtext):
    for trig, need in KOOU_ADJ:
        if trig.search(ltext) and not need.search(rtext):
            return False
    return True


# ============================================================================
# 字符 n-gram 语言模型（只用 読解/聴解 语料训练，绝不含問題6 题面）
# ============================================================================
class CharLM:
    def __init__(self, n=4):
        self.n = n
        self.cnt = [dict() for _ in range(n + 1)]
        self.tot = [0] * (n + 1)

    def train(self, text):
        for k in range(1, self.n + 1):
            d = self.cnt[k]
            for i in range(len(text) - k + 1):
                g = text[i:i + k]
                d[g] = d.get(g, 0) + 1
                self.tot[k] += 1

    def logp(self, s):
        import math
        lp = 0.0
        V = 4000.0
        for i in range(len(s)):
            p = 0.0
            w = [0.55, 0.28, 0.12, 0.05][: self.n][::-1]
            for k in range(1, self.n + 1):
                if i - k + 1 < 0:
                    continue
                g = s[i - k + 1:i + 1]
                ctx = g[:-1]
                c = self.cnt[k].get(g, 0)
                cc = self.cnt[k - 1].get(ctx, self.tot[1]) if k > 1 else self.tot[1]
                pk = (c + 0.1) / (cc + 0.1 * V)
                p += w[min(k, len(w)) - 1] * pk
            lp += math.log(max(p, 1e-12))
        return lp


def build_lm():
    lm = CharLM(4)
    buf = []
    for p in glob.glob(os.path.join(DATA, "*読解*.txt")) + glob.glob(os.path.join(DATA, "*聴解*.txt")):
        for line in open(p, encoding="utf-8"):
            line = line.rstrip("\n")
            if line.startswith("#干") or line.startswith("#选"):
                buf.append(re.sub(r"^#\S+\s*\d*\s*", "", line))
            elif not line.startswith("#"):
                buf.append(line)
    txt = "\n".join(buf)
    lm.train(txt)
    return lm, len(txt)


LM, LM_SIZE = build_lm()
# 语料仅 7 万字符，实测加权后反而掉点，默认关闭（见报告 LM 消融）
LM_W = 0.0


# ---- 软打分（只在多解/无解时排序用）----
def soft_score(seq_tls, prefix_tl, suffix_tl):
    s = 0.0
    chain = [prefix_tl] + seq_tls + [suffix_tl]
    for a, b in zip(chain, chain[1:]):
        if not a or not b:
            continue
        L, R = tail_feat(a), head_feat(b)
        # 名詞+名詞 轻罚
        if L[0] == "名詞" and R[0] == "名詞":
            s -= 0.5
        # 格助詞 + 用言 奖励
        if L[0] == "助詞" and L[1] == "格助詞" and R[0] in ("動詞", "形容詞", "副詞"):
            s += 0.8
        # 連体形 + 名詞 奖励
        if L[0] in ("動詞", "形容詞") and L[3] == "基本形" and R[0] == "名詞":
            s += 0.6
        if L[0] == "助詞" and L[1] == "連体化" and R[0] == "名詞":
            s += 0.8
        # 接続助詞 + 新句起点 奖励
        if L[0] == "助詞" and L[1] == "接続助詞" and R[0] in ("名詞", "副詞", "接続詞"):
            s += 0.4
        # 副詞 + 用言 奖励
        if L[0] == "副詞" and R[0] in ("動詞", "形容詞", "名詞"):
            s += 0.3
    return s


# ============================================================================
# 求解
# ============================================================================
def solve(q):
    sp = split_slots(q.stem)
    if sp is None:
        return dict(status="PARSE_FAIL")
    prefix, suffix, star = sp
    ids = sorted(q.opts)
    tl = {i: toks(q.opts[i]) for i in ids}
    ptl, stl = toks(prefix), toks(suffix)

    legal, scored = [], []
    for perm in permutations(ids):
        chain = [ptl] + [tl[i] for i in perm] + [stl]
        texts = [prefix] + [q.opts[i] for i in perm] + [suffix]
        ok = True
        for j in range(len(chain) - 1):
            if not junction_ok(chain[j], chain[j + 1],
                               at_prefix=(j == 0), at_suffix=(j == len(chain) - 2),
                               ltext=texts[j], rtext=texts[j + 1]):
                ok = False
                break
            if not kooou_adj_ok(texts[j], texts[j + 1]):
                ok = False
                break
        sent = prefix + "".join(q.opts[i] for i in perm) + suffix
        sc = soft_score([tl[i] for i in perm], ptl, stl) + LM_W * LM.logp(sent)
        scored.append((sc, perm, ok))
        if ok:
            legal.append(perm)

    star_ids = {p[star] for p in legal}
    if len(legal) == 0:
        status = "NO_SOLUTION"
    elif len(legal) == 1:
        status = "UNIQUE"
    elif len(star_ids) == 1:
        status = "STAR_CONSISTENT"
    else:
        status = "AMBIGUOUS"

    det = status in ("UNIQUE", "STAR_CONSISTENT")
    pred = list(star_ids)[0] if det else None
    # 兜底：软打分 argmax（多解时只在合法集内选）
    pool = [x for x in scored if x[2]] or scored
    best = max(pool, key=lambda x: x[0])
    fb = best[1][star]
    return dict(status=status, n_legal=len(legal), pred=pred, fallback=fb,
                star=star, legal=legal, prefix=prefix, suffix=suffix)


def main():
    qs = []
    for p in sorted(glob.glob(os.path.join(DATA, "*言語知識*.txt"))):
        qs += parse_p6(p)
    rows = []
    for q in qs:
        r = solve(q)
        rows.append((q, r))

    out = []
    W = out.append
    W("# 組句★题求解器实测（問題6，4 卷 × 5 题 = 20 题）")
    W("")
    W("| 卷 | 题 | ★位 | 合法排列数 | 判定 | 确答输出 | 软打分兜底 | 正确答案 | 确答对错 |")
    W("|---|---|---|---|---|---|---|---|---|")
    for q, r in rows:
        if r["status"] == "PARSE_FAIL":
            W(f"| {q.paper} | {q.num} | - | - | 解析失败 | - | - | {q.ans} | - |")
            continue
        mark = ""
        if r["pred"] is not None:
            mark = "✓" if r["pred"] == q.ans else "✗"
        W(f"| {q.paper} | {q.num} | {r['star']+1} | {r['n_legal']} | {r['status']} | "
          f"{r['pred'] if r['pred'] else '-'} | {r['fallback']} | {q.ans} | {mark} |")
    W("")

    def block(name, sel):
        sub = [(q, r) for q, r in rows if sel(q) and r["status"] != "PARSE_FAIL"]
        n = len(sub)
        det = [(q, r) for q, r in sub if r["pred"] is not None]
        det_ok = sum(1 for q, r in det if r["pred"] == q.ans)
        amb = sum(1 for q, r in sub if r["status"] == "AMBIGUOUS")
        nos = sum(1 for q, r in sub if r["status"] == "NO_SOLUTION")
        fb_ok = sum(1 for q, r in sub if r["fallback"] == q.ans)
        W(f"**{name}**（n={n}）")
        W("")
        W(f"- 确答（唯一解 或 多解但★位一致）: {len(det)} 题，其中正确 {det_ok} 题"
          f"（确答准确率 {det_ok}/{len(det)} = {det_ok/len(det)*100:.1f}%）" if det else
          f"- 确答: 0 题")
        W(f"- 多解（★位不一致）: {amb} 题")
        W(f"- 无解（0 个合法排列）: {nos} 题")
        W(f"- 全 20 题都强行给答案（确答优先，否则软打分兜底）总正确率: "
          f"{sum(1 for q, r in sub if (r['pred'] if r['pred'] else r['fallback']) == q.ans)}/{n}")
        W(f"- 纯软打分 argmax 正确率: {fb_ok}/{n} = {fb_ok/n*100:.1f}%（基线 25%）")
        cand = [len({p[r["star"]] for p in r["legal"]}) for q, r in sub if r["legal"]]
        inset = sum(1 for q, r in sub if q.ans in {p[r["star"]] for p in r["legal"]})
        if cand:
            W(f"- ★候选集平均大小: {sum(cand)/len(cand):.2f}/4（硬约束几乎没能缩小候选）；"
              f"正确答案落在候选集内 {inset}/{n}（说明硬约束没有错杀，但也没筛出东西）")
        W(f"- 平均合法排列数: {sum(r['n_legal'] for q, r in sub)/n:.1f}/24")
        W("")

    block("全 4 卷", lambda q: True)
    block("3 套正式版（不含 2024-12 回忆版）", lambda q: q.paper != "2024-12")
    block("2024-12 回忆重排版", lambda q: q.paper == "2024-12")

    if VERBOSE:
        W("## 明细")
        for q, r in rows:
            if r["status"] == "PARSE_FAIL":
                continue
            W(f"### {q.paper} #{q.num}  ★在第{r['star']+1}空  答案={q.ans}")
            W(f"- prefix: 「{r['prefix']}」 suffix: 「{r['suffix']}」")
            for i in sorted(q.opts):
                W(f"  - {i}. {q.opts[i]}")
            W(f"- 合法排列 {r['n_legal']} 个: {r['legal'][:8]}")
            W("")

    txt = "\n".join(out)
    print(txt)
    with open("/Users/herclyon/JLPT/mining/_partB.md", "w", encoding="utf-8") as f:
        f.write(txt)


if __name__ == "__main__":
    main()
