let R = {read:[0,0], lis:[0,0], sure:[0,0], elim:[0,0]};
for(const [name, text] of Object.entries(FILES)){
  const out = runExam(text);
  for(const {type, q, r} of out.results){
    if(r.tier==="lean" && q.answer){
      const k = (type==="reading") ? "read" : "lis";
      R[k][1]++; if(r.pick===q.answer) R[k][0]++;
    }
    if(r.tier==="sure" && q.answer){ R.sure[1]++; if(r.answer===q.answer) R.sure[0]++; }
    if(r.tier==="elim" && q.answer){ R.elim[1]++; if(!r.eliminated.includes(q.answer)) R.elim[0]++; }
  }
}
print("読解 读A 倾向: " + R.read[0] + "/" + R.read[1] + " = " + (100*R.read[0]/R.read[1]).toFixed(1) + "%  (挖掘基准46%, 基线25%)");
print("聴解 听A 倾向: " + R.lis[0] + "/" + R.lis[1] + " = " + (100*R.lis[0]/R.lis[1]).toFixed(1) + "%  (挖掘基准59%, 基线25%)");
print("确答: " + R.sure[0] + "/" + R.sure[1] + "   排除(正解存活): " + R.elim[0] + "/" + R.elim[1]);
