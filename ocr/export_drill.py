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

def misaligned_sessions():
    """哪些场次的音频切片是用串位的台本切出来的。

    切片脚本 segment_audio.py 用台本开头去 ASR 里对齐，而它读台本时踩的是同一个
    「块里嵌的 #文 属于下一题」的坑。凡是新旧两种读法给出的台本不一致的场次，
    切出来的 Q*.mp3 整体挪了一格——**音频和选项对不上，练了是负收益**。
    所以这里主动把这些场次的 audio 置空，只留文字练习，直到重新切片为止。
    """
    bad = set()
    for p in sorted(glob.glob(f'{ROOT}/converted/*_聴解.txt')):
        tag = os.path.basename(p)[:-len('_聴解.txt')]
        raw = open(p, encoding='utf-8').read()
        pas = {m.group(1): m.group(2) for m in
               re.finditer(r'^#文 (\S+)\n(.*?)^#文完', raw, re.M | re.S)}
        for b in re.split(r'^(?=#題 |#大題 )', raw, flags=re.M):
            mq = re.match(r'^#題 (\S+)(?:\s*[@＠]文\s*(\S+))?', b)
            if not mq:
                continue
            ref = (mq.group(2) or '').strip()
            m = re.search(r'^#文 \S+\n(.*?)^#文完', b, re.M | re.S)
            old_body = m.group(1) if m else pas.get(ref, '')
            new_body = pas[ref] if (ref and ref in pas) else (m.group(1) if m else '')
            if old_body != new_body:
                bad.add(tag)
                break
    return bad


def main():
    items = []
    skew = misaligned_sessions()
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
            # 块是按 #題/#大題 切的，#文 不是切点，所以「#題 1 @文 K4-1」这个块里
            # 装着的是**下一题**的 #文。2026-07 每道题都写了 @文，于是 11 道题的
            # 刺激句整体串位了一格（最后一题的刺激句还被复制成了两道）。
            # @文 是原卷里写明的指向，它在就以它为准，块里嵌的 #文 只当退路。
            ref = (mq.group(2) or '').strip()
            if ref and ref in pas:
                body = pas[ref]
            else:
                m = re.search(r'^#文 \S+\n(.*?)^#文完', b, re.M | re.S)
                body = m.group(1) if m else ''
            opts = [x.strip() for x in re.findall(r'^#选 \d (.*)$', b, re.M)]
            an = re.search(r'^#答 ([1-4])', b, re.M)
            if not (body and len(opts) == 3 and an):
                continue
            stim = clean(re.sub(r'\s', '', body))
            aud = f'{tag}/Q4-{mq.group(1)}.mp3'
            items.append({'id': f'{tag}-4-{mq.group(1)}', 'session': tag,
                          'no': mq.group(1), 'stimulus': stim, 'options': opts,
                          'answer': int(an.group(1)),
                          'audio': None if tag in skew else
                                   (aud if os.path.exists(f'{ROOT}/audio_clips/{aud}') else None)})
    json.dump(items, open(f'{ROOT}/export/drill_soku.json', 'w'), ensure_ascii=False, indent=1)
    L = sorted(len(x['stimulus']) for x in items)
    print(f'{len(items)} 题 → export/drill_soku.json')
    print(f'刺激句长度: 中位 {L[len(L)//2]} 字, 最长 {L[-1]}, 最短 {L[0]}')
    print(f'有音频 {sum(1 for x in items if x["audio"])}/{len(items)}')
    if skew:
        print(f'音频串位、已停用的场次: {sorted(skew)}（重新切片后自动恢复）')
    bad = [x["id"] for x in items if OPT.search(x['stimulus'])]
    print(f'仍含选项标记的: {bad if bad else "无"}')
    # 同一句刺激出现两次，几乎一定是台本对错了行——2026-07 那次串位就是这么露的马脚。
    # 真题里同一场次不会考两道一模一样的即時応答。
    seen = {}
    dup = []
    for x in items:
        k = (x['session'], x['stimulus'])
        if k in seen:
            dup.append(f"{seen[k]} 与 {x['id']}")
        seen[k] = x['id']
    print(f'同场次刺激句重复的: {dup if dup else "无"}')
    if dup:
        print('  ↑ 这是台本串位的典型症状，先查 converted/ 里那份再用')

if __name__ == '__main__':
    main()
