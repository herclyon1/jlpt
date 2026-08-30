// 核心规则模块：音读判别 / 読解 / 聴解
// 每条规则有 id，引擎触发时引用；CARDS 里是同一条规则给人背的中文版本。

// ===================== 规则卡片（你要背的就是这些） =====================
const CARDS = {
  // ===== 実証で残ったルールのみ。括号内是 4 套真题(384题)上的实测数据 =====
  // --- 漢字読み(問題1): 这三条合起来 4 卷确答18题全对 ---
  "音A": "送り仮名闸门：纯汉字词→读音读；带送り仮名→读训读（实测 16/17 与 7/7）",
  "音B": "禁止音训混搭：一个词里要么全音读要么全训读，重箱/湯桶読み在正解里从不出现——混搭选项直接划掉",
  "音C": "漢語連濁限制：音读复合词第二字开头浊化（か→が、は→ば）只允许在前一拍是 ん 或 っ 时。例：三階さんがい○",
  // --- 文法(問題5/6/7) ---
  "文A": "呼応固定搭配：しか→必接ない、どうりで→必接はず/わけ、決して/少しも→必接ない、まるで→ようだ。看到前项直接锁后项（触发2次,2次全对,但样本少）",
  "文B": "敬语两条：①て形后只能接 まいる/おる/いらっしゃる/くださる/いただく，ていたす・てなさる 不成立 ②自己方→谦让、对方→尊敬",
  "文C": "接续排除只值 5%：40 题里 38 题四选项接续全部合法。别指望它定案，它只在敬语题和极少数题上有用——N1 文法考的是语义搭配不是形态",
  // --- 読解(問題8-13) ---
  "读A": "★主力规则：选与其他三个选项用词最像的那个（干扰项由正解改写而来，正解因此与多项共享词面）。实测 46%，基线 25%",
  "读B": "与末段主张句内容词重叠最低的那个选项可以划掉（正解率仅 8.2%）",
  // --- 聴解(問題1/2 only) ---
  "听A": "★問題1/2：正解是「换了说法的那个」，跟录音重复词最多的是陷阱。选与台本用词重叠最少者，实测 59.1%（p=0.0007）。注意只对問題1/2 有效",
  "听B": "問題1/2 不要选录音里最后才提到的那个（実測 問題2 上 0/16）",
};

// ===================== 音读模块 (V6: Unihan音训表, 拼音路线已废弃)
const SMALL_YOON = "ゃゅょ";
// 把一个假名串按音拍粗分段, 返回段数组的所有 n 分法
function splitsOf(kana, n){
  // 音拍化: 小写拗音并入前拍
  const morae = [];
  for(const ch of kana){
    if(SMALL_YOON.includes(ch) && morae.length) morae[morae.length-1] += ch;
    else morae.push(ch);
  }
  const res = [];
  (function rec(start, parts){
    if(parts.length === n){ if(start === morae.length) res.push(parts.slice()); return; }
    const remain = morae.length - start, need = n - parts.length;
    for(let len = 1; len <= 6 && start+len <= morae.length; len++){
      if(remain - len < (need-1)*1 || remain - len > (need-1)*6) continue;
      parts.push(morae.slice(start, start+len).join(""));
      rec(start+len, parts); parts.pop();
    }
  })(0, []);
  return res;
}
// 音读题主判定 V6: Unihan音训表 + 三条硬约束(送り仮名闸门/禁止音训混搭/漢語連濁限ん・っ后)
// 实测(4套真题24题): 期望20.08/24=83.7%, 零风险确答17题全对, 误杀0
const DAKU_BASE = {"が":"か","ぎ":"き","ぐ":"く","げ":"け","ご":"こ","ざ":"さ","じ":"し","ず":"す","ぜ":"せ","ぞ":"そ",
  "だ":"た","ぢ":"ち","づ":"つ","で":"て","ど":"と","ば":"は","び":"ひ","ぶ":"ふ","べ":"へ","ぼ":"ほ",
  "ぱ":"は","ぴ":"ひ","ぷ":"ふ","ぺ":"へ","ぽ":"ほ"};
function unvoiceFirst(s){ return s ? (DAKU_BASE[s[0]] || s[0]) + s.slice(1) : s; }
// 单字段匹配: seg 是否为 ch 在 pool(音读集/训读集) 中的合法读音
function segMatch(seg, pool, pos, isKun, prev){
  if(!pool || !pool.length) return false;
  const cands = new Set([seg]);
  const allowVoice = isKun || (prev && "んっ".includes(prev[prev.length-1]));
  if(pos > 0 && allowVoice) cands.add(unvoiceFirst(seg));
  if(seg.endsWith("っ")){
    for(const t of "つちくき"){
      cands.add(seg.slice(0,-1) + t);
      if(pos > 0 && allowVoice) cands.add(unvoiceFirst(seg.slice(0,-1) + t));
    }
  }
  for(const c of cands){
    if(pool.includes(c)) return true;
    if(isKun) for(const r of pool){ if(r.startsWith(c) && r.length - c.length > 0 && r.length - c.length <= 2) return true; }
  }
  return false;
}
function solveOnyomi(word, options, _unusedPinyin){
  const kanji = [...word].filter(c => /[一-鿿]/.test(c));
  if(kanji.length === 0) return { tier: "none", note: "无汉字" };
  if(kanji.some(c => !YOMI[c])) return { tier: "none", note: "读音表缺字" };
  const oku = word.replace(/[一-鿿]/g, "");   // 送り仮名
  const surv = [], detail = [];
  options.forEach((opt, idx) => {
    const kana = opt.replace(/[^ぁ-ゖー]/g, "");
    const base = (oku && kana.endsWith(oku)) ? kana.slice(0, kana.length - oku.length) : kana;
    let ok = false, how = "";
    for(const sp of splitsOf(base, kanji.length)){
      // 禁止音训混搭: 要么全音读, 要么全训读
      if(sp.every((seg,i) => segMatch(seg, YOMI[kanji[i]][0], i, false, i?sp[i-1]:null))){ ok = true; how = "音読み"; break; }
      if(sp.every((seg,i) => segMatch(seg, YOMI[kanji[i]][1], i, true,  i?sp[i-1]:null))){ ok = true; how = "訓読み"; break; }
    }
    if(ok) surv.push(idx);
    detail.push({ opt, ok, how });
  });
  if(surv.length === 0) return { tier: "none", note: "读音表覆盖不足(全灭)", detail };
  if(surv.length === options.length) return { tier: "none", note: "四项读音均合法,靠词汇量", detail };
  const elim = options.map((_,i)=>i+1).filter(n => !surv.includes(n-1));
  if(surv.length === 1) return { tier: "sure", answer: surv[0]+1, rules: ["音A","音B","音C"], eliminated: elim, detail };
  if(elim.length >= 2) return { tier: "elim", eliminated: elim, rules: ["音A","音B","音C"], detail };
  return { tier: "weak", eliminated: elim, rules: ["音A","音B","音C"], detail };
}

// ===================== 词面重叠 (JS端近似内容词: 汉字串+片假名串) =====================
function contentTokens(str){
  if(!str) return new Set();
  const out = new Set();
  for(const run of (str.match(/[一-鿿]+/g) || [])){
    if(run.length === 1) out.add(run);
    else for(let i = 0; i + 2 <= run.length; i++) out.add(run.slice(i, i+2));
  }
  for(const run of (str.match(/[ァ-ヶー]{2,}/g) || [])) out.add(run);
  return out;
}
function simOverlap(a, b){
  if(!a.size || !b.size) return 0;
  let hit = 0; a.forEach(t => { if(b.has(t)) hit++; });
  return hit / Math.min(a.size, b.size);
}

// ===================== 読解模块 (実証版) =====================
// 读A: 与其他三项词面平均相似度最高者 = 答案 (实测全88题46.0%, 挖掘47.9%/验证40.0%, 基线25%)
function readingLean(options){
  const toks = options.map(contentTokens);
  const avg = toks.map((t,i) => {
    let s = 0, n = 0;
    toks.forEach((u,j) => { if(i!==j){ s += simOverlap(t,u); n++; } });
    return n ? s/n : 0;
  });
  const max = Math.max(...avg);
  if(max <= 0) return null;
  const top = avg.map((v,i)=>v===max?i+1:0).filter(Boolean);
  return top.length === 1 ? { pick: top[0], scores: avg.map(v=>+v.toFixed(3)) } : { pick: null, scores: avg.map(v=>+v.toFixed(3)) };
}
// 读B: 与末段主张句内容词重叠最低者可排除 (实测正解率8.2%, 挖掘8.3%/验证7.7%)
function findClaims(passage){
  if(!passage) return [];
  const paras = passage.split(/\n\s*\n/).filter(s=>s.trim());
  const lastP = paras[paras.length-1] || "";
  return lastP.split(/(?<=[。？！])/).filter(s =>
    /(のだ|のである|べきだ|べきではない|のではないか|のではないだろうか|と思う|と考える|必要がある|てはならない|なければならない)[。」]?\s*$/.test(s.trim()));
}
function claimElim(options, passage){
  const claims = findClaims(passage);
  if(!claims.length) return { elim: null, claims };
  const ct = contentTokens(claims.join(""));
  if(ct.size < 3) return { elim: null, claims };
  const sc = options.map(o => simOverlap(contentTokens(o), ct));
  const min = Math.min(...sc);
  const low = sc.map((v,i)=>v===min?i+1:0).filter(Boolean);
  return { elim: low.length === 1 ? low[0] : null, claims, scores: sc.map(v=>+v.toFixed(3)) };
}

// ===================== 聴解模块 (実証版) =====================
// 听A: 問題1/2 正解是"换了说法的那个"——与台本词面重叠最少者 (实测13/22=59.1%, p=0.0007)
function listeningLean(options, script){
  if(!script) return null;
  const st = contentTokens(script);
  if(st.size < 5) return null;
  const sc = options.map(o => simOverlap(contentTokens(o), st));
  const min = Math.min(...sc);
  const low = sc.map((v,i)=>v===min?i+1:0).filter(Boolean);
  return { pick: low.length === 1 ? low[0] : null, scores: sc.map(v=>+v.toFixed(3)) };
}

// ===================== 情報検索(問題13) 约束抽取器 =====================
// 该题型不考日语理解, 考约束计算。引擎不硬解, 而是把约束和数字摊开给你套。
const CONSTRAINT_RE = /(上限|まで|までに|以内|以上|以下|未満|超える|必ず|ただし|除く|のみ|無料|割引|不要|当日|事前|先着|限り)/;
function infoRetrieval(stem, passage){
  if(!passage) return null;
  const lines = passage.split(/\n|(?<=。)/).map(x=>x.trim()).filter(x=>x);
  const hits = lines.filter(l => CONSTRAINT_RE.test(l) && /[0-9０-９]/.test(l) || /(必ず|ただし|除く|のみ|不要)/.test(l));
  if(hits.length < 2) return null;
  const nums = (stem.match(/[0-9０-９,，]+\s*(円|回|泊|日|時|人|点|kg|個|枚|名|分|月)/g) || []);
  const facts = [];
  if(/初めて|初回/.test(stem)) facts.push("首次利用");
  if(/日帰り/.test(stem)) facts.push("当日往返→无住宿费");
  const mem = stem.match(/(普通会員|特別会員|一般|学生|市内|市外|在住)/g);
  if(mem) facts.push("身份:" + [...new Set(mem)].join("/"));
  const dates = (stem.match(/[0-9０-９]{1,2}月[0-9０-９]{1,2}日/g) || []);
  return { constraints: hits.slice(0, 14), nums, facts, dates, rules: ["检1","检2","检3","检4"] };
}

// ===================== 锚点定位器 (你的提案: 只读相关那几句) =====================
// 実測: 有锚点题(下線部/引用符)占読解 24%, 定位是字符串检索≈100%可靠,
//       证据在锚点±2句内占 58%, 阅读量 17.6句 → 5句
function anchorLocate(stem, passage, win){
  if(!passage) return null;
  const am = stem.match(/＜(.+?)＞/) || stem.match(/「(.+?)」/);
  if(!am) return null;
  const key = am[1];
  const sents = [];
  for(const para of passage.split("\n")){
    const p = para.trim();
    if(!p || p.startsWith("（注")) continue;
    for(const x of p.split(/(?<=[。？！])/)) if(x.trim()) sents.push(x.trim());
  }
  if(sents.length < 4) return null;
  let idx = sents.findIndex(x => x.includes(key));
  if(idx < 0){
    const core = key.replace(/[はがをにでとのもや、。]/g,"").slice(0,6);
    if(core) idx = sents.findIndex(x => x.includes(core));
  }
  if(idx < 0) return { key, found:false };
  const w = win || 2;
  const lo = Math.max(0, idx-w), hi = Math.min(sents.length-1, idx+w);
  return { key, found:true, idx, anchor: sents[idx],
           window: sents.slice(lo, hi+1), lo, hi, total: sents.length,
           why: /なぜ|理由|どうして/.test(stem) ? "なぜ型→依据常在锚点【后】1-2句(なぜなら/からだ/のである)"
              : /どういうこと|とは/.test(stem) ? "換言型→依据常在锚点【前后】紧邻句"
              : "指示型→先解开锚点里的指示词(それ/この), 所指在锚点【前】最近一句" };
}
