#!/usr/bin/env python3
"""导出 聴解問題4（即時応答）训练集 → export/drill_soku.json

刺激句要剥掉台本里念出来的三个选项（有的场次台本把选项也写进了 #文 块）。
"""
import re, os, sys, json, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 选项标记：1. / 1． / １． / 1、 等，且后面跟内容
OPT = re.compile(r'[1１][.．、]\s*\S')

def clean(stim):
    m = OPT.search(stim)
    if m:
        stim = stim[:m.start()]
    stim = re.sub(r'^\d+番[：:]?\s*', '', stim)
    stim = re.sub(r'^[男女MF][12]?[：:]\s*', '', stim)
    return stim.strip()

def main():
    items = []
    for p in sorted(glob.glob(f'{ROOT}/converted/*_聴解.txt')):
        tag = os.path.basename(p)[:-len('_聴解.txt')]
        raw = open(p, encoding='utf-8').read()
        pas = {m.group(1): m.group(2) for m in
               re.finditer(r'^#文 (\S+)\n(.*?)^#文完', raw, re.M | re.S)}
        dai = None
        for b in re.split(r'^(?=#題 |#大題 )', raw, flags=re.M):
            md = re.match(r'^#大題 問題(\d+)', b)
            if md:
                dai = int(md.group(1)); continue
            mq = re.match(r'^#題 (\S+)(?:\s*[@＠]文\s*(\S+))?', b)
            if not mq or dai != 4:
                continue
            m = re.search(r'^#文 \S+\n(.*?)^#文完', b, re.M | re.S)
            body = m.group(1) if m else pas.get(mq.group(2) or '', '')
            opts = [x.strip() for x in re.findall(r'^#选 \d (.*)$', b, re.M)]
            an = re.search(r'^#答 ([1-4])', b, re.M)
            if not (body and len(opts) == 3 and an):
                continue
            stim = clean(re.sub(r'\s', '', body))
            aud = f'{tag}/Q4-{mq.group(1)}.mp3'
            items.append({'id': f'{tag}-4-{mq.group(1)}', 'session': tag,
                          'no': mq.group(1), 'stimulus': stim, 'options': opts,
                          'answer': int(an.group(1)),
                          'audio': aud if os.path.exists(f'{ROOT}/audio_clips/{aud}') else None})
    json.dump(items, open(f'{ROOT}/export/drill_soku.json', 'w'), ensure_ascii=False, indent=1)
    L = sorted(len(x['stimulus']) for x in items)
    print(f'{len(items)} 题 → export/drill_soku.json')
    print(f'刺激句长度: 中位 {L[len(L)//2]} 字, 最长 {L[-1]}, 最短 {L[0]}')
    print(f'有音频 {sum(1 for x in items if x["audio"])}/{len(items)}')
    bad = [x["id"] for x in items if OPT.search(x['stimulus'])]
    print(f'仍含选项标记的: {bad if bad else "无"}')

if __name__ == '__main__':
    main()
