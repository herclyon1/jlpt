#!/usr/bin/env python3
"""把 converted/ 的标准格式导出成网站直接可用的 JSON。

用法（仓库根目录）:
    python3 ocr/export_json.py              # 导出全部场次
    python3 ocr/export_json.py 2026-07      # 只导一场

产物: export/<场次>.json     单场完整数据
      export/index.json      所有场次的目录与统计

JSON 结构:
{
  "session": "2026-07",
  "passages": { "A1": "文章正文…", "T1-1": "听力台本…" },
  "sections": [
    { "name": "言語知識",
      "problems": [
        { "no": 1,
          "questions": [
            { "id": "2026-07-言語知識-1-1",
              "no": "1",
              "stem": "相手チームの多彩な攻撃に＜翻弄＞された。",
              "target": "翻弄",          # 题干里 ＜＞ 括起来的被考词（没有则为 null）
              "options": ["ばんろう", "ほんりょう", "ほんろう", "ばんりょう"],
              "answer": 3,               # 1-based
              "passage": null,           # 关联的 passages 键
              "audio": "2026-07/Q1-1.mp3"  # 仅聴解，相对 audio_clips/ 的路径
            } ] } ] } ]
}
"""
import re, os, sys, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse(path):
    """解析一个标准格式文件，返回 (科目, passages, [问题])"""
    sec = None
    passages = {}
    qs = []
    dai = None
    cur = None
    pas_name = None
    pas_buf = None
    for raw in open(path, encoding='utf-8'):
        l = raw.rstrip('\n')
        if pas_buf is not None:
            if l.startswith('#文完'):
                passages[pas_name] = '\n'.join(pas_buf).strip()
                pas_buf = None
            else:
                pas_buf.append(l)
            continue
        if l.startswith('#科'):
            sec = l[3:].strip()
        elif l.startswith('#大題'):
            m = re.search(r'\d+', l)
            dai = int(m.group()) if m else None
        elif l.startswith('#文 '):
            pas_name = l[3:].strip()
            pas_buf = []
            # 聴解是 #題 在前、#文 在后 → 回填给当前题
            if cur is not None and not cur['passage']:
                cur['passage'] = pas_name
        elif l.startswith('#題'):
            m = re.match(r'^#題\s+(\S+)(?:\s*[@＠]文\s*(\S+))?', l)
            if not m:
                continue
            cur = {'no': m.group(1), 'dai': dai, 'stem': '', 'options': [],
                   'answer': None, 'passage': m.group(2), '_last': pas_name}
            qs.append(cur)
        elif l.startswith('#干') and cur is not None:
            cur['stem'] = l[3:].strip()
        elif l.startswith('#选') and cur is not None:
            m = re.match(r'^#选\s+\d+\s+(.*)$', l)
            if m:
                cur['options'].append(m.group(1).strip())
        elif l.startswith('#答') and cur is not None:
            m = re.match(r'^#答\s+([1-4])', l)
            if m:
                cur['answer'] = int(m.group(1))
        elif l.strip() and cur is not None and not l.startswith('#'):
            cur['stem'] = (cur['stem'] + l.strip()) if cur['stem'] else l.strip()
    return sec, passages, qs


def export(tag):
    out = {'session': tag, 'passages': {}, 'sections': []}
    clips = set()
    cdir = f'{ROOT}/audio_clips/{tag}'
    if os.path.isdir(cdir):
        clips = {os.path.basename(f) for f in glob.glob(f'{cdir}/*.mp3')}
    for name in ('言語知識', '読解', '聴解'):
        p = f'{ROOT}/converted/{tag}_{name}.txt'
        if not os.path.exists(p):
            continue
        sec, passages, qs = parse(p)
        out['passages'].update(passages)
        byd = {}
        for q in qs:
            m = re.search(r'＜(.+?)＞', q['stem'])
            item = {
                'id': f"{tag}-{name}-{q['dai']}-{q['no']}",
                'no': q['no'],
                'stem': q['stem'] or None,
                'target': m.group(1) if m else None,
                'options': q['options'],
                'answer': q['answer'],
                'passage': q['passage'],
                'audio': None,
            }
            if name == '聴解':
                fn = f"Q{q['dai']}-{q['no']}.mp3"
                if fn in clips:
                    item['audio'] = f'{tag}/{fn}'
            byd.setdefault(q['dai'], []).append(item)
        out['sections'].append({
            'name': name,
            'problems': [{'no': d, 'questions': byd[d]} for d in sorted(byd)],
        })
    return out


def main(tags):
    os.makedirs(f'{ROOT}/export', exist_ok=True)
    index = []
    for t in tags:
        data = export(t)
        if not data['sections']:
            continue
        json.dump(data, open(f'{ROOT}/export/{t}.json', 'w'), ensure_ascii=False, indent=1)
        nq = sum(len(p['questions']) for s in data['sections'] for p in s['problems'])
        na = sum(1 for s in data['sections'] for p in s['problems']
                 for q in p['questions'] if q['answer'])
        naud = sum(1 for s in data['sections'] for p in s['problems']
                   for q in p['questions'] if q['audio'])
        index.append({'session': t, 'questions': nq, 'answers': na,
                      'audio_clips': naud, 'passages': len(data['passages']),
                      'sections': [s['name'] for s in data['sections']]})
        print(f'  {t}: {nq} 题 / {na} 答 / {len(data["passages"])} 篇文章 / {naud} 个音频片段')
    json.dump(index, open(f'{ROOT}/export/index.json', 'w'), ensure_ascii=False, indent=1)
    print(f'\n→ export/  共 {len(index)} 场次, {sum(i["questions"] for i in index)} 题')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tags = args or sorted({os.path.basename(f).rsplit('_', 1)[0]
                           for f in glob.glob(f'{ROOT}/converted/*.txt')})
    main(tags)
