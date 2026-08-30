const D={};
for(const [name,text] of Object.entries(FILES)){
  const out=runExam(text);
  for(const {sec,dai,type,q,r} of out.results){
    const k=(/言語/.test(sec)?"言語知識":/読解/.test(sec)?"読解":"聴解")+"|"+dai+"|"+type;
    D[k]=D[k]||{n:0,sure:0,sureOK:0,lean:0,leanOK:0,elim:0,info:0,loc:0,exp:0,base:0};
    const S=D[k]; const no=q.options.length||4;
    S.n++; S.base+=1/no;
    if(r.tier==="sure"){S.sure++; if(q.answer&&r.answer===q.answer)S.sureOK++; S.exp+=1;}
    else if(r.tier==="lean"){S.lean++; if(q.answer&&r.pick===q.answer)S.leanOK++; S.exp+=(type==="reading"?0.431:0.552);}
    else if(r.tier==="elim"){S.elim++; S.exp+=1/Math.max(no-r.eliminated.length,1);}
    else if(r.tier==="info"){S.info++; S.exp+=1/no;}
    else S.exp+=1/no;
    if(r.loc&&r.loc.found) S.loc++;
  }
}
const rows=Object.entries(D).sort();
print("科目|大題|题型|题/卷|確答(对)|倾向(中)|排除|情報検索|锚点定位|期望/卷|纯蒙/卷");
for(const [k,S] of rows){
  const [sec,dai,type]=k.split("|");
  print([sec,dai,type,(S.n/4).toFixed(1),S.sure/4+"("+S.sureOK/4+")",(S.lean/4).toFixed(2)+"("+(S.leanOK/4).toFixed(2)+")",
    (S.elim/4).toFixed(2),(S.info/4).toFixed(1),(S.loc/4).toFixed(2),(S.exp/4).toFixed(2),(S.base/4).toFixed(2)].join(" | "));
}
