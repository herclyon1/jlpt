#!/usr/bin/env python3
"""把从答案表原图读到的答案应用到 converted/ 文件（按題块重建，位置无关）。

输入每行:
  ## <场次>
  L <題号> <答案>          言語知識 + 読解
  T<大題号> <番号> <答案>   聴解（大題内番号）

用法: python3 ocr/apply_answers.py <答案文件> [--only 场次]
"""
import re, sys, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_ans(fp):
    out = {}
    sess = None
    for l in open(fp, encoding='utf-8'):
        l = l.strip()
        m = re.match(r'^##\s*(\S+)', l)
        if m:
            sess = m.group(1)
            out.setdefault(sess, {})
            continue
        if not sess or l.startswith('#'):
            continue
        m = re.match(r'^L\s+(\d+)\s+([1-9?])$', l)
        if m:
            if m.group(2) in '1234':
                out[sess][('L', int(m.group(1)))] = m.group(2)
            continue
        m = re.match(r'^T(\d)\s+(\d+)\s+([1-9?])$', l)
        if m and m.group(3) in '1234':
            out[sess][('T', int(m.group(1)), int(m.group(2)))] = m.group(3)
    return out


def apply(sess, ans):
    total = 0
    for sec, key in (('言語知識', 'L'), ('読解', 'L'), ('聴解', 'T')):
        p = f'{ROOT}/converted/{sess}_{sec}.txt'
        if not os.path.exists(p):
            continue
        lines = open(p, encoding='utf-8').read().split('\n')
        blocks = []
        cur = ['head', None, None, []]
        dai = None
        for l in lines:
            md = re.match(r'^#大題 問題(\d+)', l)
            mq = re.match(r'^#題 (\d+)', l)
            if md:
                blocks.append(cur)
                dai = int(md.group(1))
                cur = ['dai', dai, None, [l]]
                continue
            if mq:
                blocks.append(cur)
                cur = ['q', dai, int(mq.group(1)), [l]]
                continue
            cur[3].append(l)
        blocks.append(cur)

        changed = nq = nans = 0
        for b in blocks:
            if b[0] != 'q':
                n0 = len(b[3])
                b[3] = [x for x in b[3] if not x.startswith('#答')]
                changed += n0 - len(b[3])
                continue
            nq += 1
            k = (key, b[1], b[2]) if key == 'T' else (key, b[2])
            v = ans.get(k)
            body = [x for x in b[3] if not x.startswith('#答')]
            had = [x for x in b[3] if x.startswith('#答')]
            while body and not body[-1].strip():
                body.pop()
            if v:
                new = f'#答 {v}'
                if had != [new]:
                    changed += 1
                body.append(new)
                nans += 1
            elif had:
                body.append(had[0])
                nans += 1
            body.append('')
            b[3] = body

        txt = '\n'.join(x for b in blocks for x in b[3])
        txt = re.sub(r'\n{3,}', '\n\n', txt).rstrip() + '\n'
        open(p, 'w', encoding='utf-8').write(txt)

        r = subprocess.run([sys.executable, f'{ROOT}/ocr/check_format.py', p],
                           capture_output=True, text=True)
        if '✅ 通过' in r.stdout:
            mark = '✅'
        else:
            r = subprocess.run([sys.executable, f'{ROOT}/ocr/check_format.py', p, '--loose'],
                               capture_output=True, text=True)
            mark = '◐' if '✅ 通过' in r.stdout else '❌'
        print(f"  {sess}_{sec}: {nq}题 {nans}答 (改动{changed}) {mark}")
        total += changed
    return total


if __name__ == '__main__':
    fp = sys.argv[1]
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    A = parse_ans(fp)
    for sess, ans in sorted(A.items()):
        if only and sess != only:
            continue
        print(f"\n=== {sess} ({len(ans)} 条) ===")
        apply(sess, ans)
