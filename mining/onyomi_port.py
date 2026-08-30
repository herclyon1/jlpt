# -*- coding: utf-8 -*-
"""Faithful Python port of engine/rules_core.js solveOnyomi (no node available on this box).
Ported 1:1 including quirks; verified line-by-line against rules_core.js."""
import re, json, os

PY_INITIALS = ["zh","ch","sh","b","p","m","f","d","t","n","l","g","k","h","j","q","x","r","z","c","s","y","w"]
TONE_MARKS = {"ā":("a",1),"á":("a",2),"ǎ":("a",3),"à":("a",4),"ē":("e",1),"é":("e",2),"ě":("e",3),"è":("e",4),
  "ī":("i",1),"í":("i",2),"ǐ":("i",3),"ì":("i",4),"ō":("o",1),"ó":("o",2),"ǒ":("o",3),"ò":("o",4),
  "ū":("u",1),"ú":("u",2),"ǔ":("u",3),"ù":("u",4),"ǖ":("ü",1),"ǘ":("ü",2),"ǚ":("ü",3),"ǜ":("ü",4),"ü":("ü",0),
  "ń":("n",2),"ň":("n",3),"ǹ":("n",4),"ḿ":("m",2)}

def parse_pinyin(py):
    if not py: return None
    tone = 0; s = ""
    for ch in py:
        if ch in TONE_MARKS:
            s += TONE_MARKS[ch][0]
            if TONE_MARKS[ch][1]: tone = TONE_MARKS[ch][1]
        else: s += ch
    s = s.lower()
    ini = ""
    for p in PY_INITIALS:
        if s.startswith(p): ini = p; break
    fin = s[len(ini):]
    return {"ini": ini, "fin": fin, "tone": tone, "raw": s}

def is_rusheng(p):
    if not p: return None
    ini, fin, tone, raw = p["ini"], p["fin"], p["tone"], p["raw"]
    if fin.endswith("n") or fin.endswith("ng"): return False
    if fin == "üe" or fin == "ue":
        if raw in ("jue","que","xue","yue","lüe","nüe") or fin == "üe":
            return True
    if ini in ("b","d","g","j","zh","z") and tone == 2: return True
    if ini in ("d","t","n","l","z","c","s") and fin == "e": return True
    if ini in ("b","p","m","d","t","n","l") and fin == "ie" and raw != "die1": return True
    if raw in ("fa","fo"): return True
    if ini in ("k","zh","ch","sh","r") and fin == "uo": return True
    return None

INI_ROWS = {
  "b":["H","M"], "p":["H"], "f":["H","M"], "m":["M","H"], "w":["W","M","K"],
  "d":["T","N"], "t":["T"], "n":["N","T","R"], "l":["R"], "r":["S","N"],
  "g":["K"], "k":["K"], "h":["K","W"], "j":["K","S"], "q":["K","S"], "x":["K","S"], "y":["Y","W","K"],
  "zh":["T","S"], "ch":["T","S"], "sh":["S"], "z":["S"], "c":["S"], "s":["S"], "":["W","Y","K"]}
_ROWS = {"K":"かきくけこがぎぐげごきゃきゅきょぎゃぎゅぎょ","S":"さしすせそざじずぜぞしゃしゅしょじゃじゅじょ",
  "T":"たちつてとだぢづでど","N":"なにぬねの",
  "H":"はひふへほばびぶべぼぱぴぷぺぽひゃひゅひょびゃびゅびょぴゃぴゅぴょ",
  "M":"まみむめも","R":"らりるれろりゃりゅりょ","Y":"やゆよ","W":"わをあいうえお"}
KANA_ROW = {}
for _r,_k in _ROWS.items():
    for _c in _k:
        if _c not in KANA_ROW: KANA_ROW[_c] = _r
SMALL_YOON = "ゃゅょ"

def morae_of(kana):
    m = []
    for ch in kana:
        if ch in SMALL_YOON and m: m[-1] += ch
        else: m.append(ch)
    return m

def splits_of(kana, n):
    morae = morae_of(kana)
    res = []
    def rec(start, parts):
        if len(parts) == n:
            if start == len(morae): res.append(list(parts))
            return
        remain = len(morae) - start; need = n - len(parts)
        for ln in range(1, 4):
            if start + ln > len(morae): break
            if remain - ln < (need-1)*1 or remain - ln > (need-1)*3: continue
            parts.append("".join(morae[start:start+ln]))
            rec(start+ln, parts); parts.pop()
    rec(0, [])
    return res

DAKU = "がぎぐげござじずぜぞだぢづでどばびぶべぼ"

def check_segment(seg, py, ch):
    bad = []
    p = parse_pinyin(py)
    if not p: return bad
    last = seg[-1]
    nasal_n = p["fin"].endswith("n") and not p["fin"].endswith("ng")
    nasal_ng = p["fin"].endswith("ng")
    rd = is_rusheng(p)
    if nasal_n and last != "ん": bad.append("音1")
    if nasal_ng:
        if not ((last == "う" or last == "い") and len(seg) >= 2): bad.append("音1")
    if (not nasal_n) and (not nasal_ng) and last == "ん": bad.append("音1")
    if rd is True:
        if last not in "くきつちっう" or len(seg) == 1: bad.append("音2")
    if rd is False and not nasal_n and not nasal_ng:
        if last == "っ": bad.append("音4")
    first = seg[0]
    row = KANA_ROW.get(first)
    allowed = INI_ROWS.get(p["ini"])
    if row and allowed and row not in allowed: bad.append("音5")
    if p["fin"] in ("a","o","e","i","u","ü","v") and rd is not True:
        if len(seg) >= 2 and last in ("う","ー"): bad.append("音7")
    if p["ini"] in ("p","t","k","q","c","ch"):
        if first in DAKU: bad.append("音8")
    if p["tone"] in (1,3) and p["ini"] in ("b","p","f","d","t","g","k","h","j","q","x","z","c","s","zh","ch","sh"):
        if first in DAKU: bad.append("音9")
    if rd is False and "っ" in seg: bad.append("音4")
    if p["fin"] == "iao" and not seg.endswith("ょう"): bad.append("音10")
    if (p["fin"] in ("iu","iou") or (p["fin"] == "ou" and p["ini"] == "y")) and not (seg.endswith("ゅう") or seg.endswith("ゆう")):
        bad.append("音10")
    if p["fin"] == "ao" and (ch or "") != "保" and not (last == "う" and len(seg) >= 2): bad.append("音11")
    has_yoon = any(c in SMALL_YOON for c in seg)
    raw, fin = p["raw"], p["fin"]
    has_medial = bool(re.match(r"^[jqx]", raw)) or bool(re.search(r"i[aou]", fin)) or fin.startswith("ü") \
                 or (bool(re.search(r"u[ae]", fin)) and bool(re.match(r"^[jqxy]", raw)))
    if has_yoon and not has_medial and not re.match(r"^[zcs]h?", raw) and not re.match(r"^r", raw) and "i" not in fin:
        bad.append("音6")
    return bad

DAK_NORM = {"が":"か","ぎ":"き","ぐ":"く","げ":"け","ご":"こ","ざ":"さ","じ":"し","ず":"す","ぜ":"せ","ぞ":"そ",
  "だ":"た","ぢ":"ち","づ":"つ","で":"て","ど":"と","ば":"は","び":"ひ","ぶ":"ふ","べ":"へ","ぼ":"ほ",
  "ぱ":"は","ぴ":"ひ","ぷ":"ふ","ぺ":"へ","ぽ":"ほ"}

def _norm(s): return "".join(DAK_NORM.get(c, c) for c in s)
KANA_RE = re.compile(r"[^ぁ-ゖー]")
def _related(a, b):
    x = _norm(KANA_RE.sub("", a)); y = _norm(KANA_RE.sub("", b))
    if len(x) != len(y): return False
    return sum(1 for i in range(len(x)) if x[i] != y[i]) <= 1

def solve_onyomi(word, options, pinyin_map):
    kanji = [c for c in word if re.match(r"[一-鿿]", c)]
    if not kanji: return {"tier":"none","note":"无汉字"}
    pys = [pinyin_map.get(c) for c in kanji]
    if any(not p for p in pys): return {"tier":"none","note":"缺拼音数据"}
    verdicts = []
    for opt in options:
        kana = KANA_RE.sub("", opt)
        sps = splits_of(kana, len(kanji))
        if not sps:
            verdicts.append({"ok": None, "viol": []}); continue
        best = None
        for sp in sps:
            viol = []
            for i, seg in enumerate(sp): viol += check_segment(seg, pys[i], kanji[i])
            if best is None or len(viol) < len(best): best = viol
            if len(best) == 0: break
        verdicts.append({"ok": len(best) == 0, "viol": sorted(set(best))})
    ok_idx = [i for i,v in enumerate(verdicts) if v["ok"] is not False]
    elim  = [i for i,v in enumerate(verdicts) if v["ok"] is False]
    all_rules = sorted({r for v in verdicts for r in v["viol"]})
    if len(ok_idx) == 1 and len(elim) == len(options)-1:
        surv = options[ok_idx[0]]
        unrel = [i for i in elim if not _related(surv, options[i])]
        if not unrel:
            return {"tier":"sure","answer":ok_idx[0]+1,"rules":all_rules,"verdicts":verdicts}
        rel_elim = [i+1 for i in elim if _related(surv, options[i])]
        if len(rel_elim) >= 2:
            return {"tier":"elim","eliminated":rel_elim,"rules":["音12"],"note":"音训风险:只杀同源变体","verdicts":verdicts}
        return {"tier":"none","note":"音训对立,规则不判(音12)","verdicts":verdicts}
    if len(elim) >= 2:
        return {"tier":"elim","eliminated":[i+1 for i in elim],"rules":all_rules,"verdicts":verdicts}
    if len(elim) == 1:
        return {"tier":"weak","eliminated":[i+1 for i in elim],"rules":all_rules,"verdicts":verdicts}
    return {"tier":"none","verdicts":verdicts}
