const tally = {};
let totQ = 0, totSure = 0, totSureOK = 0, totElim = 0, totElimOK = 0, totWeak = 0;
const bySec = {};
for(const [name, text] of Object.entries(FILES)){
  const out = runExam(text);
  const sec = name.includes('言語') ? '言語知識' : name.includes('読解') ? '読解' : '聴解';
  bySec[sec] = bySec[sec] || {q:0,sure:0,sureOK:0,elim:0,elimOK:0,weak:0};
  for(const {q, r} of out.results){
    totQ++; bySec[sec].q++;
    (r.rules||[]).forEach(id => tally[id] = (tally[id]||0)+1);
    if(r.tier==='sure'){ totSure++; bySec[sec].sure++; if(q.answer && r.answer===q.answer){totSureOK++; bySec[sec].sureOK++;} }
    else if(r.tier==='elim'){ totElim++; bySec[sec].elim++; if(q.answer && !r.eliminated.includes(q.answer)){totElimOK++; bySec[sec].elimOK++;} }
    else if(r.tier==='weak'){ totWeak++; bySec[sec].weak++; }
  }
}
print("总计: " + totQ + "题 确答" + totSure + "(对" + totSureOK + ") 排除" + totElim + "(存活" + totElimOK + ") 弱排" + totWeak);
for(const [s,v] of Object.entries(bySec)) print(s + ": " + v.q + "题 确答" + v.sure + "(对" + v.sureOK + ") 排除" + v.elim + "(存活" + v.elimOK + ") 弱排" + v.weak);
print("规则触发次数: " + JSON.stringify(tally));
