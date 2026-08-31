#!/usr/bin/env python3
"""统一 聴解問題5 的題号格式，消除撞号。

問題5 的结构固定：1番（单问）+ 2番（双问：質問1/質問2）。
但 11 套卷里出现过 6 种写法（`2質問1`/`3質問2`/`2番質問1`/`2 質問1`/`2-1`…），
其中 2025-07 的 `#題 2 質問1` 带空格，会被 `^#題 (\S+)` 截成 `2`，
与 `#題 2 質問2` 撞号——而这两题答案不同，网站按 id 取答案会取错。

统一为：#題 1 / #題 2-1 / #題 2-2
"""
import re, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def norm(path):
    raw = open(path, encoding='utf-8').read()
    i = raw.find('#大題 問題5')
    if i < 0:
        return 0
    head, body = raw[:i], raw[i:]
    # 按出现顺序把 問題5 的題号重编为 1 / 2-1 / 2-2
    labels = ['1', '2-1', '2-2']
    k = [0]
    def rep(m):
        rest = m.group(2)                     # 可能带 @文 引用
        ref = re.search(r'[@＠]文\s*(\S+)', rest)
        lab = labels[k[0]] if k[0] < len(labels) else str(k[0] + 1)
        k[0] += 1
        return f'#題 {lab}' + (f' @文 {ref.group(1)}' if ref else '')
    body2 = re.sub(r'^#題 (\S+)(.*)$', rep, body, flags=re.M)
    if body2 == body:
        return 0
    open(path, 'w', encoding='utf-8').write(head + body2)
    return k[0]

if __name__ == '__main__':
    files = sys.argv[1:] or sorted(glob.glob(f'{ROOT}/converted/*_聴解.txt'))
    for f in files:
        n = norm(f)
        if n:
            print(f'  {os.path.basename(f)}: 問題5 的 {n} 个題号已统一为 1 / 2-1 / 2-2')
