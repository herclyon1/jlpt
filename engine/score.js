const SEC = {};
for(const [name, text] of Object.entries(FILES)){
  const out = runExam(text);
  for(const {sec, type, q, r} of out.results){
    const k = /言語/.test(sec)?"言語知識":/読解/.test(sec)?"読解":"聴解";
    SEC[k] = SEC[k] || {n:0, exp:0, base:0, sure:0, lean:0, elimq:0, none:0};
    const S = SEC[k];
    const nopt = q.options.length || 4;
    S.n++; S.base += 1/nopt;
    if(r.tier === "sure"){ S.exp += 1; S.sure++; }
    else if(r.tier === "lean"){ S.exp += (type==="reading" ? 0.431 : 0.552); S.lean++; }
    else if(r.tier === "elim"){ const left = nopt - r.eliminated.length; S.exp += 1/Math.max(left,1); S.elimq++; }
    else if(r.tier === "weak"){ S.exp += 1/Math.max(nopt-1,1); S.none++; }
    else { S.exp += 1/nopt; S.none++; }
  }
}
let tn=0, te=0, tb=0;
for(const [k,S] of Object.entries(SEC)){
  const per = 4;
  print(k + ": " + (S.n/per).toFixed(0) + "题/卷 | 规则期望得分 " + (S.exp/per).toFixed(1)
    + " (纯蒙 " + (S.base/per).toFixed(1) + ") | 正确率 " + (100*S.exp/S.n).toFixed(1) + "%"
    + " | 确答" + (S.sure/per).toFixed(1) + " 倾向" + (S.lean/per).toFixed(1) + " 排除" + (S.elimq/per).toFixed(1));
  tn+=S.n; te+=S.exp; tb+=S.base;
}
print("——");
print("全卷: " + (tn/4).toFixed(0) + "题 | 规则期望 " + (te/4).toFixed(1) + "题 (纯蒙 " + (tb/4).toFixed(1) + ") | 原始正确率 " + (100*te/tn).toFixed(1) + "% (纯蒙 " + (100*tb/tn).toFixed(1) + "%)");
print("净增益: +" + ((te-tb)/4).toFixed(1) + " 题/卷");
