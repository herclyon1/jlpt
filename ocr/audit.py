#!/usr/bin/env python3
"""题库可用度审计：逐题检查题干/选项/答案是否齐全，输出每场次可用度。

用法（必须在仓库根目录跑）:
    python3 ocr/audit.py
    python3 ocr/audit.py --detail        # 列出每一道不可用的题

「可用」的定义：
  - 选项齐全（聴解問題4 需 3 个，其余需 4 个）
  - 选项之间互不重复
  - 有 1-4 的答案
  - 不在已知不可修复缺陷清单里
"""
import re, sys, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 已知不可修复的缺陷（源数据本身缺失，详见 DEVIATIONS.md）
UNFIXABLE = set()   # 已全部修复（2025-07 聴解問5題1 已从音频 whisper 转写补回）


def audit_file(path, sess, sec):
    """返回 (总题数, 可用题数, [不可用明细])"""
    tot = ok = 0
    bad = []
    dai = None
    for b in re.split(r'^(?=#題 |#大題 )', open(path, encoding='utf-8').read(), flags=re.M):
        md = re.match(r'^#大題 問題(\d+)', b)
        if md:
            dai = int(md.group(1))
            continue
        mq = re.match(r'^#題 (\S+)', b)
        if not mq:
            continue
        n = mq.group(1)
        tot += 1
        opts = [x.strip() for x in re.findall(r'^#选 \d (.*)$', b, re.M)]
        need = 3 if (sec == '聴解' and dai == 4) else 4
        ans = re.search(r'^#答 ([1-4])$', b, re.M)
        why = None
        if len(opts) < need:
            why = f'选项只有{len(opts)}个(需{need})'
        elif len(set(opts)) < len(opts):
            why = '选项有重复'
        elif not ans:
            why = '缺答案'
        elif (sess, sec, dai, n) in UNFIXABLE:
            why = '源数据缺失(不可修)'
        if why:
            bad.append(f'{sec} 問題{dai} 題{n}: {why}')
        else:
            ok += 1
    return tot, ok, bad


def main(detail=False):
    conv = os.path.join(ROOT, 'converted')
    sess = sorted({os.path.basename(f).rsplit('_', 1)[0] for f in glob.glob(f'{conv}/*.txt')})
    print(f"{'场次':<10}{'总题':>6}{'可用':>6}{'可用度':>9}   状态")
    print('-' * 58)
    T = O = 0
    allbad = []
    for s in sess:
        tot = ok = 0
        bad = []
        for sec in ('言語知識', '読解', '聴解'):
            p = f'{conv}/{s}_{sec}.txt'
            if not os.path.exists(p):
                continue
            t, o, b = audit_file(p, s, sec)
            tot += t; ok += o; bad += b
        if not tot:
            continue
        T += tot; O += ok
        mark = '★ 100%' if ok == tot else '; '.join(bad[:2]) + (f' …共{len(bad)}处' if len(bad) > 2 else '')
        print(f'{s:<10}{tot:>6}{ok:>6}{ok / tot * 100:>8.1f}%   {mark}')
        allbad += [f'{s} {x}' for x in bad]
    print('-' * 58)
    print(f"{'合计':<10}{T:>6}{O:>6}{O / T * 100:>8.1f}%")
    if detail and allbad:
        print('\n不可用明细:')
        for x in allbad:
            print('  ' + x)
    return 0 if O == T else 1


if __name__ == '__main__':
    sys.exit(main('--detail' in sys.argv))
