// 判题引擎: 解析标准卷面格式 → 按大题分派规则 → 三档裁决
// 依赖: rules_core.js (CARDS, solveOnyomi, ...), rules_grammar.js (GRAMMAR), YOMI(kanji→音训读音表)

// ===================== 卷面解析 =====================
function parseExam(text){
  const lines = text.split(/\r?\n/);
  const exam = { meta: {}, sections: [], passages: {} };
  let curDai = null, curQ = null, curPas = null, curSec = null;
  for(const raw of lines){
    const line = raw.replace(/\s+$/,"");
    if(curPas !== null){
      if(/^[#＃]文完/.test(line)){
        exam.passages[curPas.id] = curPas.text.join("\n").trim();
        // 聴解式顺序: #題 在前、#文 在后且未写 @文 → 自动挂到当前题
        if(curQ && !curQ.passage) curQ.passage = curPas.id;
        curPas = null;
      }
      else curPas.text.push(line);
      continue;
    }
    const m = line.match(/^[#＃](卷|科|大題|大题|題|题|干|选|選|答|文)\s*(.*)$/);
    if(!m){
      if(curQ && line.trim() && !line.startsWith("#")){ // 干的续行
        if(curQ._last === "stem") curQ.stem += "\n" + line;
        else if(curQ._last === "opt" && curQ.options.length) curQ.options[curQ.options.length-1] += line;
      }
      continue;
    }
    const [, tag, val] = m;
    if(tag === "卷") exam.meta.id = val.trim();
    else if(tag === "科"){ curSec = { name: val.trim(), dai: [] }; exam.sections.push(curSec); }
    else if(tag === "大題" || tag === "大题"){ curDai = { name: val.trim(), questions: [] }; (curSec||(curSec={name:"?",dai:[]},exam.sections.push(curSec),curSec)).dai.push(curDai); curQ=null; }
    else if(tag === "題" || tag === "题"){
      const qm = val.match(/^(\d+)\s*(?:[@＠]文\s*(\S+))?/);
      curQ = { num: qm?+qm[1]:0, passage: qm&&qm[2]?qm[2]:null, stem: "", options: [], answer: null, _last: null };
      if(!curDai){ curDai = { name:"?", questions: [] }; (curSec||exam.sections[0]).dai.push(curDai); }
      curDai.questions.push(curQ);
    }
    else if(tag === "干"){ if(curQ){ curQ.stem = val; curQ._last = "stem"; } }
    else if(tag === "选" || tag === "選"){
      if(curQ){ const om = val.match(/^(\d+)\s+([\s\S]*)$/); if(om) curQ.options[+om[1]-1] = om[2]; else curQ.options.push(val); curQ._last = "opt"; }
    }
    else if(tag === "答"){ if(curQ) curQ.answer = parseInt(val.trim()) || null; }
    else if(tag === "文"){ curPas = { id: val.trim(), text: [] }; }
  }
  if(curPas) exam.passages[curPas.id] = curPas.text.join("\n").trim();
  return exam;
}

// ===================== 接续判定器 =====================
// 判断空格前文字的形态类别集合
function tailClasses(before){
  const t = before.replace(/[「」『』（）\s]/g,"").replace(/＜|＞/g,"");
  const s = t.slice(-6);
  const out = new Set();
  if(!s) return out;
  const last = s[s.length-1];
  if(/て$|で$/.test(s)) out.add("Vte");
  if(/た$|だ$/.test(s)) { out.add("Vta"); out.add("PL"); }
  if(/ない$/.test(s)) { out.add("Vnai"); out.add("PL"); }
  if(/(なかっ|だっ|かっ)た$/.test(s)) out.add("PL");
  if(/[うくぐすつぬぶむる]$/.test(s)) { out.add("Vd"); out.add("PL"); }
  if(/(よう|おう|ろう|とう|こう|そう|もう|ぼう|のう|ごう)$/.test(s) && /[おうこそとのぼもろよご]う$/.test(s)) out.add("Vvol");
  if(/[えけせてねべめれげ]ば$/.test(s)) out.add("Vba");
  if(/い$/.test(s) && !/ない$/.test(s)) { out.add("A"); out.add("PL"); out.add("Vm"); }
  if(/[き|し|ち|に|ひ|み|り|ぎ|じ|び|え|け|せ|め|べ|れ]$/.test(last)) out.add("Vm");
  if(/[一-鿿ァ-ヶa-zA-Z0-9０-９]$/.test(last)) { out.add("N"); out.add("Na"); }
  if(/の$/.test(s)) out.add("N");
  if(/[0-9０-９一二三四五六七八九十百千万]([人円個台年月日回度分秒歳冊枚本匹]|つ)$/.test(s)) out.add("Q");
  if(/こと$|もの$|ところ$/.test(s)) out.add("N");
  return out;
}
// 在文法表中找选项对应句型
// before: 空格前文字 —— 支持"空格前尾字+选项"合成句型（如 て + からというもの）
function matchGrammar(opt, before){
  const o = opt.trim();
  const tail = (before||"").replace(/[「」『』（）\s]/g,"");
  let best = null;
  for(const [pats, prev, mean] of GRAMMAR){
    for(const p of pats){
      const core = p.replace(/～/g,"");
      for(let k = 0; k <= 2 && k <= tail.length; k++){
        const cand = (k ? tail.slice(-k) : "") + o;
        const cand2 = cand.replace(/^[はがもにをと]/,"");
        if(cand.startsWith(core) || cand2.startsWith(core)){
          if(!best || core.length > best.len) best = { pat: p, prev, mean, len: core.length, consumed: k };
        }
      }
    }
  }
  return best;
}
// 敬语题模块(敬1/敬2)
const KEIGO_RE = /(まいり|いたし|いらっしゃ|なさ|おり|申し|伺い|いただ|くださ|おっしゃ|さしあげ)/;
function solveKeigo(stem, options, before){
  const hits = options.filter(o=>KEIGO_RE.test(o)).length;
  if(hits < 3) return null;
  const elim = new Set(); const rules = new Set();
  const teForm = /[てで]\s*$/.test(before.trim());
  options.forEach((o,i)=>{
    if(teForm && /^(いたし|なさ|申し|伺い)/.test(o.trim())){ elim.add(i+1); rules.add("敬1"); }
  });
  const selfActor = /(私ども|わたくし|弊社|当社|我が社|私|僕)(は|が|も|、)/.test(stem);
  const otherActor = /(お客様|先生|皆様|部長|課長|社長|様)(は|が|も)/.test(stem);
  if(selfActor && !otherActor){
    options.forEach((o,i)=>{ if(/(いらっしゃ|なさ|おっしゃ)/.test(o)){ elim.add(i+1); rules.add("敬2"); } });
  } else if(otherActor && !selfActor){
    options.forEach((o,i)=>{ if(/(まいり|いたし|申し|伺い|おり)/.test(o) && !/て(おり|まいり)/.test(o)){ elim.add(i+1); rules.add("敬2"); } });
  }
  if(elim.size === 0) return null;
  const alive = options.map((_,i)=>i+1).filter(n=>!elim.has(n));
  if(alive.length === 1) return { tier:"sure", answer: alive[0], rules:[...rules], eliminated:[...elim] };
  if(elim.size >= 2) return { tier:"elim", eliminated:[...elim], rules:[...rules] };
  return { tier:"weak", eliminated:[...elim], rules:[...rules] };
}
function solveGrammar(stem, options){
  const bm = stem.match(/^([\s\S]*?)（\s*）([\s\S]*)$/);
  if(!bm) return { tier: "none", note: "未找到（　）空格" };
  const before = bm[1];
  const keigo = solveKeigo(stem, options, before);
  if(keigo) return keigo;
  const classes = tailClasses(before);
  if(classes.size === 0) return { tier: "none", note: "前接形态无法判定" };
  const details = options.map(opt => {
    const g = matchGrammar(opt, before);
    if(!g) return { known: false };
    if(g.prev.includes("any")) return { known: true, ok: true, g };
    // 句型吞掉了空格前的k个字时，接续检查用吞掉前的形态
    const cls = g.consumed ? tailClasses(before.slice(0, before.length - g.consumed)) : classes;
    const ok = g.prev.some(c => cls.has(c)) ||
      (g.consumed > 0);  // 吞字匹配成功 = 表面形已含接续证据
    return { known: true, ok, g };
  });
  const elim = details.map((d,i)=>d.known && !d.ok ? i+1 : 0).filter(Boolean);
  const alive = details.map((d,i)=>!(d.known && !d.ok) ? i+1 : 0).filter(Boolean);
  const allKnown = details.every(d=>d.known);
  const rules = ["接1"];
  if(alive.length === 1 && allKnown) return { tier: "sure", answer: alive[0], rules: ["接1","接2"], details, classes:[...classes] };
  if(elim.length >= 2) return { tier: "elim", eliminated: elim, rules, details, classes:[...classes] };
  if(elim.length === 1) return { tier: "weak", eliminated: elim, rules, details, classes:[...classes] };
  return { tier: "none", details, classes:[...classes] };
}

// ===================== 大题分派 =====================
// 大題名 → 题型 (N1 标准结构)
function daiType(secName, daiName){
  const n = (daiName.match(/\d+/)||[0])[0]*1;
  if(/言語知識/.test(secName)){
    return ({1:"kanji",2:"context",3:"paraphrase",4:"usage",5:"grammar",6:"star",7:"cloze"})[n] || "unknown";
  }
  if(/読解/.test(secName)) return "reading";
  if(/聴解/.test(secName)) return ({1:"task",2:"point",3:"gist",4:"quick",5:"integrated"})[n] || "listening";
  return "unknown";
}

function solveQuestion(q, type, exam, dai13){
  const passage = q.passage ? exam.passages[q.passage] : null;
  switch(type){
    case "kanji": {
      const wm = q.stem.match(/＜(.+?)＞/);
      if(!wm) return { tier: "none", note: "题干无＜＞考察点" };
      // V6 自带送り仮名闸门, 音读/训读统一处理, 不再预先弃权
      return solveOnyomi(wm[1], q.options);
    }
    case "grammar": return solveGrammar(q.stem, q.options);
    case "star": return { tier: "none", note: "组句题(★)暂无规则覆盖" };
    case "cloze": {
      if(!passage) return { tier:"none", note:"缺文章块" };
      const r = solveGrammar_cloze(q, passage);
      return r;
    }
    case "context": case "paraphrase": case "usage":
      return { tier: "none", note: "词汇题——规则化边界外,靠你" };
    case "reading": {
      const loc = anchorLocate(q.stem, passage, 2);
      // 問題13 情報検索: 走约束抽取而非词汇统计
      if(/問題?\s*13/.test(dai13 || "")){
        const ir = infoRetrieval(q.stem, passage);
        if(ir) return { tier:"info", ...ir };
      }

      const ce = claimElim(q.options, passage);
      const lean = readingLean(q.options);
      const rules = [], elim = [];
      if(ce.elim){ elim.push(ce.elim); rules.push("读B"); }
      if(lean && lean.pick && !elim.includes(lean.pick)){
        rules.push("读A");
        return { tier:"lean", pick: lean.pick, hit:"46%", eliminated: elim, rules,
                 claims: ce.claims, scores: lean.scores, loc };
      }
      if(elim.length) return { tier:"weak", eliminated: elim, rules, claims: ce.claims, loc };
      return { tier:"none", claims: ce.claims, loc };
    }
    case "quick":
      return { tier:"none", note:"即時応答:33题实测无任何可挖规律,纯靠听懂" };
    case "task": case "point": {
      if(!passage) return { tier:"none", note:"缺听力原文" };
      const lean = listeningLean(q.options, passage);
      if(lean && lean.pick)
        return { tier:"lean", pick: lean.pick, hit:"59%", rules:["听A"], scores: lean.scores };
      return { tier:"none", scores: lean ? lean.scores : null };
    }
    case "gist": case "integrated": case "listening":
      return { tier:"none", note:"该题型实测无可挖规律" };
    default: return { tier: "none" };
  }
}
// 文章语法(cloze): 空位【n】前文接续判定
function solveGrammar_cloze(q, passage){
  const mark = "【" + q.num + "】";
  const idx = passage.indexOf(mark);
  if(idx < 0) return { tier:"none", note:"文中未找到"+mark };
  const before = passage.slice(Math.max(0, idx-30), idx);
  const classes = tailClasses(before);
  // 守卫: 前接形态判定不出来时必须弃权 —— 空证据不能当作排除依据(2021-07 題43 误杀教训)
  if(classes.size === 0) return { tier:"none", note:"前接形态无法判定,弃权" };
  // 接続詞填空(そこで/むしろ/とはいえ…)不受前接约束, 接续逻辑不适用
  if(q.options.every(o => /^(確かに|むしろ|とはいえ|とすると|そこで|しかし|だが|つまり|例えば|また|さらに|ただし|なぜなら|こうして|一方|あるいは|ちなみに|すなわち|それとも|したがって|そのため)/.test(o.trim())))
    return { tier:"none", note:"接続詞选择题,接续规则不适用" };
  const details = q.options.map(opt => {
    const g = matchGrammar(opt, before);
    if(!g) return { known:false };
    if(g.prev.includes("any")) return { known:true, ok:true, g };
    return { known:true, ok: g.prev.some(c=>classes.has(c)) || g.consumed > 0, g };
  });
  const elim = details.map((d,i)=>d.known&&!d.ok?i+1:0).filter(Boolean);
  const alive = details.map((d,i)=>!(d.known&&!d.ok)?i+1:0).filter(Boolean);
  if(alive.length===1 && details.every(d=>d.known)) return { tier:"sure", answer:alive[0], rules:["接1","接2"], details };
  if(elim.length>=2) return { tier:"elim", eliminated:elim, rules:["接1"], details };
  if(elim.length===1) return { tier:"weak", eliminated:elim, rules:["接1"], details };
  return { tier:"none", details };
}

// ===================== 全卷运行 + 统计 =====================
function runExam(text){
  const exam = parseExam(text);
  const results = [];
  for(const sec of exam.sections){
    for(const dai of sec.dai){
      const type = daiType(sec.name, dai.name);
      // 質問1/質問2 共用台本: 无 #文 的题继承同大題前一题的
      let prevPas = null;
      for(const q of dai.questions){ if(!q.passage && prevPas && /聴解/.test(sec.name)) q.passage = prevPas; prevPas = q.passage; }
      for(const q of dai.questions){
        const r = solveQuestion(q, type, exam, dai.name);
        results.push({ sec: sec.name, dai: dai.name, type, q, r });
      }
    }
  }
  const stats = { total: results.length, sure:0, sureRight:0, sureWithKey:0, lean:0, leanRight:0, leanWithKey:0,
                  elim:0, elimSaved:0, elimWithKey:0, info:0, weak:0, none:0 };
  for(const {q, r} of results){
    if(r.tier === "sure"){ stats.sure++;
      if(q.answer){ stats.sureWithKey++; if(r.answer === q.answer) stats.sureRight++; } }
    else if(r.tier === "lean"){ stats.lean++;
      if(q.answer){ stats.leanWithKey++; if(r.pick === q.answer) stats.leanRight++; } }
    else if(r.tier === "elim"){ stats.elim++;
      if(q.answer){ stats.elimWithKey++; if(!r.eliminated.includes(q.answer)) stats.elimSaved++; } }
    else if(r.tier === "info") stats.info = (stats.info||0)+1;
    else if(r.tier === "weak") stats.weak++;
    else stats.none++;
  }
  return { exam, results, stats };
}

if (typeof module !== 'undefined') module.exports = { parseExam, runExam, solveGrammar, tailClasses, matchGrammar };
