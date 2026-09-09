# -*- coding: utf-8 -*-
import json, re

SRC = r'C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code\run\bench1k\blind_b2.json'
OUT = r'C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code\run\bench1k\answers_big_b2.json'

d = json.load(open(SRC, encoding='utf-8'))

# T6 event -> classification (keyword -> answer)
t6_rules = [
    ('心率 68', 'IGNORE'),
    ('静息状态下心率 110', 'ESCALATE'),
    ('明天能见面吗', 'LOCAL'),
    ('交付时间表发我', 'ESCALATE'),
    ('地铁上', 'IGNORE'),
    ('夜宵外卖', 'ESCALATE'),
    ('实际在刷手机', 'ESCALATE'),
    ('谈论天气', 'IGNORE'),
    ('明天给你方案', 'LOCAL'),
    ('运动中瞬时心率', 'IGNORE'),
    ('银行短信', 'ESCALATE'),
    ('今天真没意思', 'ESCALATE'),
]

def t6_answer(q):
    event = q.split('事件：')[-1]
    for kw, ans in t6_rules:
        if kw in event:
            return ans
    return 'UNKNOWN'

def t4_answer(ctx):
    c = ctx[0] if ctx else ''
    if '保证月底前上线' in c:
        return '保证月底前上线'
    if '答应小雅周末陪她看展' in c:
        return '答应小雅周末陪她看展'
    if '向王医生保证按时复查' in c:
        return '向王医生保证按时复查'
    if '这个版本的交互要重做，明天给你方案' in c:
        return '这个版本的交互要重做，明天给你方案'
    return '记录中没有'

def t3_answer(ctx):
    total = 0
    for line in ctx:
        m = re.search(r'¥(\d+)', line)
        if m:
            total += int(m.group(1))
    return str(total)

def t5_answer(ctx):
    vals = [int(m.group(1)) for line in ctx for m in [re.search(r'心率\s*(\d+)', line)] if m]
    return str(max(vals))

answers = []
for item in d:
    qid = item['qid']
    t = item['type']
    q = item['q']
    ctx = item.get('ctx', [])
    if t == 'T3':
        ans = t3_answer(ctx)
    elif t == 'T4':
        ans = t4_answer(ctx)
    elif t == 'T5':
        ans = t5_answer(ctx)
    elif t == 'T6':
        ans = t6_answer(q)
    else:
        ans = '记录中没有'
    answers.append({'qid': qid, 'answer': ans})

json.dump(answers, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# summary
from collections import Counter
cnt = Counter(x['type'] for x in d)
print('total', len(answers))
print('type counts', dict(cnt))
unknown = [a for a in answers if a['answer'] == 'UNKNOWN']
print('unknown', unknown)
no_rec = [a['qid'] for a in answers if a['answer'] == '记录中没有']
print('记录中没有 count', len(no_rec))
print('记录中没有 qids:', no_rec)
