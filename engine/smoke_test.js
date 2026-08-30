const sample = `#卷 TEST N1
#科 言語知識
#大題 問題1
#題 1
#干 事件の＜真相＞を究明する。
#选 1 しんそう
#选 2 しんしょう
#选 3 まそう
#选 4 まっそう
#答 1
#題 2
#干 彼は＜潔く＞罪を認めた。
#选 1 いさぎよく
#选 2 きよく
#选 3 こころよく
#选 4 いさましく
#答 1
#大題 問題5
#題 26
#干 大学を卒業して（　）、彼とは一度も会っていない。
#选 1 からというもの
#选 2 が早いか
#选 3 とあって
#选 4 ないまでも
#答 1
#題 27
#干 この規則は状況の（　）変更されることがある。
#选 1 いかんによって
#选 2 が最後
#选 3 んがために
#选 4 かたわら
#答 1
`;
const out = runExam(sample);
for(const {q, r} of out.results){
  print("題" + q.num + " tier=" + r.tier + " ans=" + (r.answer||"-") + " 正解=" + q.answer + " elim=" + JSON.stringify(r.eliminated||[]) + " note=" + (r.note||""));
}
print(JSON.stringify(out.stats));
