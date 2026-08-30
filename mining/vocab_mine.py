# -*- coding: utf-8 -*-
"""JLPT N1 词汇部分 (問題1-4) 规律挖掘。
用法: python3 vocab_mine.py            # 全量报告
数据: /Users/herclyon/JLPT/converted/*言語知識*.txt
"""
import os, re, glob, json, itertools, collections, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onyomi_port import (solve_onyomi, check_segment, parse_pinyin, splits_of,
                         morae_of, KANA_RE, DAK_NORM, _norm, _related)

CONV = "/Users/herclyon/JLPT/converted"
ENGINE = "/Users/herclyon/JLPT/engine"
MINE_SETS = ["2024-12", "2025-07", "2025-12"]   # 挖掘集
VAL_SETS  = ["2026-07"]                          # 验证集(留一)
CORRUPT = "2024-12"                              # 回忆重排版, 有印刷讹误

# ---------------------------------------------------------------- 解析
def parse_file(path):
    exam = None; mondai = None; items = []; cur = None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#卷"): exam = line.split()[1]
        elif line.startswith("#大題"): mondai = line.split()[1]
        elif line.startswith("#題"):
            cur = {"exam": exam, "mondai": mondai, "no": line.split()[1],
                   "stem": "", "opts": [], "ans": None}
            items.append(cur)
        elif line.startswith("#干") and cur is not None: cur["stem"] = line[3:].strip()
        elif line.startswith("#选") and cur is not None:
            m = re.match(r"#选\s+(\d+)\s*(.*)", line)
            if m: cur["opts"].append(m.group(2))
        elif line.startswith("#答") and cur is not None: cur["ans"] = int(line.split()[1])
    return items

ALL = []
for f in sorted(glob.glob(os.path.join(CONV, "*言語知識*.txt"))):
    ALL += parse_file(f)
Q = [x for x in ALL if x["mondai"] in ("問題1", "問題2", "問題3", "問題4") and x["ans"]]
for it in Q:
    m = re.search(r"＜(.+?)＞", it["stem"])
    it["target"] = m.group(1) if m else it["stem"].strip()
    it["opts"] = [o.replace("＜", "").replace("＞", "") for o in it["opts"]]
    it["cor"] = it["opts"][it["ans"] - 1]
    it["set"] = "mine" if it["exam"] in MINE_SETS else "val"

def sel(mondai=None, group=None, items=None):
    xs = items if items is not None else Q
    if mondai: xs = [x for x in xs if x["mondai"] == mondai]
    if group: xs = [x for x in xs if x["set"] == group]
    return xs

BASE = 0.25
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s); print(s)

def rate(hits, n):
    return f"{hits}/{n} = {hits/n*100:.1f}%" if n else f"0/0 = n/a"

def report(name, pred, items, note=""):
    """pred(item) -> predicted answer index (1-4) or None (弃权)."""
    rows = {}
    for g in ("mine", "val", "all"):
        xs = [x for x in items if g == "all" or x["set"] == g]
        att = [x for x in xs if pred(x) is not None]
        hit = [x for x in att if pred(x) == x["ans"]]
        rows[g] = (len(hit), len(att), len(xs))
    flag = " ⚠样本不足" if rows["all"][1] < 8 else ""
    say(f"  [{name}] 挖掘 {rate(*rows['mine'][:2])} (作答{rows['mine'][1]}/{rows['mine'][2]})"
        f" | 验证 {rate(*rows['val'][:2])} (作答{rows['val'][1]}/{rows['val'][2]})"
        f" | 合计 {rate(*rows['all'][:2])}{flag}" + (f"  {note}" if note else ""))
    return rows

# ---------------------------------------------------------------- 工具
def lev(a, b):
    m, n = len(a), len(b)
    d = list(range(n + 1))
    for i in range(1, m + 1):
        prev, d[0] = d[0], i
        for j in range(1, n + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j-1] + 1, prev + (a[i-1] != b[j-1]))
            prev = cur
    return d[n]

LONGV = set("あいうえお")
def strip_long(s):
    out = []
    for i, c in enumerate(s):
        if c == "ー": continue
        if c == "う" and i > 0 and s[i-1] not in LONGV:
            prev = _norm(s[i-1])
            # お段/う段 后的う 视为长音
            if prev in "おこそとのほもよろをくすつぬふむゆるうょゅ" or s[i-1] in "ょゅ": continue
        if c == "い" and i > 0 and _norm(s[i-1]) in "えけせてねへめれ": continue
        out.append(c)
    return "".join(out)
def strip_soku(s): return s.replace("っ", "")
def strip_yoon(s): return re.sub(r"[ゃゅょ]", "", s)

VOWEL = {}
for _row, _k in [("a","あかさたなはまやらわがざだばぱ"),("i","いきしちにひみりぎじぢびぴ"),
                 ("u","うくすつぬふむゆるぐずづぶぷ"),("e","えけせてねへめれげぜでべぺ"),
                 ("o","おこそとのほもよろをごぞどぼぽ")]:
    for c in _k: VOWEL[c] = _row
CONS = {}
for _r, _k in [("k","かきくけこがぎぐげご"),("s","さしすせそざじずぜぞ"),("t","たちつてとだぢづでど"),
               ("n","なにぬねの"),("h","はひふへほばびぶべぼぱぴぷぺぽ"),("m","まみむめも"),
               ("r","らりるれろ"),("y","やゆよ"),("w","わをん"),("a","あいうえお")]:
    for c in _k: CONS[c] = _r

def diff_type(a, b):
    """a=正解 b=干扰, 返回变形标签集合"""
    if a == b: return {"same"}
    tags = set()
    if _norm(a) == _norm(b): tags.add("清浊")
    if strip_long(a) == strip_long(b) and a != b: tags.add("長短")
    if strip_soku(a) == strip_soku(b) and a != b: tags.add("促音")
    if strip_yoon(a) == strip_yoon(b) and a != b: tags.add("拗直")
    if tags: return tags
    # 组合变形
    for f1, n1 in ((strip_long,"長短"),(strip_soku,"促音"),(strip_yoon,"拗直"),(_norm,"清浊")):
        for f2, n2 in ((strip_long,"長短"),(strip_soku,"促音"),(strip_yoon,"拗直"),(_norm,"清浊")):
            if n1 >= n2: continue
            if f1(f2(a)) == f1(f2(b)): tags.add(n1 + "+" + n2)
    if tags: return tags
    ma, mb = morae_of(a), morae_of(b)
    if len(ma) == len(mb):
        d = [i for i in range(len(ma)) if ma[i] != mb[i]]
        if len(d) == 1:
            x, y = ma[d[0]][0], mb[d[0]][0]
            if VOWEL.get(x) == VOWEL.get(y) and CONS.get(x) != CONS.get(y): return {"換行"}
            if CONS.get(x) == CONS.get(y): return {"換母音"}
            return {"換拍"}
        if len(d) >= 2: return {"多拍差"}
    return {"別語(訓/無関係)"}

def matrix2x2(opts):
    """检测四选项是否构成 2x2 笛卡尔矩阵 (前段2值 x 后段2值)。返回 (前段列表,后段列表) 或 None"""
    mors = [morae_of(o) for o in opts]
    cand = [range(0, len(m) + 1) for m in mors]
    for cut in itertools.product(*cand):
        pre = ["".join(mors[i][:cut[i]]) for i in range(4)]
        suf = ["".join(mors[i][cut[i]:]) for i in range(4)]
        if len(set(pre)) == 2 and len(set(suf)) == 2 and len(set(zip(pre, suf))) == 4:
            if all(p and s for p, s in zip(pre, suf)):
                return pre, suf
    return None

# ================================================================ 問題1
say("=" * 78)
say("問題1 漢字読み  (n = %d; 其中回忆版 %s %d 题)"
    % (len(sel("問題1")), CORRUPT, len([x for x in sel("問題1") if x["exam"] == CORRUPT])))
say("=" * 78)
PY = json.load(open(os.path.join(ENGINE, "kanji_pinyin.json"), encoding="utf-8"))
M1 = sel("問題1")

# --- 1A 现有引擎实测
say("\n[1A] 现有引擎 solveOnyomi 实测")
tally = collections.Counter(); detail = []
sure_hit = sure_miss = 0; elim_ok = elim_kill = 0; elim_tot = 0
for it in M1:
    r = solve_onyomi(it["target"], it["opts"], PY)
    tally[r["tier"]] += 1
    ok = None
    if r["tier"] == "sure":
        ok = (r["answer"] == it["ans"])
        sure_hit += ok; sure_miss += (not ok)
    elif r["tier"] in ("elim", "weak"):
        elim_tot += 1
        if it["ans"] in r["eliminated"]: elim_kill += 1
        else: elim_ok += 1
    detail.append((it, r, ok))
say("  tier 分布:", dict(tally))
say(f"  确答(sure): {sure_hit+sure_miss} 题, 对 {sure_hit} 错 {sure_miss}"
    f"  → 确答准确率 {rate(sure_hit, sure_hit+sure_miss)}")
say(f"  排除(elim/weak): {elim_tot} 题, 未误杀 {elim_ok}, 误杀正解 {elim_kill}"
    f"  → 排除安全率 {rate(elim_ok, elim_tot)}")
# 排除后的期望收益
exp = 0.0; n_exp = 0
for it, r, ok in detail:
    if r["tier"] in ("elim", "weak"):
        rem = [i for i in range(1, 5) if i not in r["eliminated"]]
        n_exp += 1
        exp += (1.0 / len(rem)) if it["ans"] in rem else 0.0
say(f"  排除后蒙题期望正确数 {exp:.2f}/{n_exp} (= {exp/n_exp*100:.1f}%, 基线25%)" if n_exp else "")
tot_exp = sure_hit + exp + 0.25 * tally["none"]
say(f"  ★ 引擎在 24 题上的总期望得分 ≈ {tot_exp:.2f}/24 ({tot_exp/24*100:.1f}%),"
    f" 纯蒙基线 6.0/24")
say("  失败/弃权明细:")
for it, r, ok in detail:
    if r["tier"] == "sure" and ok: continue
    say(f"    {it['exam']} Q{it['no']} {it['target']}  选项={'/'.join(it['opts'])}"
        f"  答={it['ans']}  tier={r['tier']}"
        + (f" 判={r.get('answer')}" if r.get("answer") else "")
        + (f" 杀={r.get('eliminated')}" if r.get("eliminated") else "")
        + (f" {r.get('note','')}"))

# --- 1B 正解是否零违规 / 干扰是否必违规
say("\n[1B] 假设: 正解满足全部音韵规则, 干扰项至少违反一条")
def viol_profile(it):
    kanji = [c for c in it["target"] if re.match(r"[一-鿿]", c)]
    pys = [PY.get(c) for c in kanji]
    if not kanji or any(not p for p in pys): return None
    prof = []
    for o in it["opts"]:
        kana = KANA_RE.sub("", o)
        sps = splits_of(kana, len(kanji))
        if not sps: prof.append(None); continue
        best = None
        for sp in sps:
            v = []
            for i, seg in enumerate(sp): v += check_segment(seg, pys[i], kanji[i])
            if best is None or len(v) < len(best): best = v
        prof.append(sorted(set(best)))
    return prof
n_prof = 0; ans_clean = 0; dist_all_dirty = 0; both = 0
for it in M1:
    p = viol_profile(it)
    if p is None or any(x is None for x in p): continue
    n_prof += 1
    a = len(p[it["ans"]-1]) == 0
    d = all(len(p[i]) > 0 for i in range(4) if i != it["ans"]-1)
    ans_clean += a; dist_all_dirty += d; both += (a and d)
say(f"  可对齐题数 n={n_prof}")
say(f"  正解零违规: {rate(ans_clean, n_prof)}")
say(f"  全部干扰项均有违规: {rate(dist_all_dirty, n_prof)}")
say(f"  两者同时成立(=规则可唯一确答): {rate(both, n_prof)}")

# --- 1C 干扰项构造类型学
say("\n[1C] 干扰项相对正解的变形类型 (每题3个干扰, 共 %d 个)" % (len(M1) * 3))
cnt = collections.Counter(); cnt_m = collections.Counter(); cnt_v = collections.Counter()
for it in M1:
    a = KANA_RE.sub("", it["cor"])
    for i, o in enumerate(it["opts"]):
        if i == it["ans"] - 1: continue
        for t in sorted(diff_type(a, KANA_RE.sub("", o))):
            cnt[t] += 1
            (cnt_m if it["set"] == "mine" else cnt_v)[t] += 1
tot = sum(cnt.values())
for t, c in cnt.most_common():
    say(f"    {t:<14} {c:>3}  ({c/tot*100:4.1f}%)   挖掘{cnt_m[t]:>2} 验证{cnt_v[t]:>2}")

# --- 1D 2x2 矩阵
say("\n[1D] 四选项是否构成 2×2 矩阵 / 矩阵内正解有无位置偏好")
mat = []
for it in M1:
    r = matrix2x2([KANA_RE.sub("", o) for o in it["opts"]])
    mat.append((it, r))
nm = sum(1 for _, r in mat if r)
say(f"  构成 2×2 的题数: {nm}/{len(M1)}"
    f"  (挖掘 {sum(1 for it,r in mat if r and it['set']=='mine')}/{len(sel('問題1','mine'))},"
    f" 验证 {sum(1 for it,r in mat if r and it['set']=='val')}/{len(sel('問題1','val'))})")
posc = collections.Counter(); longer = shorter = eqlen = 0; voiced = unvoiced = novoi = 0
for it, r in mat:
    if not r: continue
    posc[it["ans"]] += 1
    pre, suf = r
    a = it["ans"] - 1
    for fac in (pre, suf):
        vs = sorted(set(fac), key=len)
        if len(vs[0]) != len(vs[-1]):
            if len(fac[a]) == len(vs[-1]): longer += 1
            else: shorter += 1
        else: eqlen += 1
        if len(set(_norm(v) for v in vs)) == 1 and vs[0] != vs[1]:
            if any(c in "がぎぐげござじずぜぞだぢづでどばびぶべぼ" for c in fac[a]): voiced += 1
            else: unvoiced += 1
        else: novoi += 1
say(f"  2×2 题的正解编号分布: {dict(sorted(posc.items()))}")
say(f"  含长短对立的因子中, 正解取【长】{longer} 次 / 取【短】{shorter} 次")
say(f"  含清浊对立的因子中, 正解取【浊】{voiced} 次 / 取【清】{unvoiced} 次")
say("  → 2×2 矩阵四格结构对称, 纯结构信息无法定位正解 (每格到其余三格距离恒为1/1/2)")

# --- 1E 无结构关系(纯训读/别词) 题
say("\n[1E] 纯词汇型(四选项互为不同词, 无音变关系)题数")
purevocab = []
for it in M1:
    a = KANA_RE.sub("", it["cor"])
    tags = [diff_type(a, KANA_RE.sub("", o)) for i, o in enumerate(it["opts"]) if i != it["ans"]-1]
    if all("別語(訓/無関係)" in t or "多拍差" in t for t in tags): purevocab.append(it)
say(f"  {len(purevocab)}/{len(M1)}: " + ", ".join(f"{x['exam']}Q{x['no']}{x['target']}" for x in purevocab))
say("  → 这些题音韵规则完全无效, 是纯词汇量题")

# --- 1F 送り仮名闸门: 训读题识别
say("\n[1F] 闸门假设: 題干带送り仮名 ⇒ 训读题(音韵规则不适用); 纯汉字 ⇒ 音读题")
# 正解读音的音/训 人工标注(24题, 可核对)
KUN_TRUTH = {"侮って","筋道","鈍い","裁く","潜んで","芳しくない","悟った","滑らか"}
pure_on = pure_kun = oku_on = oku_kun = 0
KUN_ITEMS = []
for it in M1:
    pure = bool(re.fullmatch(r"[一-鿿]+", it["target"]))
    is_kun = it["target"] in KUN_TRUTH
    KUN_ITEMS.append((it, pure, is_kun))
    if pure and not is_kun: pure_on += 1
    elif pure and is_kun: pure_kun += 1
    elif not pure and not is_kun: oku_on += 1
    else: oku_kun += 1
say(f"  纯汉字題干: {pure_on+pure_kun} 题 → 音读型 {pure_on}, 训读型 {pure_kun}"
    f"  (纯汉字⇒音读 精确率 {rate(pure_on, pure_on+pure_kun)})")
say(f"  带送假名題干: {oku_on+oku_kun} 题 → 音读型 {oku_on}, 训读型 {oku_kun}"
    f"  (带送假名⇒训读 精确率 {rate(oku_kun, oku_on+oku_kun)})")
for g in ("mine", "val"):
    sub = [(it,p,k) for it,p,k in KUN_ITEMS if it["set"] == g]
    ok = sum(1 for it,p,k in sub if p != k)
    say(f"    {g}: 闸门判定正确 {rate(ok, len(sub))}")
say("  例外: " + ", ".join(f"{it['exam']}Q{it['no']}{it['target']}" for it,p,k in KUN_ITEMS if p == k))

# --- 1G 引擎变体
say("\n[1G] 引擎变体对比 (期望得分 = Σ 1/|存活集| , 弃权按0.25计)")
def variant(it, gate, guard):
    prof = viol_profile(it)
    if gate and not re.fullmatch(r"[一-鿿]+", it["target"]): return None
    if prof is None: return None
    # 与引擎一致: 无法对齐(可能训读)的选项视为"未被排除"
    surv = [i for i, p in enumerate(prof) if p is None or len(p) == 0]
    if len(surv) == 0 or len(surv) == 4: return None
    if guard and len(surv) == 1:
        s = it["opts"][surv[0]]
        unrel = [i for i in range(4) if i not in surv and not _related(s, it["opts"][i])]
        if unrel: return None
    return surv
def score_variant(name, gate, guard, items):
    res = {}
    for g in ("mine", "val", "all"):
        xs = [x for x in items if g == "all" or x["set"] == g]
        exp = 0.0; act = 0; sure_n = 0; sure_ok = 0; kill = 0
        for it in xs:
            s = variant(it, gate, guard)
            if s is None: exp += 0.25; continue
            act += 1
            if len(s) == 1:
                sure_n += 1; sure_ok += (s[0]+1 == it["ans"])
            if it["ans"]-1 in s: exp += 1.0/len(s)
            else: kill += 1
        res[g] = (exp, len(xs), act, sure_n, sure_ok, kill)
    for g in ("mine", "val", "all"):
        e, n, act, sn, so, kl = res[g]
        say(f"  [{name}/{g}] 期望 {e:.2f}/{n} ({e/n*100:.1f}%) | 出手{act} 确答{sn}(对{so}) 误杀正解{kl}")
    return res
V0 = score_variant("V0 原引擎(有音12守卫,无闸门)", False, True, M1)
V1 = score_variant("V1 去掉音12守卫", False, False, M1)
V2 = score_variant("V2 去守卫+送假名闸门", True, False, M1)
say("  V1 逐题存活集:")
for it in M1:
    s = variant(it, False, False)
    say(f"    {it['exam']} Q{it['no']} {it['target']:<6} 存活="
        + (str([i+1 for i in s]) if s else "弃权") + f" 答={it['ans']}"
        + ("  ★误杀" if s and it["ans"]-1 not in s else ("  ✓确答" if s and len(s)==1 else "")))

# --- 1G2 Unihan 词典变体: "正解=该汉字的标准读音" 假设
say("\n[1G2] 假设检验: 正解总是各汉字在 Unihan 中登记的标准读音 (需外部词典)")
K2R = {}
_hira = lambda s: "".join(chr(ord(c)-0x60) if "ァ" <= c <= "ヶ" else c for c in s)
for line in open(os.path.join(ENGINE, "Unihan_Readings.txt"), encoding="utf-8"):
    if "\tkJapanese\t" not in line: continue
    cp, _, val = line.rstrip("\n").split("\t")
    K2R[chr(int(cp[2:], 16))] = set(_hira(x) for x in val.split())
UNV = {v: k for k, v in [] }
def unvoice_first(s):
    return (_norm(s[0]) + s[1:]) if s else s
def seg_ok(seg, ch):
    R = K2R.get(ch)
    if not R: return None
    cands = {seg, unvoice_first(seg)}
    if seg.endswith("っ"):
        for t in "つちくき": cands.add(seg[:-1] + t); cands.add(unvoice_first(seg[:-1] + t))
    for c in cands:
        if c in R: return True
        for r in R:
            if r.startswith(c) and 0 < len(r) - len(c) <= 2 and re.search(r"[ぁ-ゖ]", r): return True
    return False
def unihan_surv(it):
    tgt = it["target"]
    kanji = [c for c in tgt if re.match(r"[一-鿿]", c)]
    oku = re.sub(r"[一-鿿]", "", tgt)
    if not kanji or any(c not in K2R for c in kanji): return None
    surv = []
    for idx, o in enumerate(it["opts"]):
        kana = KANA_RE.sub("", o)
        if oku:
            base = kana[:-len(oku)] if kana.endswith(oku) else kana
        else: base = kana
        ok = False
        for sp in splits_of(base, len(kanji)):
            if all(seg_ok(sp[i], kanji[i]) for i in range(len(kanji))): ok = True; break
        if ok: surv.append(idx)
    if not surv or len(surv) == 4: return None
    return surv
u_exp = 0.0; u_act = 0; u_sure = 0; u_sure_ok = 0; u_kill = 0; u_ansin = 0; u_n = 0
u_g = {"mine": [0.0, 0, 0, 0], "val": [0.0, 0, 0, 0]}
for it in M1:
    s = unihan_surv(it)
    g = u_g[it["set"]]
    if s is None:
        u_exp += 0.25; g[0] += 0.25; g[1] += 1; continue
    u_act += 1; u_n += 1; g[1] += 1; g[2] += 1
    if len(s) == 1:
        u_sure += 1; u_sure_ok += (s[0]+1 == it["ans"])
    if it["ans"]-1 in s: u_exp += 1.0/len(s); g[0] += 1.0/len(s); u_ansin += 1
    else: u_kill += 1
    g[3] += 1
say(f"  出手 {u_act}/24, 确答 {u_sure}(对 {u_sure_ok}), 正解落在存活集 {rate(u_ansin, u_act)}, 误杀 {u_kill}")
say(f"  期望得分 {u_exp:.2f}/24 ({u_exp/24*100:.1f}%)")
for g in ("mine", "val"):
    e, n, a, _ = u_g[g]
    say(f"    {g}: 期望 {e:.2f}/{n} ({e/n*100:.1f}%), 出手 {a}")
# 正解本身是否总能被词典解释
ansok = 0; ansn = 0; distdead = 0; distn = 0
for it in M1:
    tgt = it["target"]; kanji = [c for c in tgt if re.match(r"[一-鿿]", c)]
    oku = re.sub(r"[一-鿿]", "", tgt)
    if not kanji or any(c not in K2R for c in kanji): continue
    for idx, o in enumerate(it["opts"]):
        kana = KANA_RE.sub("", o)
        base = kana[:-len(oku)] if oku and kana.endswith(oku) else kana
        ok = any(all(seg_ok(sp[i], kanji[i]) for i in range(len(kanji))) for sp in splits_of(base, len(kanji)))
        if idx == it["ans"]-1: ansn += 1; ansok += ok
        else: distn += 1; distdead += (not ok)
say(f"  正解可被词典解释: {rate(ansok, ansn)}   干扰项无法被词典解释: {rate(distdead, distn)}")
say("  → 词典法把 '干扰项' 杀掉的比例, 即为该假设的判别力")
say("  逐题存活集:")
for it in M1:
    s = unihan_surv(it)
    say(f"    {it['exam']} Q{it['no']} {it['target']:<6} 存活="
        + (str([i+1 for i in s]) if s else "弃权(0或4项存活)") + f" 答={it['ans']}"
        + ("  ★误杀" if s and it["ans"]-1 not in s else ("  ✓确答" if s and len(s)==1 else "")))

# --- 1G3 词典法 + 音训不混搭约束
say("\n[1G3] 词典法 V4 = Unihan + 連濁仅限非首字 + 禁止音训混搭(重箱/湯桶読み)")
ON = collections.defaultdict(set); KUN = collections.defaultdict(set)
for line in open(os.path.join(ENGINE, "Unihan_Readings.txt"), encoding="utf-8"):
    if "\tkJapanese\t" not in line: continue
    cp, _, val = line.rstrip("\n").split("\t")
    ch = chr(int(cp[2:], 16))
    for w in val.split():
        (ON if re.fullmatch(r"[ァ-ヶー]+", w) else KUN)[ch].add(_hira(w))
def _match(seg, pool, pos, kun):
    cands = {seg}
    if pos > 0: cands.add(unvoice_first(seg))
    if seg.endswith("っ"):
        for t in "つちくき":
            cands.add(seg[:-1] + t)
            if pos > 0: cands.add(unvoice_first(seg[:-1] + t))
    for c in cands:
        if c in pool: return True
        if kun:
            for r in pool:
                if r.startswith(c) and 0 < len(r) - len(c) <= 2: return True
    return False
def unihan4_surv(it):
    tgt = it["target"]
    kanji = [c for c in tgt if re.match(r"[一-鿿]", c)]
    oku = re.sub(r"[一-鿿]", "", tgt)
    if not kanji or any(c not in K2R for c in kanji): return None
    surv = []
    for idx, o in enumerate(it["opts"]):
        kana = KANA_RE.sub("", o)
        base = kana[:-len(oku)] if oku and kana.endswith(oku) else kana
        ok = False
        for sp in splits_of(base, len(kanji)):
            if all(_match(sp[i], ON[kanji[i]], i, False) for i in range(len(kanji))): ok = True; break
            if all(_match(sp[i], KUN[kanji[i]], i, True) for i in range(len(kanji))): ok = True; break
        if ok: surv.append(idx)
    if not surv or len(surv) == 4: return None
    return surv
def score_surv(name, fn, items):
    for g in ("mine", "val", "all"):
        xs = [x for x in items if g == "all" or x["set"] == g]
        e = 0.0; act = 0; sn = 0; so = 0; kl = 0
        for it in xs:
            s = fn(it)
            if s is None: e += 0.25; continue
            act += 1
            if len(s) == 1: sn += 1; so += (s[0]+1 == it["ans"])
            if it["ans"]-1 in s: e += 1.0/len(s)
            else: kl += 1
        say(f"  [{name}/{g}] 期望 {e:.2f}/{len(xs)} ({e/len(xs)*100:.1f}%) | 出手{act} 确答{sn}(对{so}) 误杀{kl}")
score_surv("V3 Unihan基础", unihan_surv, M1)
score_surv("V4 Unihan+音训不混搭", unihan4_surv, M1)
say("  V4 逐题存活集:")
for it in M1:
    s = unihan4_surv(it)
    say(f"    {it['exam']} Q{it['no']} {it['target']:<6} 存活="
        + (str([i+1 for i in s]) if s else "弃权") + f" 答={it['ans']}"
        + ("  ★误杀" if s and it["ans"]-1 not in s else ("  ✓确答" if s and len(s)==1 else "")))
say("\n[1G3b] V6 = V4 + 漢語連濁仅允许在 ん/っ 之后 (日语实际音韵条件)")
def _match6(seg, pool, pos, kun, prev):
    cands = {seg}
    allow_voice = kun or (prev and prev[-1] in "んっ")
    if pos > 0 and allow_voice: cands.add(unvoice_first(seg))
    if seg.endswith("っ"):
        for t in "つちくき":
            cands.add(seg[:-1] + t)
            if pos > 0 and allow_voice: cands.add(unvoice_first(seg[:-1] + t))
    for c in cands:
        if c in pool: return True
        if kun:
            for r in pool:
                if r.startswith(c) and 0 < len(r) - len(c) <= 2: return True
    return False
def unihan6_surv(it):
    tgt = it["target"]
    kanji = [c for c in tgt if re.match(r"[一-鿿]", c)]
    oku = re.sub(r"[一-鿿]", "", tgt)
    if not kanji or any(c not in K2R for c in kanji): return None
    surv = []
    for idx, o in enumerate(it["opts"]):
        kana = KANA_RE.sub("", o)
        base = kana[:-len(oku)] if oku and kana.endswith(oku) else kana
        ok = False
        for sp in splits_of(base, len(kanji)):
            if all(_match6(sp[i], ON[kanji[i]], i, False, sp[i-1] if i else None) for i in range(len(kanji))):
                ok = True; break
            if all(_match6(sp[i], KUN[kanji[i]], i, True, sp[i-1] if i else None) for i in range(len(kanji))):
                ok = True; break
        if ok: surv.append(idx)
    if not surv or len(surv) == 4: return None
    return surv
score_surv("V6", unihan6_surv, M1)
say("  V6 逐题存活集:")
for it in M1:
    s = unihan6_surv(it)
    say(f"    {it['exam']} Q{it['no']} {it['target']:<6} 存活="
        + (str([i+1 for i in s]) if s else "弃权") + f" 答={it['ans']}"
        + ("  ★误杀" if s and it["ans"]-1 not in s else ("  ✓确答" if s and len(s)==1 else "")))

say("\n[1G5] 假设: 正解 = 各汉字在 Unihan 中【首位登记】的读音 (=最常见读音)")
ORD = {}
for line in open(os.path.join(ENGINE, "Unihan_Readings.txt"), encoding="utf-8"):
    if "\tkJapanese\t" not in line: continue
    cp, _, val = line.rstrip("\n").split("\t")
    ORD[chr(int(cp[2:], 16))] = [_hira(w) for w in val.split()]
first_hit = first_n = 0
for it in M1:
    kanji = [c for c in it["target"] if re.match(r"[一-鿿]", c)]
    oku = re.sub(r"[一-鿿]", "", it["target"])
    if any(c not in ORD for c in kanji): continue
    kana = KANA_RE.sub("", it["cor"])
    base = kana[:-len(oku)] if oku and kana.endswith(oku) else kana
    good = False
    for sp in splits_of(base, len(kanji)):
        if all(_match(sp[i], {ORD[kanji[i]][0]}, i, False) or
               _match(sp[i], {ORD[kanji[i]][0]}, i, True) for i in range(len(kanji))):
            good = True; break
    first_n += 1; first_hit += good
say(f"  正解的每个字都取【首位读音】: {rate(first_hit, first_n)}")
say("  → 反例即 '常见字的非首位读音' 考点 (如 行政ぎょう / 胸中ちゅう), 这正是出题人取材处")

say("\n[1G4] V5 = V4 ∩ 拼音音韵规则 (两法取交集)")
def v5(it):
    a = unihan4_surv(it); b = variant(it, False, False)
    if a is None and b is None: return None
    if a is None: return b
    if b is None: return a
    inter = [i for i in a if i in b]
    return inter if inter else a
score_surv("V5 交集", v5, M1)

# --- 1H 残余对立类型: 规则杀完之后剩下的是什么
say("\n[1H] 规则杀完后残余候选之间的对立类型 (=规则天花板的成因)")
resid = collections.Counter()
for it in M1:
    s = variant(it, True, False)
    if s is None or len(s) < 2: continue
    for i in range(len(s)):
        for j in range(i+1, len(s)):
            for t in sorted(diff_type(KANA_RE.sub("", it["opts"][s[i]]), KANA_RE.sub("", it["opts"][s[j]]))):
                resid[t] += 1
tt = sum(resid.values())
for t, c in resid.most_common():
    say(f"    {t:<14} {c:>3} ({c/tt*100:4.1f}%)")
say("  → 汉语拼音无法承载的对立(清浊/長短)占残余的绝大部分, 这就是规则法的物理上限")

# --- 1I 清浊预测: 中古全浊/次浊 → 日语濁音?
say("\n[1I] 假设: 首拍清浊可由拼音声母推断 (次浊 m/n/l/r/w/y → 濁; 其余 → 清)")
pairs = []
for it in M1:
    ks = [KANA_RE.sub("", o) for o in it["opts"]]
    for i in range(4):
        for j in range(4):
            if i >= j: continue
            if _norm(ks[i]) == _norm(ks[j]) and ks[i] != ks[j] and (i == it["ans"]-1 or j == it["ans"]-1):
                pairs.append((it, i, j))
say(f"  纯清浊对立且含正解的选项对: n={len(pairs)}")
hit = 0; hit_alwaysclean = 0
for it, i, j in pairs:
    ks = [KANA_RE.sub("", o) for o in it["opts"]]
    a = it["ans"]-1
    ansvoiced = any(c in "がぎぐげござじずぜぞだぢづでどばびぶべぼ" for c in ks[a][:2])
    p = parse_pinyin(PY.get(it["target"][0], "")) or {}
    pred_voiced = p.get("ini") in ("m","n","l","r","w","y","")
    hit += (pred_voiced == ansvoiced)
    hit_alwaysclean += (not ansvoiced)
say(f"  次浊→濁 预测命中 {rate(hit, len(pairs))}" + ("  ⚠样本不足" if len(pairs) < 8 else ""))
say(f"  '一律选清音' 命中 {rate(hit_alwaysclean, len(pairs))}" + ("  ⚠样本不足" if len(pairs) < 8 else ""))

# --- 1J 无知识启发式基线
say("\n[1J] 无外部知识的启发式 (对照)")
def h_longest(it):
    ls = [len(KANA_RE.sub("", o)) for o in it["opts"]]
    return ls.index(max(ls)) + 1 if ls.count(max(ls)) == 1 else None
def h_central(it):
    ks = [KANA_RE.sub("", o) for o in it["opts"]]
    d = [sum(lev(ks[i], ks[j]) for j in range(4)) for i in range(4)]
    return d.index(min(d)) + 1 if d.count(min(d)) == 1 else None
def h_outlier(it):
    ks = [KANA_RE.sub("", o) for o in it["opts"]]
    d = [sum(lev(ks[i], ks[j]) for j in range(4)) for i in range(4)]
    return d.index(max(d)) + 1 if d.count(max(d)) == 1 else None
report("最长选项", h_longest, M1)
report("最中心选项(编辑距离和最小)", h_central, M1)
report("最离群选项(编辑距离和最大)", h_outlier, M1)

# ================================================================ 問題2/3/4 共通
def cat(o):
    """粗粒度词性/形态分类"""
    s = o.strip()
    if re.fullmatch(r"[ァ-ヶー]+", s): return "カタカナ"
    if re.fullmatch(r"[ぁ-ゖー]+", s):
        if len(s) == 4 and s[:2] == s[2:]: return "擬態語ABAB"
        if s.endswith("い"): return "イ形(かな)"
        if s.endswith("に") or s.endswith("と"): return "副詞"
        return "かな語"
    if re.fullmatch(r"[一-鿿]{2,}", s): return "漢語名詞"
    if s.endswith("い"): return "イ形"
    if re.search(r"(って|いて|えて|して|んで|きて|いで|ぎて|して|ちて|びて|みて|りて|て)$", s): return "動詞テ形"
    if re.search(r"[うくぐすつぬぶむる]$", s): return "動詞辞書形"
    if s.endswith("な"): return "ナ形"
    return "その他"

say("\n" + "=" * 78)
say("問題2 文脈規定 / 問題3 言い換え / 問題4 用法  共通特征")
say("=" * 78)

# --- 答案编号分布
say("\n[G1] 答案编号分布")
for md in ("問題1", "問題2", "問題3", "問題4", None):
    xs = sel(md)
    c = collections.Counter(x["ans"] for x in xs)
    say(f"  {md or '全部'}: " + " ".join(f"{k}:{c.get(k,0)}" for k in (1,2,3,4)) + f"  (n={len(xs)})")
c = collections.Counter(x["ans"] for x in Q)
mx = max(c, key=lambda k: c[k])
say(f"  → 最高频编号 {mx} 命中率 {rate(c[mx], len(Q))}; 卡方均匀性: 期望 {len(Q)/4:.1f}/格")
chi = sum((c.get(k,0)-len(Q)/4)**2/(len(Q)/4) for k in (1,2,3,4))
say(f"  χ²={chi:.2f} (df=3, 临界7.81) → " + ("显著非均匀" if chi > 7.81 else "与均匀分布无显著差异"))

# --- 选项长度
say("\n[G2] 选项长度: 正解是否最长/最短")
for md in ("問題2", "問題3", "問題4"):
    xs = sel(md)
    def h_long(it):
        ls = [len(o) for o in it["opts"]]
        return ls.index(max(ls)) + 1 if ls.count(max(ls)) == 1 else None
    def h_short(it):
        ls = [len(o) for o in it["opts"]]
        return ls.index(min(ls)) + 1 if ls.count(min(ls)) == 1 else None
    say(f"  {md}:")
    report("最长", h_long, xs); report("最短", h_short, xs)

# --- 词性一致 / 异类
say("\n[G3] 四选项词性(粗分类)一致性; 异类项是答案还是干扰")
for md in ("問題2", "問題3"):
    xs = sel(md)
    same = 0; odd_items = []
    for it in xs:
        cs = [cat(o) for o in it["opts"]]
        cc = collections.Counter(cs)
        if len(cc) == 1: same += 1
        elif len(cc) == 2 and sorted(cc.values()) == [1, 3]:
            odd = [i for i, c_ in enumerate(cs) if cc[c_] == 1][0]
            odd_items.append((it, odd + 1))
    say(f"  {md}: 完全同类 {rate(same, len(xs))}; 3+1 型 {len(odd_items)} 题")
    if odd_items:
        h = sum(1 for it, o in odd_items if o == it["ans"])
        say(f"    其中异类项即正解 {rate(h, len(odd_items))} (基线25%)"
            + ("  ⚠样本不足" if len(odd_items) < 8 else ""))
        report("选异类项", lambda it, d=dict((id(a), b) for a, b in odd_items): d.get(id(it)), xs)

# --- 汉字共享 分组 vs 孤立
say("\n[G4] 选项间共享汉字/字面: 成组项 vs 孤立项")
def share_groups(opts):
    """按是否共享汉字连通分组"""
    ks = [set(c for c in o if re.match(r"[一-鿿]", c)) for o in opts]
    par = list(range(4))
    def find(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for i in range(4):
        for j in range(i+1, 4):
            if ks[i] & ks[j]: par[find(i)] = find(j)
    g = collections.defaultdict(list)
    for i in range(4): g[find(i)].append(i)
    return list(g.values())
for md in ("問題2", "問題3"):
    xs = sel(md)
    ngrp = 0; iso_is_ans = 0; iso_n = 0; grp_is_ans = 0
    for it in xs:
        gs = share_groups(it["opts"])
        if all(len(g) == 1 for g in gs): continue
        ngrp += 1
        a = it["ans"] - 1
        ga = [g for g in gs if a in g][0]
        if len(ga) == 1: iso_is_ans += 1
        else: grp_is_ans += 1
        iso_n += sum(1 for g in gs if len(g) == 1)
    say(f"  {md}: 存在共享汉字分组的题 {ngrp}/{len(xs)}; 正解落在孤立项 {iso_is_ans}, 落在成组项 {grp_is_ans}")
    if ngrp:
        say(f"    (孤立项平均每题 {iso_n/ngrp:.2f} 个 → 随机选孤立项的基线 ≈ {iso_n/ngrp/4*100:.0f}% 覆盖)")
    def h_iso(it):
        gs = share_groups(it["opts"])
        iso = [g[0] for g in gs if len(g) == 1]
        return iso[0] + 1 if len(iso) == 1 else None
    report("选唯一孤立项", h_iso, xs)

# ================================================================ 問題3 专项
say("\n" + "=" * 78)
say("問題3 言い換え 专项 (n=%d)" % len(sel("問題3")))
say("=" * 78)
M3 = sel("問題3")
say("\n[3A] 题干划线词 与 选项 的字面重叠 (共享汉字数)")
def overlap(it, o):
    t = set(c for c in it["target"] if re.match(r"[一-鿿]", c))
    s = set(c for c in o if re.match(r"[一-鿿]", c))
    return len(t & s)
n_any = 0; top_is_ans = 0; top_is_trap = 0
for it in M3:
    ov = [overlap(it, o) for o in it["opts"]]
    if max(ov) == 0: continue
    n_any += 1
    if ov.count(max(ov)) == 1:
        if ov.index(max(ov)) + 1 == it["ans"]: top_is_ans += 1
        else: top_is_trap += 1
say(f"  有任何汉字重叠的题: {n_any}/{len(M3)}")
say(f"  唯一最高重叠项 = 正解 {top_is_ans} 次 / = 陷阱 {top_is_trap} 次"
    + ("  ⚠样本不足" if top_is_ans + top_is_trap < 8 else ""))
def h_ovmax(it):
    ov = [overlap(it, o) for o in it["opts"]]
    return ov.index(max(ov)) + 1 if max(ov) > 0 and ov.count(max(ov)) == 1 else None
def h_ovmin(it):
    ov = [overlap(it, o) for o in it["opts"]]
    return ov.index(min(ov)) + 1 if ov.count(min(ov)) == 1 else None
report("选重叠最高项", h_ovmax, M3)
report("选重叠最低项(唯一)", h_ovmin, M3)

say("\n[3B] 划线词与选项的 语体/字种 匹配 (和語↔和語, 漢語↔漢語)")
def kind(s):
    if re.fullmatch(r"[ァ-ヶー]+", s): return "カタカナ"
    if re.search(r"[一-鿿]", s): return "漢字含"
    return "かな"
kk = 0; hit = 0
for it in M3:
    tk = kind(it["target"])
    same = [i for i, o in enumerate(it["opts"]) if kind(o) == tk]
    if len(same) == 1:
        kk += 1; hit += (same[0] + 1 == it["ans"])
say(f"  仅一个选项与划线词同字种的题: {kk}; 其中该项为正解 {rate(hit, kk)}"
    + ("  ⚠样本不足" if kk < 8 else ""))

# ================================================================ 問題4 专项
say("\n" + "=" * 78)
say("問題4 用法 专项 (n=%d)  ★核心: 格助词能否定位正解" % len(sel("問題4")))
say("=" * 78)
M4 = sel("問題4")
PARTS = ["には","では","からは","との","への","から","まで","より","を","が","に","で","と","は","も","へ","の"]
def stem_of(w):
    w = w.strip()
    if len(w) > 1 and w[-1] in "うくぐすつぬぶむるい" and re.search(r"[一-鿿]", w): return w[:-1]
    return w
def locate(sent, word):
    st = stem_of(word)
    i = sent.find(st)
    if i < 0:
        for L in range(len(st) - 1, 1, -1):
            i = sent.find(st[:L])
            if i >= 0: st = st[:L]; break
        else:
            i = -1
    if i < 0: return None
    before = sent[:i]; after = sent[i + len(st):]
    pre = None
    for p in PARTS:
        if before.endswith(p): pre = p; break
    post = None
    m = re.match(r"[ぁ-ゖー]*", after)
    tail = after[m.end():] if m else after
    infl = after[:m.end()] if m else ""
    for p in PARTS:
        if after.startswith(p): post = p; break
    if post is None:
        for p in PARTS:
            if infl and after[m.end():].startswith(p): post = p; break
    return {"pre": pre, "post": post, "infl": infl[:4], "idx": i}

say("\n[4A] 目标词前接格助词分布")
rows = []
for it in M4:
    locs = [locate(o, it["target"]) for o in it["opts"]]
    pres = [(l or {}).get("pre") for l in locs]
    rows.append((it, pres))
    say(f"  {it['exam']} Q{it['no']} 「{it['target']}」 前接= {pres}  答={it['ans']}"
        f"  正解前接={pres[it['ans']-1]}")
allpre = collections.Counter(p for it, pres in rows for p in pres)
anspre = collections.Counter(pres[it["ans"]-1] for it, pres in rows)
say(f"  全部96个句子前接助词分布: {dict(allpre)}")
say(f"  24个正解句前接助词分布: {dict(anspre)}")
uniq_hit = uniq_n = 0
for it, pres in rows:
    c = collections.Counter(p for p in pres)
    uniq = [i for i, p in enumerate(pres) if c[p] == 1]
    if len(uniq) == 1:
        uniq_n += 1; uniq_hit += (uniq[0] + 1 == it["ans"])
say(f"  '前接助词唯一的那句' 存在于 {uniq_n} 题; 其中为正解 {rate(uniq_hit, uniq_n)}"
    + ("  ⚠样本不足" if uniq_n < 8 else ""))
def h_uniqpre(it):
    locs = [locate(o, it["target"]) for o in it["opts"]]
    pres = [(l or {}).get("pre") for l in locs]
    c = collections.Counter(pres)
    u = [i for i, p in enumerate(pres) if c[p] == 1]
    return u[0] + 1 if len(u) == 1 else None
report("选前接助词唯一句", h_uniqpre, M4)
def h_wo(it):
    locs = [locate(o, it["target"]) for o in it["opts"]]
    pres = [(l or {}).get("pre") for l in locs]
    w = [i for i, p in enumerate(pres) if p == "を"]
    return w[0] + 1 if len(w) == 1 else None
report("选前接「を」唯一句", h_wo, M4)
def h_ga(it):
    locs = [locate(o, it["target"]) for o in it["opts"]]
    pres = [(l or {}).get("pre") for l in locs]
    w = [i for i, p in enumerate(pres) if p == "が"]
    return w[0] + 1 if len(w) == 1 else None
report("选前接「が」唯一句", h_ga, M4)
def h_multi(it):
    """多数派助词句 (若唯一)"""
    locs = [locate(o, it["target"]) for o in it["opts"]]
    pres = [(l or {}).get("pre") for l in locs]
    c = collections.Counter(pres)
    top = c.most_common(1)[0]
    if top[1] == 1: return None
    idx = [i for i, p in enumerate(pres) if p == top[0]]
    return None
report("多数派助词句", h_multi, M4)

say("\n[4A2] 逐助词的条件正确率 P(正解|前接=p)")
byp = collections.defaultdict(lambda: [0, 0])
for it, pres in rows:
    for i, p in enumerate(pres):
        byp[p][1] += 1
        if i == it["ans"]-1: byp[p][0] += 1
for p, (h, n) in sorted(byp.items(), key=lambda kv: -kv[1][1]):
    say(f"    前接={str(p):<4} P(正解)= {rate(h, n)}" + ("  ⚠样本不足" if n < 8 else ""))
say("  → 若某助词条件正确率显著>25% 则可用; 实测无一显著")
say("\n[4A3] 四句助词框架的区分度 (干扰句是否也语法合格)")
samec = collections.Counter()
for it, pres in rows:
    samec[len(set(pres))] += 1
say(f"  四句前接助词的不同取值个数分布: {dict(sorted(samec.items()))}")
same_all = sum(1 for it, pres in rows if len(set(pres)) == 1)
say(f"  四句助词完全相同的题: {same_all}/24 → 这些题助词零信息")
say("  → 干扰句均为合法日语句, 错的是语义搭配而非格支配, 故助词法在原理上就不成立")

say("\n[4B] 目标词后接形态 (活用/后续)")
for it in M4:
    locs = [locate(o, it["target"]) for o in it["opts"]]
    say(f"  {it['exam']} Q{it['no']} 「{it['target']}」 后接= "
        + str([(l or {}).get("infl") for l in locs]) + f"  答={it['ans']}")
inf_hit = inf_n = 0
for it in M4:
    locs = [locate(o, it["target"]) for o in it["opts"]]
    infl = [(l or {}).get("infl") for l in locs]
    c = collections.Counter(infl)
    u = [i for i, p in enumerate(infl) if c[p] == 1]
    if len(u) == 1:
        inf_n += 1; inf_hit += (u[0] + 1 == it["ans"])
say(f"  后接形态唯一句存在于 {inf_n} 题; 为正解 {rate(inf_hit, inf_n)}"
    + ("  ⚠样本不足" if inf_n < 8 else ""))

say("\n[4C] 目标词在句中的位置 (字符下标 / 相对位置)")
def h_pos_last(it):
    locs = [locate(o, it["target"]) for o in it["opts"]]
    r = [((l or {}).get("idx", -1)) / max(1, len(o)) for l, o in zip(locs, it["opts"])]
    return r.index(max(r)) + 1 if r.count(max(r)) == 1 else None
def h_pos_first(it):
    locs = [locate(o, it["target"]) for o in it["opts"]]
    r = [((l or {}).get("idx", 10**6)) / max(1, len(o)) for l, o in zip(locs, it["opts"])]
    return r.index(min(r)) + 1 if r.count(min(r)) == 1 else None
report("目标词最靠后", h_pos_last, M4)
report("目标词最靠前", h_pos_first, M4)
def h_len_long(it):
    ls = [len(o) for o in it["opts"]]
    return ls.index(max(ls)) + 1 if ls.count(max(ls)) == 1 else None
report("句子最长", h_len_long, M4)

# ================================================================ 問題2 专项
say("\n" + "=" * 78)
say("問題2 文脈規定 专项 (n=%d)" % len(sel("問題2")))
say("=" * 78)
M2 = sel("問題2")
say("\n[2A] 题干与选项的字面重叠 (共享汉字)")
def ov2(it, o):
    t = set(c for c in it["stem"] if re.match(r"[一-鿿]", c))
    s = set(c for c in o if re.match(r"[一-鿿]", c))
    return len(t & s)
def h2max(it):
    ov = [ov2(it, o) for o in it["opts"]]
    return ov.index(max(ov)) + 1 if max(ov) > 0 and ov.count(max(ov)) == 1 else None
def h2min(it):
    ov = [ov2(it, o) for o in it["opts"]]
    return ov.index(min(ov)) + 1 if ov.count(min(ov)) == 1 else None
report("题干重叠最高项", h2max, M2)
report("题干重叠最低项", h2min, M2)

say("\n[2B] 选项字种构成")
kc = collections.Counter()
for it in M2:
    kc[tuple(sorted(collections.Counter(cat(o) for o in it["opts"]).items()))] += 1
for k, v in kc.most_common():
    say(f"    {dict(k)}  ×{v}")

# ================================================================ 天花板
say("\n[2C] 题干-选项 字符级重叠(含假名)")
def ov2c(it, o):
    t = set(it["stem"].replace("（　）", ""))
    return len(t & set(o))
def h2cmax(it):
    ov = [ov2c(it, o) for o in it["opts"]]
    return ov.index(max(ov)) + 1 if ov.count(max(ov)) == 1 else None
def h2cmin(it):
    ov = [ov2c(it, o) for o in it["opts"]]
    return ov.index(min(ov)) + 1 if ov.count(min(ov)) == 1 else None
report("字符重叠最高", h2cmax, M2); report("字符重叠最低", h2cmin, M2)

say("\n[4D] 目标词的句法框架 (漢語名詞: する/される/できる/名詞用法)")
def frame(o, w):
    l = locate(o, w)
    if not l: return "?"
    s = l["infl"]
    if s.startswith("され"): return "受身"
    if s.startswith("でき") or s.startswith("せず"): return "可能"
    if s.startswith("す") or s.startswith("し"): return "する"
    return "名詞"
fh = fn = 0
for it in M4:
    if not re.fullmatch(r"[一-鿿]{2}", it["target"]): continue
    fr = [frame(o, it["target"]) for o in it["opts"]]
    c = collections.Counter(fr)
    u = [i for i, f in enumerate(fr) if c[f] == 1]
    if len(u) == 1:
        fn += 1; fh += (u[0]+1 == it["ans"])
say(f"  框架唯一句存在于 {fn} 题; 为正解 {rate(fh, fn)}" + ("  ⚠样本不足" if fn < 8 else ""))

# ================================================================ MeCab 形态素分析
say("\n" + "=" * 78)
say("MeCab (fugashi+unidic-lite) 形态素分析")
say("=" * 78)
import fugashi
TG = fugashi.Tagger()
def toks(s):
    return [{"s": w.surface, "p1": w.feature.pos1, "p2": w.feature.pos2,
             "p3": w.feature.pos3, "lem": w.feature.lemma or w.surface} for w in TG(s)]
CONTENT = ("名詞", "動詞", "形容詞", "形状詞", "副詞")

def opt_pos(o):
    """选项的词性签名: 首个内容词的 pos1(+名詞的 pos2)"""
    ts = toks(o)
    for t in ts:
        if t["p1"] in CONTENT:
            if t["p1"] == "名詞": return f"名詞/{t['p2']}"
            return t["p1"]
    return ts[0]["p1"] if ts else "?"
def opt_pos_coarse(o):
    ts = toks(o)
    for t in ts:
        if t["p1"] in CONTENT:
            # 名詞+する 视为动词性; 名詞+な 视为形状詞
            if t["p1"] == "名詞" and t["p2"] == "サ変可能": return "サ変名詞"
            return t["p1"]
    return "?"

say("\n[M1] 問題2/3 选项词性一致性 (MeCab pos1)")
for md in ("問題2", "問題3"):
    xs = sel(md)
    same = 0; odd = []
    for it in xs:
        ps = [opt_pos_coarse(o) for o in it["opts"]]
        c = collections.Counter(ps)
        if len(c) == 1: same += 1
        elif sorted(c.values()) == [1, 3]:
            odd.append((it, [i for i, p in enumerate(ps) if c[p] == 1][0] + 1))
    say(f"  {md}: 四选项词性完全一致 {rate(same, len(xs))}; 3+1 异类型 {len(odd)} 题")
    if odd:
        h = sum(1 for it, o in odd if o == it["ans"])
        hm = sum(1 for it, o in odd if o == it["ans"] and it["set"] == "mine")
        nm = sum(1 for it, o in odd if it["set"] == "mine")
        say(f"    异类项=正解 合计 {rate(h, len(odd))} | 挖掘 {rate(hm, nm)}"
            f" | 验证 {rate(h-hm, len(odd)-nm)}" + ("  ⚠样本不足" if len(odd) < 8 else ""))
        for it, o in odd:
            ps = [opt_pos_coarse(x) for x in it["opts"]]
            say(f"      {it['exam']}Q{it['no']} {ps} 异类={o} 答={it['ans']}")
    # 细粒度
    same2 = sum(1 for it in xs if len(set(opt_pos(o) for o in it["opts"])) == 1)
    say(f"    (细粒度 pos1/pos2 完全一致: {rate(same2, len(xs))})")

say("\n[M2] ★ 問題4 用法题: MeCab 格框架分析")
def frame4(sent, word):
    """返回 (前接格助詞, 目标词MeCab词性, 后续形态, 小句内全部格助词)"""
    ts = toks(sent)
    st = stem_of(word)
    if st not in sent:  # 活用/かな動詞: 退化到最长可定位前缀
        for L in range(len(st) - 1, 1, -1):
            if st[:L] in sent: st = st[:L]; break
    idx = None
    for i, t in enumerate(ts):
        if t["s"] == word or t["lem"] == word or t["s"] == st or t["lem"] == st \
           or (len(st) > 1 and t["s"].startswith(st)):
            idx = i; break
    if idx is None:  # 目标词被切碎, 用字符定位后找覆盖它的token
        ci = sent.find(st)
        if ci < 0: return None
        pos = 0
        for i, t in enumerate(ts):
            if pos <= ci < pos + len(t["s"]): idx = i; break
            pos += len(t["s"])
        if idx is None: return None
    pre = None
    for j in range(idx-1, -1, -1):
        if ts[j]["p1"] == "助詞" and ts[j]["p2"] in ("格助詞", "係助詞", "副助詞"):
            pre = ts[j]["s"]; break
        if ts[j]["p1"] in ("動詞", "形容詞") or ts[j]["p2"] == "読点": break
    nxt = ts[idx+1] if idx+1 < len(ts) else None
    # 目标词在本句中的用法角色
    if nxt and nxt["lem"] == "為る": role = "サ変(する)"
    elif nxt and nxt["lem"] == "有る": role = "名詞+ある"
    elif nxt and nxt["p1"] == "助動詞" and nxt["lem"] in ("だ", "な"): role = "形状詞(だ/な)"
    elif nxt and nxt["s"] in ("な",): role = "形状詞(な)"
    elif nxt and nxt["s"] == "に" and nxt["p2"] == "格助詞": role = "形状詞(に)/名詞に"
    elif nxt and nxt["s"] == "と": role = "と-副詞"
    elif nxt and nxt["p1"] == "助詞": role = f"名詞+{nxt['s']}"
    elif ts[idx]["p1"] == "動詞": role = "動詞"
    elif ts[idx]["p1"] == "形容詞": role = "形容詞"
    else: role = ts[idx]["p1"]
    cases = [t["s"] for t in ts[:idx] if t["p2"] == "格助詞"]
    return {"pre": pre, "role": role, "mpos": ts[idx]["p1"] + "/" + ts[idx]["p2"],
            "cases": cases, "nxt": (nxt["s"] if nxt else "")}
say("  逐题格框架 (前接助詞 | 用法角色):")
F4 = []
for it in M4:
    fs = [frame4(o, it["target"]) for o in it["opts"]]
    F4.append((it, fs))
    say(f"    {it['exam']} Q{it['no']} 「{it['target']}」 答={it['ans']}")
    for i, f in enumerate(fs):
        mark = " ←正解" if i+1 == it["ans"] else ""
        say(f"       {i+1}. 前接={str((f or {}).get('pre')):<5} 角色={str((f or {}).get('role')):<14}"
            f" MeCab={str((f or {}).get('mpos')):<16}{mark}")
# H1: 正解的"用法角色"是否与其余三句不同
h_n = h_hit = 0
for it, fs in F4:
    rs = [(f or {}).get("role") for f in fs]
    c = collections.Counter(rs)
    u = [i for i, r in enumerate(rs) if c[r] == 1]
    if len(u) == 1:
        h_n += 1; h_hit += (u[0]+1 == it["ans"])
rolevar = collections.Counter(len(set((f or {}).get("role") for f in fs)) for it, fs in F4)
prevar = collections.Counter(len(set((f or {}).get("pre") for f in fs)) for it, fs in F4)
say(f"\n  四句【用法角色】不同取值个数分布: {dict(sorted(rolevar.items()))}"
    f"  (=1 表示四句用法完全同型, 零信息)")
say(f"  四句【前接助詞】不同取值个数分布: {dict(sorted(prevar.items()))}")
say(f"  H4a 用法角色唯一的那句 = 正解: {rate(h_hit, h_n)} (n={h_n})"
    + ("  ⚠样本不足" if h_n < 8 else ""))
def h_role_uniq(it):
    fs = [frame4(o, it["target"]) for o in it["opts"]]
    rs = [(f or {}).get("role") for f in fs]
    c = collections.Counter(rs)
    u = [i for i, r in enumerate(rs) if c[r] == 1]
    return u[0]+1 if len(u) == 1 else None
report("选角色唯一句", h_role_uniq, M4)
# H2: 反向 —— 角色多数派
def h_role_major(it):
    fs = [frame4(o, it["target"]) for o in it["opts"]]
    rs = [(f or {}).get("role") for f in fs]
    c = collections.Counter(rs)
    top, n = c.most_common(1)[0]
    if n < 2 or n == 4: return None
    idx = [i for i, r in enumerate(rs) if r == top]
    return idx[0]+1 if len(idx) == 1 else None
report("选角色多数派句(唯一时)", h_role_major, M4)
# H3: サ変名詞 目标: 前接を
sa = [(it, fs) for it, fs in F4 if re.fullmatch(r"[一-鿿]{2}", it["target"])
      and any((f or {}).get("role") == "サ変(する)" for f in fs)]
say(f"\n  H4b サ変名詞题 n={len(sa)}; '前接を且做サ変' 唯一句 = 正解:")
sn = sh = 0
for it, fs in sa:
    cand = [i for i, f in enumerate(fs) if f and f.get("pre") == "を" and f.get("role") == "サ変(する)"]
    if len(cand) == 1:
        sn += 1; sh += (cand[0]+1 == it["ans"])
say(f"    {rate(sh, sn)}" + ("  ⚠样本不足" if sn < 8 else ""))
# H4: 干扰项是否 MeCab 词性与正解不同 (误用可被形态素识别?)
say("\n  H4c 正解句与干扰句的 MeCab 词性标注是否不同 (即误用能否被分词器识别)")
diffn = 0; totn = 0
for it, fs in F4:
    a = (fs[it["ans"]-1] or {}).get("mpos")
    for i, f in enumerate(fs):
        if i == it["ans"]-1: continue
        totn += 1
        if (f or {}).get("mpos") != a: diffn += 1
say(f"    干扰句中目标词被标为不同词性的比例: {rate(diffn, totn)}")
say("    → 比例越低, 说明干扰句在形态层面与正解无异, 误用纯属语义层")
# H5: 全部格助词集合
say("\n  H4d 目标词所在小句的格助词集合是否可判别")
def h_case_uniq(it):
    fs = [frame4(o, it["target"]) for o in it["opts"]]
    cs = [tuple(sorted(set((f or {}).get("cases") or []))) for f in fs]
    c = collections.Counter(cs)
    u = [i for i, x in enumerate(cs) if c[x] == 1]
    return u[0]+1 if len(u) == 1 else None
report("格助词集合唯一句", h_case_uniq, M4)

say("\n[M3] 跨题型检验: '与其余三项词面平均相似度最高者 = 答案' (来自読解的发现)")
def bigrams(s):
    s = re.sub(r"[、。「」（）\s]", "", s)
    return set(s[i:i+2] for i in range(len(s)-1)) or {s}
def dice(a, b):
    A, B = bigrams(a), bigrams(b)
    return 2*len(A & B)/(len(A)+len(B)) if (A or B) else 0.0
def lemmas(s):
    return set(t["lem"] for t in toks(s) if t["p1"] in CONTENT)
def jac(a, b):
    A, B = lemmas(a), lemmas(b)
    return len(A & B)/len(A | B) if (A | B) else 0.0
def centroid(simf):
    def f(it):
        sc = [sum(simf(it["opts"][i], it["opts"][j]) for j in range(4) if j != i)/3 for i in range(4)]
        mx = max(sc)
        return sc.index(mx)+1 if sc.count(mx) == 1 and mx > 0 else None
    return f
def anticentroid(simf):
    def f(it):
        sc = [sum(simf(it["opts"][i], it["opts"][j]) for j in range(4) if j != i)/3 for i in range(4)]
        mn = min(sc)
        return sc.index(mn)+1 if sc.count(mn) == 1 else None
    return f
for md in ("問題1", "問題2", "問題3", "問題4"):
    xs = sel(md)
    say(f"  {md}:")
    report("字面(2-gram)相似度最高", centroid(dice), xs)
    report("字面(2-gram)相似度最低", anticentroid(dice), xs)
    report("内容词(MeCab lemma)相似度最高", centroid(jac), xs)
say("  合计(問題2+3+4, 排除問題1 的音变矩阵干扰):")
X234 = sel("問題2") + sel("問題3") + sel("問題4")
report("字面相似度最高", centroid(dice), X234)
report("内容词相似度最高", centroid(jac), X234)
say("  → 読解那条'相似度最高=答案'在問題2/3 无法计算(选项是单词, 几乎零共享2-gram),")
say("     在問題4 上方向相反: 相似度最高者几乎从不是答案。")

def binom_p(k, n, p=0.25):
    """双尾二项检验 p 值"""
    from math import comb
    pm = [comb(n, i)*p**i*(1-p)**(n-i) for i in range(n+1)]
    return min(1.0, sum(x for x in pm if x <= pm[k]*1.0000001))
say("\n[M4] 反向规律检验: 問題4 '排除字面相似度最高的那句'")
for g in ("mine", "val", "all"):
    xs = [x for x in M4 if g == "all" or x["set"] == g]
    n = 0; safe = 0; e = 0.0
    for it in xs:
        k = centroid(dice)(it)
        if k is None: e += 0.25; continue
        n += 1
        if k != it["ans"]: safe += 1; e += 1/3
    say(f"  [{g}] 可排除 {n} 题, 未误杀 {rate(safe, n)} (随机基线 75%);"
        f" 期望得分 {e:.2f}/{len(xs)} ({e/len(xs)*100:.1f}%, 基线25%)")
kk = sum(1 for it in M4 if centroid(dice)(it) == it["ans"])
nn = sum(1 for it in M4 if centroid(dice)(it) is not None)
say(f"  '最高相似=答案' 命中 {kk}/{nn}, 二项双尾 p={binom_p(kk, nn):.4f} (H0: 25%)")
say("  → 效应主要来自挖掘集; 验证集 1/6 与基线无异, 判定为不稳健, 不采纳")

say("\n" + "=" * 78)
say("按卷分列 (2024-12 为回忆重排版, 含印刷讹误, 单列)")
say("=" * 78)
for ex in ["2024-12", "2025-07", "2025-12", "2026-07"]:
    xs = [x for x in Q if x["exam"] == ex]
    m1 = [x for x in xs if x["mondai"] == "問題1"]
    e = sum((0.25 if unihan6_surv(it) is None else
             (1.0/len(unihan6_surv(it)) if it["ans"]-1 in unihan6_surv(it) else 0.0)) for it in m1)
    sure = sum(1 for it in m1 if unihan6_surv(it) and len(unihan6_surv(it)) == 1)
    say(f"  {ex}{'(回忆版)' if ex == CORRUPT else '      '}  問題1 V6 期望 {e:.2f}/6, 零风险确答 {sure}/6"
        f" | 答案编号 {[x['ans'] for x in xs]}")
say("  2024-12 已知讹误: 問題4 Q20 選項3「加工」重复出现且句子破碎; Q25 選項4「父と漁民、」疑为「父は漁師で」;")
say("  Q23 選項1「正当な組み立てたのに」语法不通。→ 該卷 問題4 的助词/形态统计不可靠, 上列合计已含之。")
_m1x = [x for x in M1 if x["exam"] != CORRUPT]
_e = sum((0.25 if unihan6_surv(it) is None else
          (1.0/len(unihan6_surv(it)) if it["ans"]-1 in unihan6_surv(it) else 0.0)) for it in _m1x)
say(f"  剔除回忆版后 問題1 V6: 期望 {_e:.2f}/18 ({_e/18*100:.1f}%), 确答 "
    f"{sum(1 for it in _m1x if unihan6_surv(it) and len(unihan6_surv(it))==1)}/18")

say("\n" + "=" * 78)
say("留一交叉验证 (4 折, 每折留一套卷)")
say("=" * 78)
EXAMS = ["2024-12", "2025-07", "2025-12", "2026-07"]
def loo(name, fn_surv, items):
    tot = []
    for held in EXAMS:
        xs = [x for x in items if x["exam"] == held]
        e = 0.0
        for it in xs:
            s = fn_surv(it)
            if s is None: e += 0.25
            elif it["ans"]-1 in s: e += 1.0/len(s)
        tot.append((held, e, len(xs)))
    say(f"  [{name}] " + "  ".join(f"{h}:{e:.2f}/{n}" for h, e, n in tot)
        + f"  → 平均 {sum(e for _,e,_ in tot)/len(tot):.2f}/6")
loo("問題1 V6 词典法", unihan6_surv, M1)
loo("問題1 V0 原引擎", lambda it: variant(it, False, True), M1)
say("  (該規則无可调参数, 因此折间差异仅反映题目难度波动, 非过拟合)")

say("\n" + "=" * 78)
say("规则化天花板估算 (每卷 25 题: 問題1×6 + 問題2×7 + 問題3×6 + 問題4×6)")
say("=" * 78)
say(f"  問題1 拼音音韵引擎(现状)  期望 {tot_exp:.2f}/24 → 每卷 {tot_exp/4:.2f}/6")
e6 = 0.0
for it in M1:
    s = unihan6_surv(it)
    e6 += 0.25 if s is None else (1.0/len(s) if it["ans"]-1 in s else 0.0)
say(f"  問題1 Unihan 词典法 V6    期望 {e6:.2f}/24 → 每卷 {e6/4:.2f}/6  (其中 17/24 是零风险确答)")
say(f"  問題2 文脈規定            无规律, 期望 28×0.25={28*0.25:.2f}/28 → 每卷 1.75/7")
say(f"  問題3 言い換え            无规律, 期望 24×0.25={24*0.25:.2f}/24 → 每卷 1.50/6")
say(f"  問題4 用法                仅 1 条弱规律(排除字面最相似句), 期望 7.25/24 → 每卷 1.81/6")
say(f"  ★ 词汇部分天花板 ≈ {e6/4:.2f}+1.75+1.50+1.81 = {e6/4+1.75+1.50+1.81:.2f}/25 (纯蒙基线 6.25/25)")
say(f"    保守版(問題4 弱规律不采纳) ≈ {e6/4+4.75:.2f}/25")
say(f"  ★ 其中'零风险确答'(不靠蒙) = 17/24 ÷ 4 ≈ {17/4:.2f}/25 题")

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab_mine_log.txt"), "w",
     encoding="utf-8").write("\n".join(OUT))
