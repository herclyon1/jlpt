#!/usr/bin/env python3
"""生成完形预测训练/诊断数据 → export/drill_cloze.json

原理：把你变成一个语言模型。遮住文章里的一个词，你预测，立刻揭晓。
每个词都是一次带即时反馈的练习——这就是"自己造反馈"。

关键设计：**分开统计两类空**
  - function（虚词/零件）：助词、活用、接续——封闭集，考的是"结构直觉"
  - content（实词/词汇）：汉字词——开放集，考的是"词汇量"
两条正确率曲线一分开，就知道你卡在哪一半。
"""
import re, os, json, glob, random, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
random.seed(20260901)

def passages():
    for p in sorted(glob.glob(f'{ROOT}/converted/*_読解.txt')):
        tag = os.path.basename(p)[:-len('_読解.txt')]
        for name, body in re.findall(r'^#文 (\S+)\n(.*?)^#文完', open(p, encoding='utf-8').read(), re.M | re.S):
            body = re.sub(r'\n+', '\n', body.strip())
            if len(body) > 120:
                yield tag, name, body

def main():
    # 先统计全语料频次，用来挑干扰项（同类同频段）
    allf, allc = collections.Counter(), collections.Counter()
    P = list(passages())
    for _, _, b in P:
        allf.update(re.findall(r'[ぁ-ん]{1,4}', b))
        allc.update(re.findall(r'[一-鿿々]{2,4}', b))
    fpool = [w for w, n in allf.most_common(200) if len(w) >= 1]
    cpool = [w for w, n in allc.most_common(600)]

    items = []
    for tag, name, body in P:
        # 每篇挑 2 个虚词空 + 2 个实词空
        for kind, pat, pool in (('function', r'[ぁ-ん]{2,4}', fpool),
                                ('content', r'[一-鿿々]{2,4}', cpool)):
            cands = [m for m in re.finditer(pat, body)
                     if 30 < m.start() < len(body) - 20 and m.group() in pool]
            random.shuffle(cands)
            for m in cands[:2]:
                ans = m.group()
                distr = [w for w in pool if w != ans and abs(len(w) - len(ans)) <= 1]
                if len(distr) < 3:
                    continue
                opts = random.sample(distr, 3) + [ans]
                random.shuffle(opts)
                items.append({
                    'id': f'{tag}-{name}-{m.start()}',
                    'session': tag, 'kind': kind,
                    'left': body[max(0, m.start() - 90):m.start()],
                    'right': body[m.end():m.end() + 60],
                    'answer_text': ans,
                    'options': opts,
                    'answer': opts.index(ans) + 1,
                })
    random.shuffle(items)
    json.dump(items, open(f'{ROOT}/export/drill_cloze.json', 'w'), ensure_ascii=False)
    c = collections.Counter(x['kind'] for x in items)
    print(f'{len(items)} 题 → export/drill_cloze.json')
    print(f"  虚词空(零件) {c['function']}  ·  实词空(词汇) {c['content']}")
    print(f"  取自 {len(P)} 篇文章")

if __name__ == '__main__':
    main()
