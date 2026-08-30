#!/bin/bash
# 批量跑转写卷,输出各科命中率
cd "$(dirname "$0")"
JSC=/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc
python3 - <<'EOF'
import glob, json, subprocess, os
for f in sorted(glob.glob('../converted/*.txt')):
    txt = open(f, encoding='utf-8').read()
    js = open('combined.js').read() + f"""
const TEXT = {json.dumps(txt)};
const out = runExam(TEXT);
const s = out.stats;
const wrong = out.results.filter(x=>x.r.tier==='sure'&&x.q.answer&&x.r.answer!==x.q.answer).map(x=>x.q.num);
const lost = out.results.filter(x=>x.r.tier==='elim'&&x.q.answer&&x.r.eliminated.includes(x.q.answer)).map(x=>x.q.num);
print(JSON.stringify({{s, wrong, lost}}));
""".replace('{{','{').replace('}}','}')
    open('_tmp_run.js','w').write(js)
    r = subprocess.run([os.environ.get('JSC','/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc'),'_tmp_run.js'],capture_output=True,text=True)
    name = os.path.basename(f)
    if r.returncode or not r.stdout.strip():
        print(f"{name}: ERROR {r.stderr.strip()[:200]}"); continue
    d = json.loads(r.stdout.strip().splitlines()[-1])
    s = d['s']
    print(f"{name}: 共{s['total']}题 | 确答{s['sure']}(判对{s['sureRight']}/{s['sureWithKey']}) | 排除≥2:{s['elim']}(正解存活{s['elimSaved']}/{s['elimWithKey']}) | 弱排{s['weak']} 无覆盖{s['none']}"
          + (f" | 确答判错题:{d['wrong']}" if d['wrong'] else "")
          + (f" | 排除误杀题:{d['lost']}" if d['lost'] else ""))
EOF
