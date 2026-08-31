#!/usr/bin/env python3
"""导出 読解 练习集 → export/drill_read.json

每题附上 読B 的判定（按"共享汉字个数"给四个选项排名，人可执行的粗版度量），
供练习器对照：你选了什么 / 読B 会划掉哪个 / 正解是什么。
"""
import re, os, sys, json, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def kanji_share(opts):
    """人版度量：每个选项与其他三个共享多少个不同的汉字"""
    S = [set(''.join(re.findall(r'[一-鿿々]+', o))) for o in opts]
    return [sum(len(S[i] & S[j]) for j in range(len(S)) if i != j) for i in range(len(S))]

def main():
    items = []
    for p in sorted(glob.glob(f'{ROOT}/converted/*_読解.txt')):
        tag = os.path.basename(p)[:-len('_読解.txt')]
        raw = open(p, encoding='utf-8').read()
        pas = {m.group(1): m.group(2).strip() for m in
               re.finditer(r'^#文 (\S+)\n(.*?)^#文完', raw, re.M | re.S)}
        dai = None
        for b in re.split(r'^(?=#題 |#大題 )', raw, flags=re.M):
            md = re.match(r'^#大題 問題(\d+)', b)
            if md:
                dai = int(md.group(1)); continue
            mq = re.match(r'^#題 (\S+)(?:\s*[@＠]文\s*(\S+))?', b)
            if not mq:
                continue
            stem = re.search(r'^#干 (.*)$', b, re.M)
            opts = [x.strip() for x in re.findall(r'^#选 \d (.*)$', b, re.M)]
            an = re.search(r'^#答 ([1-4])', b, re.M)
            if len(opts) != 4 or not an:
                continue
            sc = kanji_share(opts)
            order = sorted(range(4), key=lambda i: -sc[i])
            items.append({
                'id': f'{tag}-{dai}-{mq.group(1)}',
                'session': tag, 'dai': dai, 'no': mq.group(1),
                'passage': '\n'.join(pas.get(k.strip(), '')
                                     for k in re.split(r'[,，、]', mq.group(2) or '')
                                     if k.strip()) or None,
                'stem': stem.group(1) if stem else None,
                'options': opts,
                'answer': int(an.group(1)),
                'share': sc,                    # 每个选项的共享汉字数
                'centroid': order[0] + 1,       # 読B 的"重心"（共享最多）
                'orphan': order[3] + 1,         # 読B 要划掉的"孤儿"（共享最少）
                'margin': sorted(sc)[1] - sorted(sc)[0],   # 孤儿比第二少几个汉字
            })
    json.dump(items, open(f'{ROOT}/export/drill_read.json', 'w'), ensure_ascii=False, indent=1)
    n = len(items)
    kill = sum(1 for x in items if x['orphan'] == x['answer'])
    hit = sum(1 for x in items if x['centroid'] == x['answer'])
    print(f'{n} 题 → export/drill_read.json')
    print(f'読B 孤儿误杀 {kill}/{n} = {kill/n*100:.1f}%（低于 25% 才有价值）')
    print(f'重心命中 {hit}/{n} = {hit/n*100:.1f}%')
    print(f'带文章的 {sum(1 for x in items if x["passage"])}/{n}')
    print()
    for lo, hi, lab in ((0, 2, '差0-2个(弱)'), (3, 99, '差3个以上(可靠)')):
        g = [x for x in items if lo <= x['margin'] <= hi]
        k = sum(1 for x in g if x['orphan'] == x['answer'])
        print(f'  {lab}: {len(g):>3} 题, 误杀 {k/len(g)*100:>5.1f}%')

if __name__ == '__main__':
    main()
