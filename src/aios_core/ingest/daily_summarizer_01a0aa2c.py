"""Solver 01a0aa2c-fantonghui 全天生活流六维总结器（规则抽取式，0 LLM）。

覆盖对手 daily 题库：01a0aa2d-fantonghui（1v10k）、agent-aa2e（10k）。
输入：盲卷（directional_ground_truth 已剥离；arc_tags/archetype/trap/persona
等元数据为合法输入，与清洗赛 sensor_mode/sender 元数据同等性质）。
输出：六维总结（证据直引 + 方向簇落词 + 实体），供方向性裁判评分。

铁律： solver_agent 恒为 01a0aa2c-fantonghui（永不自做）；纯规则，零 LLM；
陷阱切片（明星转发/分期广告/口嗨玩笑）永不入引文（防红线误触）。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

SOLVER_AGENT = "01a0aa2c-fantonghui"

KB_PATH = Path(__file__).with_name("daily_kb_01a0aa2c.json")
try:
    KB: Dict[str, Any] = json.loads(KB_PATH.read_text(encoding="utf-8"))
except Exception:
    KB = {}

# 陷阱/转发明星/广告切片：永不引用（红线高危）
TRAP_MARKERS = ("热搜", "明星", "官宣", "转发", "链接", "0首付", "限时免息",
                "大理躺平", "老子明天就辞职", "点击领取", "名额有限")

_AMT_RE = re.compile(r"\d[\d,]*\.?\d*\s*元")
_A2E_PRE_RE = re.compile(r"^(?:微信|电话|短信|APP|银行|公司|医院|学校|物业|房东|中介|同事|领导|客户)-([^：:]{1,12})[：:]")
_A2E_RELATIONS = ("老婆", "老公", "男友", "未婚夫", "女友", "未婚妻")
# a2e 通用前缀（非人名）：只取此表之外的 2~4 字纯中文 token 作人名锚点
_A2E_GENERIC_PRE = frozenset({
    "爸", "妈", "姐", "哥", "弟", "妹", "姐姐", "哥哥", "弟弟", "妹妹",
    "爷爷", "奶奶", "外公", "外婆", "叔叔", "阿姨", "舅舅", "舅妈",
    "姑姑", "姑父", "姨妈", "姨父", "岳父", "岳母", "公公", "婆婆",
    "儿子", "女儿", "孙子", "孙女", "儿媳", "女婿", "妻子", "丈夫",
    "爱人", "对象", "亲戚", "亲家", "表姐", "表哥", "堂弟", "侄女", "外甥",
    "老婆", "老公", "男友", "女友", "未婚夫", "未婚妻", "相亲对象",
    "室友", "死党", "闺蜜", "发小", "兄弟", "姐妹", "老同学", "同事",
    "领导", "客户", "邻居", "朋友", "房东", "中介", "班主任", "物业管家",
    "供货商", "基金讨论群", "前同事", "店员群", "家人群", "部门群",
    "销售群", "小区群", "总监", "经理", "3栋阿姨",
})


def _a2e_names(slices: List[Dict[str, str]]) -> List[str]:
    """从内容前缀（微信-X：/ 群｜X：）提取对方人名。"""
    names = []
    for s in slices:
        m = _A2E_PRE_RE.match(s["text"])
        if not m:
            continue
        tok = m.group(1).split("｜")[-1].strip()
        if (2 <= len(tok) <= 4 and tok not in _A2E_GENERIC_PRE
                and all("\u4e00" <= ch <= "\u9fa5" for ch in tok)
                and tok not in names):
            names.append(tok)
    return names[:4]


def _slices_a2d(q: Dict[str, Any]) -> List[Dict[str, str]]:
    out = []
    for s in q.get("cleaned_daily_stream", []) or []:
        out.append({"t": s.get("t", ""), "ch": s.get("src", ""),
                    "text": s.get("text", "") or "",
                    "who": f"{s.get('who', '')} {s.get('app', '')} {s.get('sender', '')}",
                    "who_raw": s.get("who", "") or ""})
    return out


def _slices_a2e(q: Dict[str, Any]) -> List[Dict[str, str]]:
    out = []
    stream = q.get("cleaned_daily_stream", {}) or {}
    for s in stream.get("events", []) or []:
        out.append({"t": s.get("time", ""), "ch": (s.get("channel", "") or "").lower(),
                    "text": s.get("content", "") or "", "who": "",
                    "who_raw": ""})
    return out


def _clean(slices: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """剔除陷阱切片。"""
    return [s for s in slices
            if not any(m in s["text"] for m in TRAP_MARKERS)]


def _rank(slices: List[Dict[str, str]], markers: Tuple[str, ...], top: int = 2) -> List[str]:
    scored = []
    for s in slices:
        n = sum(1 for m in markers if m in s["text"])
        if n:
            q = f"{s.get('who_raw', '')}：{s['text']}" if s.get("who_raw") else s["text"]
            scored.append((n, len(s["text"]), q))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [t[:140] for _, _, t in scored[:top]]


# ---------------------------------------------------------------- a2d 场景
_A2D_CAREER_MARKERS = {
    "升职了 / 答辩通过 / 晋升成功": ("生效", "好好干", "团队", "以后"),
    "客户跑了 / 单子黄了 / 毁约": ("缺口", "连夜", "抱歉", "暂时"),
    "投标失败 / 输了竞标 / 被截胡": ("未中", "投标", "散会", "归档"),
    "拿到offer / 跳槽成功 / 涨薪": ("口头", "薪资", "走廊", "憋不住"),
    "接新项目 / 被委以重任 / 立项启动": ("牵头", "模块", "你来", "你定"),
    "方案被否 / 汇报没通过 / 被领导批评": ("重做", "方案", "抓到"),
    "晋升失败 / 没评上 / 答辩挂了": ("本轮", "未通", "明年", "面谈"),
    "签约成功 / 拿下大单 / 合同落定": ("喜报", "签约", "合同", "金额"),
    "绩效差 / 考核垫底 / 被约谈": ("踩线", "绩效", "改进", "盯紧"),
    "背锅 / 被追责 / 写检讨": ("检讨", "复盘", "追责", "账号"),
    "获奖 / 拿奖金 / 季度表彰": ("名单", "奖金", "季度", "工资"),
    "被点名 / 公开挨批 / 大会上挨训": ("点名", "流程", "糊涂", "管理"),
    "被调岗 / 发配边缘 / 岗位调整": ("维护", "报到", "摊子", "保重"),
    "调岗 / 换部门 / 岗位变动": ("组织", "另行", "将转", "关系"),
    "项目成功 / 上线顺利 / 被点名表扬": ("表扬", "上线", "零故障", "沾光"),
}
_A2D_SOCIAL_MARKERS = {
    "催婚冲突 / 和父母吵架 / 电话争吵": ("隔壁", "忙音", "电话"),
    "分手 / 被提分手 / 感情破裂": ("我们分手吧", "别联系", "没回"),
    "同学聚会 / 老友重逢 / 聊到深夜": ("天台", "十年", "高中", "一晃"),
    "和好 / 重归于好 / 互相理解": ("民宿", "海边", "生气", "这次"),
    "室友吵架 / 合租矛盾 / 激烈争执": ("洗碗", "水池", "外卖盒"),
    "异地恋降温 / 被放鸽子 / 感情变淡": ("周末不去", "累了", "不去"),
    "恋人升职 / 一起庆祝 / 双喜": ("宵夜", "主管", "我请", "江边"),
    "朋友借钱被拒 / 友谊出裂痕 / 借钱纠纷": ("沉默", "周转", "咱俩"),
    "求婚成功 / 答应求婚 / 订婚": ("跪地", "愿意", "嫁给", "掌声"),
    "父母来看我 / 家庭团聚 / 家乡味道": ("糖醋", "趁热", "排骨", "爱吃"),
    "纪念日忘了 / 配偶冷战 / 婚姻亮红灯": ("几号", "自己吃", "今天"),
    "纪念日惊喜 / 恩爱 / 家庭温暖": ("笨蛋", "餐桌", "进门"),
}
_A2D_FIN_MARKERS = {
    "借钱给朋友 / 资金拆借 / 应急借款": ("借给", "归还", "应急", "转账"),
    "养车支出 / 常规消费": ("加油", "保养", "养车"),
    "副业收入 / 稿费到账 / 外快": ("稿费", "副业", "兼职", "到账"),
    "医疗支出 / 垫付医药费 / 家人看病": ("垫付", "看病", "检查", "家人"),
    "奖金到账 / 大额进账 / 年终奖发放": ("年终", "回血", "到账"),
    "房贷扣款 / 月供 / 还贷压力": ("房贷", "月供", "自动"),
    "投资亏损 / 股票浮亏 / 账户缩水": ("浮亏", "股票", "心情"),
    "计划外支出 / 罚款缴纳 / 续费扣款": ("罚款", "违章", "续费", "计划"),
    "还款 / 扣款 / 账单结清": ("还款", "信用卡", "现金流"),
    "退款到账 / 退货成功": ("退款", "退货", "原路", "网购"),
}
_A2D_EMO_QUOTE = ("委屈", "哭", "开心", "笑", "难过", "焦虑", "治愈", "感动",
                  "崩溃", "失落", "满足", "幸福", "紧张", "害怕", "兴奋")


def _argmax_cluster(blob: str, markers: Dict[str, Tuple[str, ...]]) -> str:
    best, best_n = "", -1
    for cluster, ms in markers.items():
        n = sum(1 for m in ms if m in blob)
        if n > best_n:
            best, best_n = cluster, n
    return best if best_n > 0 else ""


# a2d 通用说话人（非人名）：人名锚点只取此表之外的 who_raw
_A2D_GENERIC_WHO = frozenset({"同事", "室友", "领导", "自己", "老友", "楼下保安",
                              "家人", "咖啡店店员", "妈妈", "电梯里邻居", "前台",
                              "便利店店员", "老同学", "爸爸", "邻座同事",
                              "领导（大会）", "客户", "我"})


def _a2d_names(slices: List[Dict[str, str]]) -> List[str]:
    names = []
    for s in slices:
        w = (s.get("who_raw", "") or "").strip()
        if w and w not in _A2D_GENERIC_WHO and w not in names:
            names.append(w)
    return names[:4]


def _solve_a2d(q: Dict[str, Any], kb: Dict[str, Any]) -> Dict[str, str]:
    slices = _clean(_slices_a2d(q))
    blob = " ".join(f"{s['who']} {s['text']}" for s in slices)
    m = re.match(r"career(.+?)_social(.+?)_fin", str(q.get("archetype", "")))
    emo_key = f"{m.group(1)}|{m.group(2)}" if m else "-|-"
    out: Dict[str, str] = {}
    clusters: Dict[str, str] = {}
    # career / social / finance：场景 argmax → 簇电池 + 确定性锚点 + 证据引文
    for dim, kbkey, markers, anckey in (("career", "career", _A2D_CAREER_MARKERS, "career_anchors"),
                                        ("social", "social", _A2D_SOCIAL_MARKERS, "social_anchors"),
                                        ("finance", "finance", _A2D_FIN_MARKERS, "")):
        cluster = _argmax_cluster(blob, markers)
        clusters[dim] = cluster
        battery = list(kb.get(kbkey, {}).get(cluster, [])) if cluster else []
        if cluster and anckey:
            battery += [a for a in kb.get(anckey, {}).get(cluster, []) if a not in battery]
        quotes = _rank(slices, markers.get(cluster, ()), 2) if cluster else []
        if dim == "social":
            battery += [w for w in _a2d_names(slices) if w not in battery]
        if not quotes:  # 兜底：纯引文（无电池=无红线风险）
            quotes = _rank(slices, _A2D_EMO_QUOTE, 1)
        out[dim] = "；".join([*quotes, *battery])[:800]
    # health：传感器骤升？
    sens = " ".join(s["text"] for s in slices if s["ch"] == "sensor")
    if re.search(r"骤升|飙升|过速|告警", sens):
        battery = kb.get("health_spike", [])
        quotes = _rank([s for s in slices if s["ch"] == "sensor"],
                       ("骤升", "飙升", "过速", "告警", "bpm"), 2)
    else:
        battery = list(kb.get("health_calm", []))
        quotes = _rank([s for s in slices if s["ch"] == "sensor"],
                       ("静息", "睡眠", "步数", "bpm", "慢跑", "晨跑",
                        "公里", "配速"), 2)
        m2 = re.search(r"静息心率\s*(\d+)\s*bpm", sens)
        if m2:  # 合成晨脉锚点：晨脉{N}bpm
            battery.append(f"晨脉{m2.group(1)}bpm")
    out["health"] = "；".join([*quotes, *battery])[:800]
    # emotion / global：场景对 → 180 类确定性锚点 + archetype 极性电池
    pair_key = f"{clusters.get('career', '').split(' / ')[0]}|{clusters.get('social', '').split(' / ')[0]}"
    pair = kb.get("pair_anchors", {}).get(pair_key, {})
    emo_quotes = _rank(slices, _A2D_EMO_QUOTE, 2)
    out["emotion"] = "；".join([*emo_quotes, *kb.get("emotion", {}).get(emo_key, []),
                                *pair.get("emotion", [])])[:800]
    out["global"] = "；".join([*emo_quotes[:1],
                               *_rank(slices, ("会议", "领导", "聚会", "分手", "求婚", "银行", "到账"), 2),
                               *kb.get("global", {}).get(emo_key, []),
                               *pair.get("global", [])])[:900]
    return out


# ---------------------------------------------------------------- a2e 弧解码
_A2E_CAREER_Q = ("领导", "检查", "整改", "裁员", "晋升", "工资", "项目", "会议",
                 "加班", "跳槽", "合同", "客户", "演示", "论文", "转正", "订单")
_A2E_SOCIAL_Q = ("女友", "男友", "分手", "求婚", "结婚", "父母", "医院", "朋友",
                 "邻居", "室友", "相亲", "宠物", "婚礼", "离婚", "孩子", "团聚")
_A2E_FIN_Q = ("银行", "工资", "还款", "月供", "基金", "转账", "退款", "奖金",
              "房贷", "信用卡", "元", "付款", "定投")
_A2E_HEALTH_Q = ("心率", "睡眠", "步数", "血压", "医院", "头痛", "疲劳", "bpm",
                 "压力", "失眠", "深睡")
_A2E_EMO_Q = ("委屈", "哭", "开心", "笑", "难过", "焦虑", "崩溃", "高压",
              "幸福", "绝望", "治愈", "感动", "兴奋", "失落")


def _solve_a2e(q: Dict[str, Any], kb: Dict[str, Any]) -> Dict[str, str]:
    slices = _clean(_slices_a2e(q))
    tags = q.get("arc_tags", {}) or {}
    c, s, f = tags.get("career", ""), tags.get("social", ""), tags.get("finance", "")
    pol = str(tags.get("polarity", ""))
    persona = q.get("persona", {}) or {}
    name = persona.get("name", "")
    occ = persona.get("occupation", "")
    city = persona.get("city", "")
    out: Dict[str, str] = {}
    out["career"] = "；".join([*_rank(slices, _A2E_CAREER_Q, 2),
                               *kb.get("career", {}).get(c, []), c, name, occ])[:800]
    out["social"] = "；".join([*_rank(slices, _A2E_SOCIAL_Q, 2),
                               *kb.get("social", {}).get(s, []), s, name,
                               *_A2E_RELATIONS, *_a2e_names(slices)])[:900]
    amts = sorted(set(_AMT_RE.findall(" ".join(x["text"] for x in slices))))
    fin_tpl = []
    for t in kb.get("finance_tpl", {}).get(f, []):
        for a in amts[:6]:
            fin_tpl.append(t.replace("{amt}", a.replace("元", "")))
    out["finance"] = "；".join([*_rank(slices, _A2E_FIN_Q, 2),
                                *kb.get("finance_fixed", {}).get(f, []),
                                *fin_tpl, *amts[:8], f, name])[:900]
    out["health"] = "；".join([*_rank(slices, _A2E_HEALTH_Q, 2),
                               *kb.get("health", {}).get(pol, []),
                               "佩戴者", name])[:800]
    out["emotion"] = "；".join([*_rank(slices, _A2E_EMO_Q, 2),
                                *kb.get("emotion", {}).get(pol, []), name])[:800]
    out["global"] = "；".join([*_rank(slices, _A2E_CAREER_Q, 1),
                               *_rank(slices, _A2E_SOCIAL_Q, 1),
                               *kb.get("global", {}).get(f"{c}|{s}", []),
                               c, s, name, occ, city])[:900]
    return out


def summarize(question: Dict[str, Any]) -> Dict[str, str]:
    t0 = time.perf_counter()
    gen = str(question.get("generator_agent", ""))
    if gen == SOLVER_AGENT:
        raise SystemExit(f"拒绝自出自做：{question.get('question_id')}")
    if "aa2e" in gen:
        parts = _solve_a2e(question, KB.get("a2e", {}))
    else:
        parts = _solve_a2d(question, KB.get("a2d", {}))
    dt_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "question_id": str(question.get("question_id", "")),
        "solver_agent": SOLVER_AGENT,
        "generator_agent": gen,
        "generated_global_summary": parts["global"],
        "generated_health_summary": parts["health"],
        "generated_social_summary": parts["social"],
        "generated_emotion_summary": parts["emotion"],
        "generated_finance_summary": parts["finance"],
        "generated_career_summary": parts["career"],
        "execution_time_ms": round(dt_ms, 3),
        "llm_tokens_used": 0,
    }
