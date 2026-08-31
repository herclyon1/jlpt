#!/usr/bin/env python3
"""把整段听力 mp3 按题切成片段，供网站逐题播放。

原理：不靠 whisper 的「N番」标记（会漏），改用**内容对齐**——
拿 converted/<场次>_聴解.txt 里每道题台本的开头一句，去 whisper 带时间戳的
转写里做模糊匹配，得到该题的起始时间；下一题的起始时间即本题的结束时间。

用法（在仓库根目录）:
    python3 ocr/segment_audio.py 2025-12                 # 只算切点，输出对齐报告
    python3 ocr/segment_audio.py 2025-12 --cut           # 真正切出 mp3 片段
    python3 ocr/segment_audio.py --all --cut

产物: audio_clips/<场次>/Q<大題>-<題号>.mp3
      audio_clips/<场次>/segments.json   （每题的起止秒数与对齐置信度）
"""
import re, os, sys, glob, json, subprocess, difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASR_DIR = '/tmp/asr/out'
AUDIO_GLOB = os.path.expanduser('~/Downloads/jlpt_x/{dir}/*.mp3')
SESS_DIR = {'2021-07': '2021年7月', '2021-12': '2021年12月', '2022-07': '2022年7月',
            '2022-12': '2022年12月', '2023-07': '2023年7月', '2023-12': '2023年12月',
            '2024-07': '2024年7月', '2025-07': '2025年7月', '2025-12': '2025年12月',
            '2026-07': '2026年7月'}

def norm(s):
    return re.sub(r'[\s、。？！「」『』・,.?!ー〜]', '', s or '')

def load_asr(tag):
    """返回 [(start, end, text, norm_text)]，兼容 [s] 和 [s-e] 两种格式"""
    p = f'{ASR_DIR}/{tag}.txt'
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p, encoding='utf-8'):
        m = re.match(r'^\[([\d.]+)-([\d.]+)\]\s*(.*)$', l) or re.match(r'^\[([\d.]+)\]\s*()(.*)$', l)
        if not m:
            continue
        st = float(m.group(1))
        en = float(m.group(2)) if m.group(2) else st
        txt = m.group(3).strip()
        out.append([st, en, txt, norm(txt)])
    # 没有 end 的，用下一段的 start 补
    for i in range(len(out) - 1):
        if out[i][1] <= out[i][0]:
            out[i][1] = out[i + 1][0]
    return out

def load_questions(tag):
    """返回 [(大題, 題号, 台本开头120字)]

    兼容两种排版：#文 在 #題 之后（块内），或 #文 在前、#題 用 @文 引用。
    """
    p = f'{ROOT}/converted/{tag}_聴解.txt'
    if not os.path.exists(p):
        return []
    raw = open(p, encoding='utf-8').read()
    # 先建全局 passage 表
    pas = {m.group(1): m.group(2) for m in
           re.finditer(r'^#文 (\S+)\n(.*?)^#文完', raw, re.M | re.S)}
    qs = []
    dai = None
    for b in re.split(r'^(?=#題 |#大題 )', raw, flags=re.M):
        md = re.match(r'^#大題 問題(\d+)', b)
        if md:
            dai = int(md.group(1)); continue
        mq = re.match(r'^#題 (\S+)(?:\s*[@＠]文\s*(\S+))?', b)
        if not mq:
            continue
        m = re.search(r'^#文 \S+\n(.*?)^#文完', b, re.M | re.S)
        body = m.group(1) if m else pas.get(mq.group(2) or '', '')
        head = norm(re.sub(r'^[男女M F][12]?[：:]', '', body, flags=re.M))[:120]
        qs.append((dai, mq.group(1), head))
    return qs

def locate(head, asr, from_idx):
    """在 asr[from_idx:] 里找 head 的起始段，返回 (段索引, 相似度)"""
    if not head:
        return None, 0.0
    probe = head[:40]
    best = (None, 0.0)
    for i in range(from_idx, len(asr)):
        # 把连续几段拼起来比，因为 whisper 的分段和句子边界不一致
        cat = ''.join(a[3] for a in asr[i:i + 4])[:len(probe) + 20]
        if not cat:
            continue
        r = difflib.SequenceMatcher(None, probe, cat[:len(probe)]).ratio()
        if r > best[1]:
            best = (i, r)
        if r > 0.92:
            break
    return best

def segment(tag, cut=False):
    asr = load_asr(tag)
    qs = load_questions(tag)
    if not asr:
        print(f'{tag}: 缺 ASR 转写 ({ASR_DIR}/{tag}.txt)'); return None
    if not qs:
        print(f'{tag}: 缺 converted/{tag}_聴解.txt'); return None
    marks = []
    idx = 0
    prev_head = None
    for dai, n, head in qs:
        # 問題5 的 質問1/質問2 共用同一段対話 → 复用上一题的切点
        if prev_head is not None and head and head[:40] == prev_head[:40]:
            marks.append((dai, n, marks[-1][2], marks[-1][3])); prev_head = head; continue
        i, r = locate(head, asr, idx)
        prev_head = head
        if i is None:
            marks.append((dai, n, None, 0.0)); continue
        marks.append((dai, n, asr[i][0], r))
        idx = max(idx, i + 1)
    # 结束时间 = 下一题的起始；最后一题到音频末尾
    segs = []
    for k, (dai, n, st, r) in enumerate(marks):
        if st is None:
            segs.append({'dai': dai, 'q': n, 'start': None, 'end': None, 'conf': 0.0}); continue
        nxt = next((m[2] for m in marks[k + 1:] if m[2] is not None and m[2] > st), asr[-1][1])
        segs.append({'dai': dai, 'q': n, 'start': round(st, 1), 'end': round(nxt, 1), 'conf': round(r, 3)})
    lo = [s for s in segs if s['conf'] < 0.6]
    print(f"{tag}: {len(segs)} 题, 对齐置信度<0.6 的 {len(lo)} 题"
          + (f" → {[(s['dai'], s['q']) for s in lo]}" if lo else ''))
    outdir = f'{ROOT}/audio_clips/{tag}'
    os.makedirs(outdir, exist_ok=True)
    json.dump(segs, open(f'{outdir}/segments.json', 'w'), ensure_ascii=False, indent=1)
    if cut:
        src = glob.glob(AUDIO_GLOB.format(dir=SESS_DIR[tag]))
        if not src:
            print(f'  {tag}: 找不到音频'); return segs
        env = dict(os.environ, PATH=os.path.expanduser('~/homebrew/bin') + ':' + os.environ['PATH'])
        # 有的源音频流是 AAC（且带 h264 封面流），copy 进 mp3 容器会失败 → 改为转码
        codec = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                                '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', src[0]],
                               capture_output=True, text=True, env=env).stdout.strip()
        acodec = ['-c:a', 'copy'] if codec == 'mp3' else ['-c:a', 'libmp3lame', '-b:a', '96k']
        n_ok = 0
        for s in segs:
            if s['start'] is None:
                continue
            dst = f"{outdir}/Q{s['dai']}-{s['q']}.mp3"
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(s['start']),
                            '-to', str(s['end']), '-i', src[0],
                            '-map', '0:a:0', '-vn'] + acodec + [dst], env=env)
            n_ok += os.path.exists(dst) and os.path.getsize(dst) > 1000
        print(f'  切出 {n_ok} 个片段 → {outdir}/')
    return segs

if __name__ == '__main__':
    cut = '--cut' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tags = sorted(SESS_DIR) if ('--all' in sys.argv or not args) else args
    for t in tags:
        segment(t, cut)
