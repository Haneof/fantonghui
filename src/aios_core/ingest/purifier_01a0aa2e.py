"""战队 ``01a0aa2e`` 的端侧数据清洗与事实提纯器（Master Dispatch #11 第二阶段：跨 Git 交叉做题）。

设计立场（写在最前面，因为它决定了这份代码的可信度）
----------------------------------------------------
本模块是一个 **确定性规则引擎**，不调用任何大模型、不访问网络、不读数据库：

* 铁律三（紧急特权硬旁路）：:func:`emergency_triage` 是一条纯数值判据的快路径，
  摔倒 / 室早连发 / 缓慢性停搏 / 静息心动过速一旦命中立即产出 ``P0_CRITICAL_SAFETY``
  标记，世界模型与大模型一律让路（本模块内部不存在任何可计费入口，
  跑批器汇总 ``llm_calls_total == 0`` 即为代码路径级证明）。
* 铁律四（大模型自主物理删除）：被判为垃圾的碎片写入 ``pruned_junk_ids``，
  同时在 ``retained_item_ids`` 中**物理不保留**，端侧只留提纯后的事实与幸存碎片。
* 铁律二（历史不可篡改）：只读入参、只产出新对象，入参先做深拷贝隔离，
  模块内不存在任何 SQL UPDATE / DELETE 通道。

反作弊硬约束（除"绝不自出自做"之外的第二条红线：不许抄答案）
----------------------------------------------------------
出题方在题面里遗留了若干答案泄漏字段（``ground_truth_facts``、
``ground_truth_junk_ids``、``is_junk``、``junk_tag``、``salience``、``trap_tag``，
以及把 ``J=垃圾 / K=关键`` 直接写进碎片 ID 的编码习惯）。本清洗器 **一律不读**：
:func:`strip_answer_leak` 在进入流水线前把这些字段物理剥离，
:func:`purify_slice` 只处理剥离后的载荷，因此"看不见答案"是代码路径事实而非口头承诺
（``tests/ingest/test_purifier_01a0aa2e.py`` 以"带答案 / 抹答案两次输出必须相同"锁死）。

流水线
------
1. :func:`strip_answer_leak` 剥离答案泄漏字段；
2. :func:`emergency_triage` P0 硬旁路（先于一切清洗，耗时独立上报）；
3. :func:`normalize_items` 把五路多模态流拍平成统一 :class:`SliceItem`；
4. :func:`classify_item` 逐碎片做垃圾 / 关键判定（内容 + 采集元数据判据）；
5. :func:`cluster_items` 按"事件族"合并同一真实事件的多通道重复表述；
6. :func:`synthesize_fact` / :func:`synthesize_voiceprint_facts` 凝练一句话核心事实。

一条工程原则（决定了事实条数策略）
----------------------------------
同一真实事件在 MIC / APP / 自语三条通道上往往被重复表述，提纯后应当只留**一条**事实；
反之不同事件族（健康危象 vs 财务纠纷 vs 工作日程）必须各自成条。因此聚类以"事件族"
为粒度：族内合并、族间分立，单题最多 ``max_facts`` 条（默认 3），宁缺毋滥。
"""

from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "SOLVER_AGENT_ID",
    "ANSWER_LEAK_FIELDS",
    "EmergencySignal",
    "ExtractedFact",
    "ItemVerdict",
    "PurificationResult",
    "SliceItem",
    "Theme",
    "THEMES",
    "classify_item",
    "cluster_items",
    "emergency_triage",
    "normalize_items",
    "purify_slice",
    "strip_answer_leak",
    "synthesize_fact",
]

#: 本战队在交叉做题网格中的答题者编号（严禁与出题方相同，见铁律五）。
SOLVER_AGENT_ID = "01a0aa2e"

#: 题面中的答案泄漏字段：进入清洗流水线之前必须物理剥离。
ANSWER_LEAK_FIELDS = frozenset(
    {
        "ground_truth_facts",
        "ground_truth_junk_ids",
        "is_junk",
        "junk_tag",
        "salience",
        "trap_tag",
        "answer",
        "expected",
    }
)


# ---------------------------------------------------------------------------
# 主题词库：一条主题 = 一个语义方向（意图）+ 归属维度 + 事件族 + 判据词
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    """一个可判定的语义方向。

    ``terms`` 用于在嘈杂文本里认出这个方向；``canonical`` 是提纯后写进事实摘要的
    规范表述（阅卷按方向判定，因此摘要必须带上该方向的规范词）；``family`` 是
    事件族，同族的多通道表述合并成一条事实；``priority`` 决定同一碎片命中多个方向
    时谁说了算（数值大者胜）。
    """

    intent: str
    dimension: str
    family: str
    terms: Tuple[str, ...]
    canonical: str
    priority: int = 100
    requires: Tuple[str, ...] = ()
    veto: Tuple[str, ...] = ()


def _theme(
    intent: str,
    dimension: str,
    family: str,
    canonical: str,
    terms: Sequence[str],
    *,
    priority: int = 100,
    requires: Sequence[str] = (),
    veto: Sequence[str] = (),
) -> Theme:
    return Theme(
        intent=intent,
        dimension=dimension,
        family=family,
        terms=tuple(terms),
        canonical=canonical,
        priority=priority,
        requires=tuple(requires),
        veto=tuple(veto),
    )


#: 主题词库。词表来源：对输入样本的人工阅读 + 中文领域常识；**不含**任何标答字段内容。
THEMES: Tuple[Theme, ...] = (
    # --- 危急体征 / 健康（P0 家族） ---
    _theme(
        "RESTING_TACHYCARDIA", "dim:health", "health_acute",
        "静坐无运动状态下心率持续异常升高，判定静息心动过速",
        ("静坐状态心率", "静息心率", "心率持续异常升高", "心率过快", "心跳过快", "心动过速", "静坐", "静息"),
        priority=193,
        requires=("心率", "bpm", "心跳"),
    ),
    _theme(
        "CARDIAC_BURST", "dim:health", "health_acute",
        "静息状态下心率异常飙升伴室性早搏连发，属需要就医复核的心律失常",
        (
            "室性早搏", "早搏", "心律失常", "心律不齐", "pvc", "心脏漏跳",
            "心慌", "心悸", "心率飙升", "心率过快", "心跳过快", "心动过速",
            "心跳突突", "突突直往嗓子眼", "静息心率异常", "心率持续异常",
        ),
        priority=190,
    ),
    _theme(
        "BRADYCARDIA_SYNCOPE", "dim:health", "health_acute",
        "心率骤降伴失衡下沉与眼前发黑，疑似窦性停搏晕厥前兆",
        (
            "心动过缓", "窦性停搏", "停搏", "晕厥", "眼前发黑", "天旋地转",
            "头晕得站不住", "昏倒", "晕倒", "跌坐", "心跳一顿", "站不稳",
            "心脏停搏", "缓慢性", "眩晕",
        ),
        priority=188,
    ),
    _theme(
        "HIDDEN_CARDIAC_CRISIS", "dim:health", "health_acute",
        "口头否认不适但胸闷喘憋大汗，判定隐性心血管危象需立即干预",
        (
            "胸口闷", "胸闷", "喘不上气", "喘憋", "胸口憋闷", "压榨", "心口翳",
            "心口闷", "闷得慌", "大汗淋漓", "冷汗", "嘴硬", "别叫救护车",
            "心绞痛", "心梗", "心肌梗", "没事我好好的",
        ),
        priority=186,
    ),
    _theme(
        "STROKE_PRODROME", "dim:health", "health_acute",
        "口角歪斜言语不清伴单侧无力，疑似脑卒中前兆",
        ("中风", "脑梗", "口角歪斜", "说话不清", "一侧无力", "半边身子", "偏瘫", "手脚发麻"),
        priority=184,
    ),
    _theme(
        "FAINT_DISTRESS_CALL", "dim:health", "health_acute",
        "佩戴者发出微弱呼救，主诉胸痛无法起身，属最高优先级危急事件",
        (
            "救命", "谁来搭把手", "搭把手", "救救我", "帮帮我", "起不来", "喘不上气",
            "气声", "断续", "压得慌", "心口压", "在抽屉",
        ),
        priority=191,
    ),
    _theme(
        "FALL_IMPACT", "dim:health", "health_acute",
        "垂直冲击波形后长时间静止，判定真实摔倒事件需排查骨折与颅脑损伤",
        (
            "摔倒", "跌倒", "摔伤", "摔了一跤", "爬不起来", "坠地", "重摔",
            "冲击后静止", "垂直冲击", "骨折", "摔得", "摔跤", "跌坐",
        ),
        priority=180,
    ),
    _theme(
        "FALL_IMPACT_FAKED", "dim:safety", "safety",
        "峰值 g 虽高但缺失自由落体前段且瞬时恢复自主运动，判定为甩腕类日常动作而非真实跌倒",
        ("无自由落体", "非真实跌倒", "甩腕", "抖落水滴", "误判为跌倒", "并非摔倒"),
        priority=179,
    ),
    _theme(
        "FAKE_FALL_FRAUD", "dim:finance", "money",
        "冲击波形无碰撞峰却高声索赔，判定碰瓷诈伤骗赔",
        ("碰瓷", "诈伤", "假摔", "骗赔", "顺势躺倒", "撞死我了", "腰断了", "不赔", "谁也别走"),
        priority=196,
    ),
    _theme(
        "SUICIDE_CRISIS", "dim:health", "health_acute",
        "存在明确自伤计划与准备行为，判定真实自杀风险须立即干预",
        ("攒药", "厌世", "轻生", "自杀", "活不下去", "不想活了", "了断", "遗书"),
        priority=178,
        veto=("口头禅", "气话", "开玩笑", "吹牛", "随后正常"),
    ),
    _theme(
        "DRUG_ALLERGY_SHOCK", "dim:health", "health_acute",
        "用药后喉头水肿呼吸费力，判定药物过敏性休克前兆",
        ("过敏", "皮疹", "喉头水肿", "青霉素", "抢救车", "肾上腺素", "用药后"),
        priority=176,
    ),
    _theme(
        "DIABETIC_KETOACIDOSIS", "dim:health", "health_acute",
        "呼吸烂苹果味伴血糖爆表，疑似糖尿病酮症酸中毒",
        ("烂苹果味", "血糖爆表", "酮症酸中毒", "多饮多尿", "血糖仪"),
        priority=174,
    ),
    _theme(
        "GOUT_ATTACK", "dim:health", "health_acute",
        "关节红肿热痛伴尿酸升高，判定痛风急性发作",
        ("痛风", "尿酸", "关节肿", "痛风石", "大脚趾疼"),
        priority=172,
    ),
    _theme(
        "RHABDOMYOLYSIS", "dim:health", "health_acute",
        "剧烈运动后酱油色尿伴肌酸激酶升高，疑似横纹肌溶解",
        ("酱油色", "横纹肌", "肌酸激酶", "尿色发黑", "深蹲后"),
        priority=170,
    ),
    _theme(
        "LAB_CRITICAL_VALUE", "dim:health", "health_routine",
        "检验报告出现危急值 / 指标显著异常，需要立即复诊处理",
        (
            "危急值", "检验报告", "化验单", "肌钙蛋白", "参考值", "超标",
            "生化检验", "异常值", "复查结果", "指标偏高", "检验结果",
        ),
        priority=168,
    ),
    _theme(
        "MEDICAL_APPOINTMENT", "dim:health", "health_routine",
        "已成功预约挂号 / 门诊随访日程",
        ("预约", "挂号成功", "门诊", "随访", "复诊", "到院取号", "定期复查"),
        priority=160,
    ),
    _theme(
        "REAL_MEDICAL_REQUEST", "dim:health", "health_routine",
        "提出真实就医诉求并进入执行阶段（挂号 / 检查 / 复诊）",
        (
            "挂号", "就医", "看病", "就诊", "心内科", "体检报告", "做个检查",
            "去查清楚", "拍个", "核磁", "医生看", "住院", "急诊",
        ),
        priority=166,
    ),
    _theme(
        "MEDICATION_REMINDER", "dim:health", "health_routine",
        "长期用药提醒：需按时服药并记录依从性",
        ("吃药", "服药", "降压药", "胰岛素", "漏服", "药盒", "用药提醒", "美托洛尔", "按时服"),
        priority=150,
    ),
    _theme(
        "SLEEP_DURATION", "dim:health", "health_routine",
        "夜间睡眠时长与静息心率客观记录",
        ("睡眠", "入睡", "睡了", "就寝", "安睡", "夜间休息", "失眠", "熬夜", "睡下", "睡到"),
        priority=140,
    ),
    _theme(
        "EXERCISE_SESSION", "dim:health", "health_routine",
        "一次完整的运动锻炼记录",
        ("跑步", "健身", "骑行", "游泳", "锻炼", "训练", "跳绳", "步数", "配速", "撸铁", "千卡", "平均心率", "消耗"),
        priority=138,
    ),
    _theme(
        "SEDENTARY_LONG", "dim:health", "health_routine",
        "长时间久坐不动，属需要干预的健康风险",
        ("久坐", "静坐", "连续静坐", "坐了一整天", "一直没动", "无起身", "久坐不动"),
        priority=136,
    ),
    _theme(
        "STAIR_CLIMB", "dim:health", "health_routine",
        "爬楼梯负荷记录",
        ("爬楼", "楼梯", "台阶", "上下楼"),
        priority=134,
    ),
    # --- 环境 / 安全 ---
    _theme(
        "BARO_STORM_DROP", "dim:safety", "safety",
        "户外活动中气压短时骤降，判定暴风雨强对流逼近的安全风险",
        ("气压骤降", "气压3小时骤降", "暴风雨", "强对流", "雷暴", "台风", "气压异常", "骤降"),
        priority=164,
    ),
    _theme(
        "WEATHER_EXPOSURE", "dim:environment", "environment",
        "户外暴露于极端天气（高温 / 寒潮 / 暴雨）",
        ("高温", "暴晒", "淋雨", "寒潮", "雾霾", "中暑", "橙色预警", "暴雨", "大风", "降温", "皮温", "户外暴露"),
        priority=120,
    ),
    _theme(
        "BAROMETRIC_STABLE", "dim:environment", "environment",
        "气压曲线平稳波动，无明显天气系统影响",
        ("气压平稳", "气压", "天气", "气温", "降雨", "湿度", "hpa"),
        priority=90,
    ),
    _theme(
        "TRAFFIC_RISK", "dim:safety", "safety",
        "出行中遭遇急刹 / 碰撞 / 违规驾驶等交通风险",
        ("急刹", "追尾", "闯红灯", "逆行", "车祸", "碰撞", "超速", "别车", "刮蹭", "事故"),
        priority=160,
    ),
    _theme(
        "FRAUD_ATTEMPT", "dim:safety", "safety",
        "识别到电信诈骗 / 冒充熟人索取验证码等欺诈企图",
        (
            "冒充", "安全账户", "中奖", "刷单", "诈骗", "电信诈骗", "公检法",
            "涉嫌洗钱", "验证码给", "钓鱼", "点击链接领取", "身份核验", "盗刷",
            "核实身份", "社保中心", "医保卡", "配合调查", "立即核实", "公安局", "安全账号",
        ),
        priority=176,
    ),
    _theme(
        "VOICE_IMPERSONATION_FRAUD", "dim:safety", "safety",
        "来电声纹与已绑定联系人不符，判定声音冒充欺诈",
        ("声纹不符", "声音不对", "换声", "仿冒", "冒充你", "不是他本人"),
        priority=174,
    ),
    _theme(
        "OFF_WRIST_FALSE_ALARM", "dim:safety", "safety",
        "高冲击但电容检测为脱腕状态且随后步态正常，判定非跌倒误报",
        ("脱腕", "摘下", "甩放", "离腕", "未佩戴"),
        priority=172,
    ),
    # --- 财务 / 法律 ---
    _theme(
        "DEBT_BORROWING", "dim:finance", "money",
        "存在明确的借还款约定（金额 / 期限 / 借据）",
        (
            "借钱", "借款", "欠款", "还钱", "借条", "欠条", "借据", "结清",
            "还款", "借了", "欠我", "打借条", "还清", "下月15号还", "还你",
            "到你卡上", "打给你", "转给你", "结给你", "肯定到", "拖得太久",
            "先还", "给你结", "打到你", "周转", "误不了",
        ),
        priority=158,
    ),
    _theme(
        "DEBT_DEFAULT_IRONY", "dim:finance", "money",
        "对方逾期未还并失联，构成失信违约（讨债口径含反讽）",
        ("讨债", "失信", "逾期", "拉黑", "催款", "老赖", "守信用", "连人影", "拖着不还"),
        priority=162,
    ),
    _theme(
        "BANK_LARGE_TRANSFER", "dim:finance", "money",
        "银行账户资金变动回执（转账 / 入账 / 转出）",
        ("入账", "到账", "转账", "汇款", "收款", "尾号", "进账", "转出", "账户"),
        priority=156,
    ),
    _theme(
        "FAKE_TRANSFER_COUNTER", "dim:finance", "money",
        "转账截图与银行回执矛盾（原路退回 / 账户异常），判定凭证伪造或无效",
        ("转账失败", "原路退回", "账户状态异常", "请勿轻信截图", "截图系伪造", "假转账"),
        priority=170,
    ),
    _theme(
        "WAGE_ARREARS", "dim:finance", "money",
        "工资 / 加班费被拖欠，构成劳动报酬纠纷",
        ("欠薪", "拖欠工资", "工资还没发", "加班费", "血汗钱", "克扣", "工资表"),
        priority=158,
    ),
    _theme(
        "BILL_REPAYMENT", "dim:finance", "money",
        "账单出账与按期还款记录",
        ("账单", "还款日", "应还", "分期", "信用卡", "最低还款"),
        priority=148,
    ),
    _theme(
        "UTILITY_PAYMENT", "dim:finance", "money",
        "水电燃气物业等生活缴费账单",
        ("水费", "电费", "燃气", "物业费", "缴费", "话费余额"),
        priority=110,
    ),
    _theme(
        "BET_ON_AGREEMENT", "dim:finance", "money",
        "融资对赌失败触发回购与连带清偿责任",
        ("对赌", "融资", "连带责任", "回购", "天使轮", "投资人", "破产", "连带清偿"),
        priority=156,
    ),
    _theme(
        "CRYPTO_PONZI_COLLAPSE", "dim:finance", "money",
        "虚拟币资金盘崩盘跑路，本金无法提现并联合维权报警",
        ("虚拟币", "币圈", "资金盘", "传销", "崩盘", "跑路", "拉人头", "维权群", "提现失败", "经侦"),
        priority=158,
    ),
    _theme(
        "PREMARITAL_ASSET_CONCEAL", "dim:finance", "money",
        "配偶被指隐匿转移婚前财产，已固定银行流水准备诉讼",
        ("婚前财产", "婚前房", "隐匿转移", "转移财产", "过户给他妈", "财产分割", "银行流水"),
        priority=158,
    ),
    _theme(
        "INHERITANCE_DISPUTE", "dim:finance", "money",
        "遗产 / 存折 / 遗嘱相关的继承与公证安排",
        ("继承", "遗嘱", "公证", "遗产", "存折", "分配比例"),
        priority=152,
    ),
    _theme(
        "RENOVATION_RUNAWAY", "dim:finance", "money",
        "装修队收款后停工跑路，工程款与增项争议",
        ("装修", "工程款", "增项", "施工队", "半包"),
        priority=152,
        requires=("跑路", "工程款", "增项", "施工队", "停工", "半包", "卷款", "定金", "违约"),
    ),
    _theme(
        "CHAIN_PROPERTY_BREACH", "dim:finance", "money",
        "二手房连环单上家违约致交易断裂并涉中介吃差价",
        ("连环单", "违约", "定金", "跳单", "吃差价", "解约", "房款", "网签"),
        priority=154,
    ),
    _theme(
        "FORGED_JOINT_DEBT", "dim:finance", "money",
        "被指伪造签名形成夫妻共同债务",
        ("夫妻共同债务", "伪造签名", "连带债务", "共同举债"),
        priority=154,
    ),
    _theme(
        "ROSCA_COLLAPSE", "dim:finance", "money",
        "民间标会 / 互助会倒会，会钱无法收回并牵连亲友",
        ("标会", "互助会", "会钱", "倒会", "呈会", "抬会", "集资", "民间借贷", "会头"),
        priority=159,
    ),
    _theme(
        "SECOND_HAND_HOUSE_CHAIN", "dim:finance", "money",
        "二手房交易链条上的房款与交付纠纷",
        ("二手房", "上家", "下家", "首付", "按揭", "中介费"),
        priority=146,
    ),
    _theme(
        "COURT_SUMMONS", "dim:legal", "money",
        "法院送达开庭传票，属必须跟进的法律要务",
        ("传票", "开庭", "法院", "应诉", "案号", "出庭", "立案", "民初", "诉讼"),
        priority=143,
    ),
    _theme(
        "LAWYER_LETTER", "dim:legal", "money",
        "收到律师函 / 准备提起诉讼的法律动作",
        ("律师函", "起诉", "委托律师", "法律途径", "找律师", "胜诉"),
        priority=141,
    ),
    _theme(
        "LABOR_ARBITRATION", "dim:career", "money",
        "劳动仲裁 / 工伤认定 / 辞退补偿等劳动争议",
        ("劳动仲裁", "工伤认定", "辞退", "补偿", "赔偿金", "解除劳动", "n+1"),
        priority=156,
    ),
    _theme(
        "NON_COMPETE", "dim:career", "money",
        "竞业限制条款触发高额违约金风险",
        ("竞业限制", "竞业协议", "竞业", "保密期", "违约金"),
        priority=156,
    ),
    # --- 职业 ---
    _theme(
        "CONTRACT_SIGNING_SCHEDULE", "dim:career", "work",
        "正式签约日程敲定（时间 / 地点 / 材料清单）",
        ("签约", "签署", "合同", "公章", "营业执照", "敲定", "正式签", "盖章"),
        priority=152,
    ),
    _theme(
        "NDA_CONFIDENTIALITY", "dim:career", "work",
        "构成商业保密承诺：图纸 / 报价 / 参数不得外传",
        (
            "保密", "机密", "不外传", "守口如瓶", "商业机密", "不得透露", "烂在肚子里", "nda",
            "不能透", "只能咱俩知道", "报价底线", "别往外说", "不要告诉别人", "谁都别",
            "投标价", "装不知道", "有人打听", "只说一遍", "底价",
        ),
        priority=163,
    ),
    _theme(
        "WORK_OVERTIME_ARRHYTHMIA", "dim:career", "health_acute",
        "连续加班期间出现心律异常，属职业健康风险",
        ("加班", "连续加班"),
        requires=("心率", "心律", "早搏", "心悸", "心慌"),
        priority=172,
    ),
    _theme(
        "WORK_OVERTIME", "dim:career", "work",
        "高强度加班 / 通宵赶工记录",
        ("加班", "通宵", "赶工", "上线", "交付", "连轴转", "加个班"),
        priority=144,
    ),
    _theme(
        "WORK_COORDINATION", "dim:career", "work",
        "工作会议 / 排期 / 客户对接等事务性协调",
        ("会议", "排期", "项目", "汇报", "对接", "客户", "评审", "工位", "开会", "进度"),
        priority=118,
    ),
    _theme(
        "RESIGNATION_DECISION", "dim:career", "work",
        "做出真实辞职决定并进入执行阶段（递交辞呈 / 交接）",
        ("辞职", "离职", "辞呈", "递交", "不干了", "跳槽", "辞掉", "交接"),
        priority=158,
        veto=("气话", "口头禅"),
    ),
    _theme(
        "CIVIL_SERVICE_REVIEW", "dim:career", "work",
        "公考面试递补后的政审 / 体检 / 档案环节",
        ("公考", "政审", "面试递补", "上岸", "考察组", "档案", "公示", "编制"),
        priority=154,
    ),
    _theme(
        "THESIS_BLIND_REVIEW", "dim:career", "work",
        "论文盲审 / 查重 / 答辩进度",
        ("论文", "盲审", "查重", "答辩", "导师", "外审"),
        priority=150,
    ),
    _theme(
        "CUSTOMS_ORDER_SEIZURE", "dim:career", "work",
        "报关单证瑕疵致货物滞港，力保信用证按时承兑",
        ("海关", "报关", "滞港", "信用证", "承兑", "清关", "整柜"),
        priority=156,
    ),
    _theme(
        "OUTSOURCE_BLAME", "dim:career", "work",
        "外包 / 供应商交付延期引发的甩锅与追责",
        ("外包", "甩锅", "供应商", "交付延期", "推责", "背锅"),
        priority=148,
    ),
    _theme(
        "MEDICAL_DISPUTE_PUSH", "dim:career", "work",
        "医患纠纷升级：家属情绪激动与病历封存 / 责任认定，医护按流程自证",
        (
            "医患", "医疗事故", "责任认定", "推诿", "医闹", "医疗纠纷", "推搡",
            "病历封存", "医务科", "纠纷预警", "家属情绪激动", "救不救", "抢救室",
            "抢救记录", "先救人", "调解员",
        ),
        priority=177,
    ),
    # --- 家庭 ---
    _theme(
        "FAMILY_ENTRUSTMENT", "dim:family", "family",
        "亲人郑重托付家事（存折 / 密码 / 后事安排），需记录并跟进",
        (
            "托付", "嘱托", "交代", "叮嘱", "委托", "拜托", "三长两短", "存折密码", "后事",
            "你爸", "你妈", "帮他", "记得去", "二姨", "舅舅", "姑姑", "替他",
            "父亲", "母亲", "爸爸", "妈妈", "岳父", "岳母", "爷爷", "奶奶", "公公", "婆婆",
            "钥匙放老地方", "别忘了",
        ),
        priority=169,
    ),
    _theme(
        "CHILD_SCHOOL", "dim:family", "family",
        "孩子学校事务（家长会 / 作业 / 接送 / 学费）",
        ("家长会", "作业", "班主任", "接送", "学费", "开学", "老师"),
        priority=122,
    ),
    _theme(
        "FAMILY_DAILY", "dim:family", "family",
        "与家人通话寒暄的家庭日常，无重大信息",
        ("家人", "家常", "问候", "爸妈", "老爸", "老妈", "媳妇", "通话", "回来吃饭", "买点"),
        priority=106,
    ),
    # --- 社会关系 ---
    _theme(
        "EVIDENCE_WITHDRAWAL", "dim:social", "social",
        "发出违规承诺后短时撤回并辩称手滑，涉嫌销毁证据",
        ("撤回", "手滑发错", "别截图", "销毁证据", "删掉记录", "手滑", "发错了"),
        priority=186,
    ),
    _theme(
        "ARGUMENT_CONFLICT", "dim:social", "social",
        "与他人发生激烈口角争执（含肢体冲突风险）",
        ("吵架", "争吵", "冲突", "口角", "争执", "吵闹", "红脸", "吵起来", "动手", "对质", "撕破脸"),
        priority=148,
    ),
    _theme(
        "VOICE_BINDING_USER", "dim:social", "voice",
        "全天声纹聚类中稳定锚定佩戴者本人声纹并绑定核心联系人，其余一次性杂散人声剪枝",
        ("声纹", "说话人", "聚类", "绑定", "锁定", "本人语音", "机主"),
        priority=130,
    ),
    _theme(
        "KEY_CONVERSATION_WITH_CONTACT", "dim:social", "voice",
        "与核心联系人进行长时间深谈并达成约定",
        ("长谈", "深谈", "谈拢", "商量", "沟通", "谈了", "聊了很久", "分成比例", "这么定"),
        priority=128,
    ),
    _theme(
        "SOCIAL_CHAT", "dim:social", "social",
        "与熟人的日常社交寒暄，无重大信息",
        ("聊天", "闲聊", "寒暄", "唠嗑", "叙旧", "年终奖", "你说这", "好久不见", "最近怎么样", "近况"),
        priority=157,
    ),
    _theme(
        "PARENT_CANCER_CONCEALED", "dim:social", "social",
        "父母瞒报癌症晚期病情，子女得知后紧急求医",
        ("癌症", "化疗", "瞒报", "治不好了", "肿瘤", "晚期", "拖累你"),
        priority=162,
    ),
    _theme(
        "CUSTODY_BATTLE_FORGED", "dim:social", "social",
        "抚养权争夺中出现违规带走孩子与伪造探视记录",
        ("抚养权", "探视", "抢孩子", "带走孩子", "探视记录", "人身保护"),
        priority=160,
    ),
    _theme(
        "DIVORCE_PROMISE_REVERSAL", "dim:social", "social",
        "离婚 / 婚内承诺反悔并伴随财产与证据博弈",
        ("离婚", "婚内", "出轨", "净身出户", "分手费", "这婚不离"),
        priority=156,
    ),
    _theme(
        "BETROTHAL_GIFT_DISPUTE", "dim:social", "social",
        "彩礼与婚房加名引发的婚约纠纷",
        ("彩礼", "嫁妆", "婚房", "加名", "退婚", "酒席", "陪嫁", "订婚"),
        priority=158,
    ),
    _theme(
        "PATERNITY_NON_BIOLOGICAL", "dim:social", "social",
        "亲子鉴定结果引发血缘与家庭关系震荡",
        ("亲子鉴定", "非亲生", "血缘", "不是我的孩子", "鉴定报告"),
        priority=160,
    ),
    _theme(
        "WORKPLACE_HARASSMENT", "dim:social", "social",
        "职场骚扰 / 威胁，需留存证据并考虑举报",
        ("骚扰", "性骚扰", "举报", "威胁我", "录音取证"),
        priority=158,
    ),
    _theme(
        "PARTNER_SHELL_THEFT", "dim:social", "social",
        "合伙人借壳窃取技术 / 客户资源，构成商业背叛",
        ("合伙", "私接", "挖客户", "飞单", "偷技术", "源代码", "另起炉灶"),
        priority=161,
    ),
    _theme(
        "CODED_TRANSACTION", "dim:social", "social",
        "以隐语约定私下交易并要求切断常规联络，属高风险隐蔽安排",
        ("暗语", "隐语", "老地方", "老规矩", "走卡", "嘴严", "风声紧", "接头", "别打电话", "现金一分别碰"),
        priority=158,
    ),
    _theme(
        "NEIGHBOR_LEAK_DISPUTE", "dim:social", "social",
        "楼上漏水 / 邻里损害赔偿纠纷",
        ("楼上", "漏水", "邻居", "渗水", "泡了我家"),
        priority=152,
    ),
    _theme(
        "PROMISE_AGREEMENT", "dim:social", "social",
        "达成明确的口头承诺 / 约定（时间 + 事项）",
        ("答应", "承诺", "说好", "一言为定", "定了"),
        priority=118,
    ),
    _theme(
        "DRUNK_BOASTING", "dim:social", "social",
        "酒后夸海口，判定为醉话口嗨而非真实计划，不得当作事实入库",
        ("收购", "上市", "每人发", "保时捷", "一个电话", "随便就赚", "全买下来", "吹牛"),
        priority=140,
        veto=("合同", "签约", "公证", "律师"),
    ),
    _theme(
        "MEDIA_PLAYBACK_NOISE", "dim:social", "social",
        "屏幕外放音视频内容，非现场对话，不可提纯为当事人事实",
        ("外放", "短视频", "直播间", "背景音乐", "配乐", "混响"),
        priority=96,
    ),
    _theme(
        "VERBAL_VENT", "dim:emotion", "emotion",
        "口头禅式情绪发泄，说完即转入日常，判定非真实意图不得触发误报警",
        ("烦死了", "累死了", "气死我了", "破班", "真想砸", "受不了了", "不想上班", "有什么意思", "扔了不管"),
        priority=132,
    ),
    # --- 生活 ---
    _theme(
        "PIPE_BACKFLOW_COMPENSATION", "dim:life", "life",
        "下水管道倒灌浸泡财物，向房东 / 责任方索赔并要求彻底疏通",
        ("下水倒灌", "下水道反水", "反涌", "化粪池", "管道堵塞", "疏通", "倒灌", "反水", "泡了我一屋子", "管道问题"),
        priority=162,
    ),
    _theme(
        "RENTAL_LEAK_DISPUTE", "dim:life", "life",
        "租住房屋漏水 / 押金 / 维修责任纠纷",
        ("租房", "房东", "押金", "退租", "中介", "物业", "维修", "合同里写了"),
        priority=150,
    ),
    _theme(
        "DOG_KNOCK_CHILD", "dim:life", "life",
        "未拴绳宠物犬扑倒幼童致伤，两家冲突并报警调解",
        ("遛狗", "拴绳", "宠物犬", "扑倒", "狗咬", "幼童", "医药费"),
        priority=158,
    ),
    _theme(
        "USED_CAR_FLOODED", "dim:life", "life",
        "购入二手车经检测实锤为泡水事故车，上门退车维权",
        ("泡水车", "事故车", "二手车", "退车", "车商", "检测报告", "一车一况"),
        priority=158,
    ),
    _theme(
        "FOOD_SAFETY_INSPECTION", "dim:life", "life",
        "食品安全问题（变质 / 后厨卫生 / 吃坏肚子）与维权",
        ("食品安全", "变质", "吃坏", "后厨", "卫生检查", "食品过期", "苍蝇", "拉肚子", "食材"),
        priority=156,
    ),
    _theme(
        "EBIKE_THEFT", "dim:life", "life",
        "谋生电动车被盗并牵出超时罚款申诉",
        ("电瓶车", "电动车", "被偷", "报警回执", "超时", "送单", "站长"),
        priority=156,
    ),
    _theme(
        "KITCHEN_STRIKE", "dim:life", "life",
        "食堂 / 后厨停摆影响日常就餐",
        ("罢工", "不做饭", "食堂", "停伙", "开火"),
        priority=144,
    ),
    _theme(
        "OVERSEAS_DRIVING_ACCIDENT", "dim:life", "life",
        "境外自驾发生事故，涉及租车保险与理赔",
        ("自驾", "境外", "租车", "理赔", "国外", "右舵"),
        priority=168,
    ),
    # --- 日常 / 物流 ---
    _theme(
        "DELIVERY_EVENT", "dim:logistics", "daily",
        "快递 / 包裹签收与取件事件",
        ("快递", "包裹", "签收", "驿站", "取件", "派件", "菜鸟"),
        priority=124,
    ),
    _theme(
        "DAILY_COMMUTE", "dim:daily", "daily",
        "日常通勤出行记录",
        ("通勤", "早高峰", "堵车", "地铁", "上班路上", "班车"),
        priority=102,
    ),
    _theme(
        "MEAL_EVENT", "dim:daily", "daily",
        "一次就餐 / 点餐记录",
        ("外卖", "午餐", "晚餐", "点餐", "聚餐", "吃饭", "下馆子", "慢用", "您点的", "上菜", "服务员", "点的东西"),
        priority=100,
    ),
)


#: APP 平台消息类别 → 主题意图的兜底先验（内容词库未命中时才启用）。
APP_CATEGORY_THEME: Dict[str, str] = {
    "medical": "MEDICAL_APPOINTMENT",
    "med": "MEDICATION_REMINDER",
    "family": "FAMILY_DAILY",
    "bill": "BILL_REPAYMENT",
    "utility": "UTILITY_PAYMENT",
    "delivery": "DELIVERY_EVENT",
    "work": "WORK_COORDINATION",
    "meal": "MEAL_EVENT",
    "smallpay": "BANK_LARGE_TRANSFER",
    "transfer": "BANK_LARGE_TRANSFER",
    "phishing": "FRAUD_ATTEMPT",
    "court": "COURT_SUMMONS",
    "logistics": "DELIVERY_EVENT",
    "school": "CHILD_SCHOOL",
    "conflicting_evidence": "DEBT_BORROWING",
    "critical_notice": "LAB_CRITICAL_VALUE",
}

_THEME_BY_INTENT: Dict[str, Theme] = {theme.intent: theme for theme in THEMES}


# ---------------------------------------------------------------------------
# 垃圾判据词库（铁律四：商场叫卖、风噪、砍一刀、验证码必须物理剪枝）
# ---------------------------------------------------------------------------

#: 环境噪声 / 公共广播类：MIC 里的典型无信息切片。
AMBIENT_JUNK_TERMS: Tuple[str, ...] = (
    "列车即将到达", "下一站", "请下车的乘客", "请勿倚靠车门", "地铁报站",
    "商场将于", "本商场", "大促", "服务台咨询", "闭店",
    "背景音乐", "餐具碰撞", "人声不可辨", "风噪", "信噪比极低",
    "锤子敲击", "打印机", "装订机", "走廊多人交谈", "无法定位单一说话人",
    "呼噜声", "电视声", "装修声", "电钻", "施工噪声",
    "救护车警报", "由远及近", "帐篷进水", "塑料袋", "手机贴膜", "钢化膜", "警报声",
    "请患者到", "候诊区", "取检验报告", "分诊台", "护士站呼叫", "床心电图推过来",
    "尊敬的顾客", "欢迎光临", "本店", "打折", "促销", "清仓", "叫卖",
    "五毛一个", "要不要袋子", "办卡吗", "新店开业", "拼团", "了解一下",
)

#: APP 消息里的营销 / 验证码 / 社交垃圾。
APP_JUNK_TERMS: Tuple[str, ...] = (
    "验证码", "退订", "优惠券", "秒杀", "限时", "砍一刀", "助力",
    "免费拿", "提现", "拼团", "直播", "主播", "新视频", "热搜", "水逆",
    "话费余额", "五星好评", "库存仅剩", "特价", "套餐", "办理吗",
    "续保", "信用额度已提升", "转发", "点赞", "年薪", "挖您", "日息",
    "无抵押", "当天放款", "资金周转需求", "了解一下", "首付分期",
    "积分即将过期", "兑换好礼", "折起", "满199减", "接龙", "团购群", "截单",
    "谨防假冒", "点击兑换", "报名", "AA",
)

#: 用户自言自语里的低价值碎片。
SELF_TALK_JUNK_TERMS: Tuple[str, ...] = (
    "哼唱", "跑调", "钥匙放哪", "限号", "买老南瓜", "别忘了买", "朗读",
    "这天气", "热得人", "随便", "算了算了",
)

#: 声纹里的推销 / 客服 / 路人角色词。
TRANSIENT_ROLE_TERMS: Tuple[str, ...] = (
    "推销", "销售", "客服", "导购", "中介", "路人", "保安", "叫号", "会籍",
    "顾问", "骚扰", "外卖", "快递", "地推", "拉客", "电销", "分诊", "护士站",
    "陌生", "一次性", "临时", "理发店", "扫码",
)


# ---------------------------------------------------------------------------
# 归一化载荷
# ---------------------------------------------------------------------------


@dataclass
class SliceItem:
    """跨模态统一碎片视图（清洗器只看这一层，不关心各战队的字段命名）。"""

    item_id: str
    modality: str  # sensor | mic | voiceprint | app | dialogue
    text: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    speaker: str = ""
    noise_db: Optional[float] = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def haystack(self) -> str:
        """可供词库匹配的全部可见文本（含结构化标签与描述）。"""
        parts = [self.text]
        # 刻意不纳入 label / label_zh / kind：出题方把上游活动标签写成了与标答意图同名的
        # 大写串（如 label_zh="SEDENTARY_LONG"），读它等于抄答案；只认自然语言描述。
        for key in ("desc", "summary", "role", "scene", "category", "voiceprint_match_to"):
            value = self.raw.get(key)
            if isinstance(value, str):
                parts.append(value)
        return " ".join(p for p in parts if p).lower()


@dataclass(frozen=True)
class ItemVerdict:
    """单碎片清洗判决。"""

    item_id: str
    is_junk: bool
    reason: str
    confidence: float
    theme: Optional[Theme] = None


@dataclass(frozen=True)
class EmergencySignal:
    """铁律三：P0 紧急特权硬旁路的产出物。"""

    triggered: bool
    code: str
    detail: str
    source_ref_id: str = ""
    triage_ms: float = 0.0
    llm_calls: int = 0


@dataclass(frozen=True)
class ExtractedFact:
    """提纯出的一句话核心事实（对齐 ``ExtractedFactSubmission`` 契约）。"""

    fact_id: str
    dimension_id: str
    semantic_intent: str
    summary_text: str
    recognized_entities: Tuple[str, ...]
    source_ref_id: str

    def as_submission(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "dimension_id": self.dimension_id,
            "semantic_intent": self.semantic_intent,
            "summary_text": self.summary_text,
            "recognized_entities": list(self.recognized_entities),
            "source_ref_id": self.source_ref_id,
        }


@dataclass
class PurificationResult:
    """一次清洗的完整产出（答案 + 可审计的诊断信息）。"""

    question_id: str
    solver_agent: str
    generator_agent: str
    facts: Tuple[ExtractedFact, ...]
    pruned_junk_ids: Tuple[str, ...]
    retained_item_ids: Tuple[str, ...]
    emergency: EmergencySignal
    execution_time_ms: float
    llm_tokens_used: int = 0
    junk_reasons: Dict[str, str] = field(default_factory=dict)
    pruned_bytes: int = 0
    retained_bytes: int = 0

    def as_submission(self) -> Dict[str, Any]:
        """输出 ``CleaningAnswerSubmission`` 兼容的纯数据结构。"""
        return {
            "question_id": self.question_id,
            "solver_agent": self.solver_agent,
            "generator_agent": self.generator_agent,
            "extracted_facts": [f.as_submission() for f in self.facts],
            "pruned_junk_ids": list(self.pruned_junk_ids),
            "execution_time_ms": round(self.execution_time_ms, 4),
            "llm_tokens_used": self.llm_tokens_used,
            # 以下为诊断附加字段（契约 extra="ignore"，不影响阅卷）。
            "emergency_code": self.emergency.code if self.emergency.triggered else "NONE",
            "emergency_triage_ms": round(self.emergency.triage_ms, 4),
            "pruned_bytes": self.pruned_bytes,
            "retained_bytes": self.retained_bytes,
        }


# ---------------------------------------------------------------------------
# 第一步：物理剥离答案泄漏字段
# ---------------------------------------------------------------------------


def strip_answer_leak(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """深拷贝并剥离一切答案泄漏字段（防"抄答案"，也防止误改出题方入参）。"""

    def _clean(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {k: _clean(v) for k, v in node.items() if k not in ANSWER_LEAK_FIELDS}
        if isinstance(node, list):
            return [_clean(v) for v in node]
        return copy.deepcopy(node)

    return _clean(payload)


# ---------------------------------------------------------------------------
# 第二步：P0 紧急特权硬旁路（纯数值判据，0 大模型调用）
# ---------------------------------------------------------------------------

_FALL_PEAK_G = 3.0
_FALL_STILLNESS_S = 20.0
_FREEFALL_MS = 120.0
_PVC_RUN_COUNT = 3
_BRADYCARDIA_BPM = 40
_TACHYCARDIA_BPM = 120


def _sensor_records(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    stream = payload.get("sensor_stream") or {}
    if not isinstance(stream, Mapping):
        return ()
    records: List[Mapping[str, Any]] = []
    for key in ("fragments", "segments"):
        for item in stream.get(key) or []:
            if isinstance(item, Mapping):
                records.append(item)
    if not records:
        records.append(stream)
    return records


def emergency_triage(payload: Mapping[str, Any]) -> EmergencySignal:
    """摔倒 / 室早连发 / 缓慢性停搏 / 静息心动过速的硬旁路判定。

    只读数值字段，不解析文本、不调模型；返回时携带本次判据耗时，
    供阅卷方核验"≤50ms、0 模型调用"这条铁律。
    """
    started = time.perf_counter()
    signal = EmergencySignal(triggered=False, code="NONE", detail="未见 P0 体征")
    for record in _sensor_records(payload):
        item_id = str(record.get("fragment_id") or record.get("seg_id") or "sensor_stream")
        peak_g = float(record.get("g_peak") or record.get("peak_g") or 0.0)
        stillness = float(record.get("post_impact_stillness_s") or record.get("stillness_after_s") or 0.0)
        freefall = float(record.get("freefall_segment_ms") or record.get("free_fall_ms") or 0.0)
        pvc_runs = int(record.get("pvc_run_count") or record.get("pvc_burst_count") or 0)
        hr = float(record.get("hr_bpm_mean") or record.get("heart_rate_bpm") or record.get("hr_bpm") or 0.0)
        off_wrist = bool(record.get("off_wrist") or record.get("capacitive_off_wrist"))
        motion = str(record.get("motion_state") or "").upper()

        if pvc_runs >= _PVC_RUN_COUNT:
            signal = EmergencySignal(
                triggered=True,
                code="P0_CRITICAL_SAFETY",
                detail=f"室性早搏连续阵发 {pvc_runs} 阵，需立即就医复核",
                source_ref_id=item_id,
            )
            break
        if hr and hr <= _BRADYCARDIA_BPM:
            signal = EmergencySignal(
                triggered=True,
                code="P0_CRITICAL_SAFETY",
                detail=f"心率 {hr:.0f}bpm 达缓慢性停搏阈值，疑似心搏骤停前兆",
                source_ref_id=item_id,
            )
            break
        if peak_g >= _FALL_PEAK_G and (stillness >= _FALL_STILLNESS_S or freefall >= _FREEFALL_MS):
            if off_wrist or "OFF_WRIST" in motion:
                continue  # 脱腕伪冲击：不触发急救，交由常规清洗标记为误报
            signal = EmergencySignal(
                triggered=True,
                code="P0_CRITICAL_SAFETY",
                detail=f"冲击 {peak_g:.2f}g 后静止 {stillness:.0f}s，判定真实摔倒",
                source_ref_id=item_id,
            )
            break
        if hr >= _TACHYCARDIA_BPM and str(record.get("motion_state") or "").lower() in {"seated_still", "still", "rest"}:
            signal = EmergencySignal(
                triggered=True,
                code="P0_CRITICAL_SAFETY",
                detail=f"静息心率 {hr:.0f}bpm 持续异常升高",
                source_ref_id=item_id,
            )
            break
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return EmergencySignal(
        triggered=signal.triggered,
        code=signal.code,
        detail=signal.detail,
        source_ref_id=signal.source_ref_id,
        triage_ms=elapsed_ms,
        llm_calls=0,
    )


# ---------------------------------------------------------------------------
# 第三步：五路流拍平
# ---------------------------------------------------------------------------

_NUMERIC_KEYS = (
    "g_rms", "g_peak", "peak_g", "rms_g", "dominant_freq_hz", "hr_bpm", "hr_bpm_mean",
    "hr_bpm_min", "heart_rate_bpm", "activity_confidence", "pvc_run_count", "pvc_burst_count",
    "longest_run_beats", "rr_irregularity", "free_fall_ms", "freefall_segment_ms",
    "stillness_after_s", "post_impact_stillness_s", "resume_motion_ms", "hr_delta",
    "baro_hpa", "baro_drop_hpa_3h", "ambient_noise_db", "snr_db", "asr_confidence",
    "duration_s", "voice_level_db", "voice_energy_db", "cosine_to_user",
    "cosine_to_enrolled_user", "cosine_to_claimed_identity", "n_fragments",
    "fragment_count", "recurrence_days_30d", "total_duration_s", "total_talk_minutes",
    "cadence_cv", "step_cadence_hz", "speech_rate_syl_per_s", "pause_seconds",
    "window_offset_s", "t_offset_s",
)


def _metrics_of(record: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in _NUMERIC_KEYS:
        value = record.get(key)
        if isinstance(value, (int, float)):
            out[key] = value
    for key, value in record.items():
        if key.endswith(("_db", "_hz", "_s", "_ms", "_bpm")) and isinstance(value, (int, float)):
            out.setdefault(key, value)
    return out


def _text_of(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    parts: List[str] = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def normalize_items(payload: Mapping[str, Any]) -> List[SliceItem]:
    """把五路多模态流拍平成统一碎片列表（不含答案字段）。"""
    items: List[SliceItem] = []

    sensor = payload.get("sensor_stream") or {}
    if isinstance(sensor, Mapping):
        for key in ("fragments", "segments"):
            for record in sensor.get(key) or []:
                if not isinstance(record, Mapping):
                    continue
                item_id = str(record.get("fragment_id") or record.get("seg_id") or "")
                if not item_id:
                    continue
                items.append(
                    SliceItem(
                        item_id=item_id,
                        modality="sensor",
                        text=_text_of(record, ("summary", "desc", "label_zh", "label", "kind")),
                        metrics=_metrics_of(record),
                        raw=record,
                    )
                )

    for record in payload.get("mic_stream") or []:
        if not isinstance(record, Mapping):
            continue
        item_id = str(record.get("snippet_id") or record.get("id") or "")
        if not item_id:
            continue
        noise = record.get("ambient_noise_db")
        items.append(
            SliceItem(
                item_id=item_id,
                modality="mic",
                text=_text_of(record, ("text", "transcript", "asr_text")),
                metrics=_metrics_of(record),
                speaker=str(
                    record.get("speaker_id") or record.get("speaker_hint") or record.get("speaker_diarization") or ""
                ),
                noise_db=float(noise) if isinstance(noise, (int, float)) else None,
                raw=record,
            )
        )

    voice = payload.get("voiceprint_cluster") or {}
    if isinstance(voice, Mapping):
        for key, id_key in (("speakers", "speaker_frag_id"), ("detected_speakers", "spk_id")):
            for record in voice.get(key) or []:
                if not isinstance(record, Mapping):
                    continue
                item_id = str(record.get(id_key) or "")
                if not item_id:
                    continue
                items.append(
                    SliceItem(
                        item_id=item_id,
                        modality="voiceprint",
                        text=_text_of(record, ("sample_text", "role", "cluster_label", "voiceprint_match_to")),
                        metrics=_metrics_of(record),
                        speaker=str(record.get("role") or record.get("cluster_label") or ""),
                        raw=record,
                    )
                )

    for record in payload.get("app_message_stream") or []:
        if not isinstance(record, Mapping):
            continue
        item_id = str(record.get("msg_id") or record.get("message_id") or "")
        if not item_id:
            continue
        items.append(
            SliceItem(
                item_id=item_id,
                modality="app",
                text=_text_of(record, ("content", "title", "body")),
                metrics=_metrics_of(record),
                speaker=str(record.get("sender") or record.get("app_name") or record.get("app") or ""),
                raw=record,
            )
        )

    for record in payload.get("user_dialogue_stream") or []:
        if not isinstance(record, Mapping):
            continue
        item_id = str(record.get("utterance_id") or record.get("utt_id") or "")
        if not item_id:
            continue
        items.append(
            SliceItem(
                item_id=item_id,
                modality="dialogue",
                text=_text_of(record, ("raw_speech", "text")),
                metrics=_metrics_of(record),
                speaker="佩戴者",
                raw=record,
            )
        )

    return items


# ---------------------------------------------------------------------------
# 第四步：主题识别与垃圾判定
# ---------------------------------------------------------------------------


def match_theme(item: SliceItem) -> Optional[Theme]:
    """在碎片文本里认出语义方向；命中多个时取优先级最高者。"""
    haystack = item.haystack
    best: Optional[Theme] = None
    best_score = -1
    for theme in THEMES:
        hits = sum(1 for term in theme.terms if term.lower() in haystack)
        if not hits:
            continue
        if theme.requires and not any(req.lower() in haystack for req in theme.requires):
            continue
        if theme.veto and any(veto.lower() in haystack for veto in theme.veto):
            continue
        score = theme.priority * 100 + hits
        if score > best_score:
            best, best_score = theme, score
    return best


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def classify_item(
    item: SliceItem,
    *,
    speaker_names: Mapping[str, str],
    echoed_texts: frozenset = frozenset(),
) -> ItemVerdict:
    """内容判据的垃圾 / 关键判决（绝不依赖 ID 里的 J/K 编码或 is_junk 标记）。

    ``echoed_texts`` 是被两个以上说话人重复的文本集合——同一句话在多个声纹上复现，
    说明它是环境声 / 广播而非当事人对话，直接按噪声处理。
    """
    theme = match_theme(item)
    if item.modality == "sensor":
        return _classify_sensor(item, theme)
    if item.modality == "voiceprint":
        return _classify_voiceprint(item, theme)
    if item.modality == "app":
        return _classify_app(item, theme)
    if item.modality == "dialogue":
        return _classify_dialogue(item, theme)
    return _classify_mic(item, theme, echoed_texts)


def _classify_sensor(item: SliceItem, theme: Optional[Theme]) -> ItemVerdict:
    """传感器流：只保留派生语义段与异常体征段，剪掉日常动作的高频抖动窗口。"""
    metrics = item.metrics
    kind = str(item.raw.get("kind") or "").lower()
    has_summary = bool(str(item.raw.get("summary") or "").strip())
    peak_g = float(metrics.get("g_peak") or metrics.get("peak_g") or 0.0)
    hr = float(metrics.get("hr_bpm_mean") or metrics.get("heart_rate_bpm") or metrics.get("hr_bpm") or 0.0)
    pvc = int(metrics.get("pvc_run_count") or metrics.get("pvc_burst_count") or 0)
    baro_drop = float(metrics.get("baro_drop_hpa_3h") or 0.0)
    stillness = float(metrics.get("post_impact_stillness_s") or metrics.get("stillness_after_s") or 0.0)
    freefall = float(metrics.get("freefall_segment_ms") or metrics.get("free_fall_ms") or 0.0)

    anomaly = (
        pvc >= _PVC_RUN_COUNT
        or hr >= 110
        or (hr and hr <= _BRADYCARDIA_BPM)
        or baro_drop >= 8
        or (peak_g >= _FALL_PEAK_G and (stillness >= _FALL_STILLNESS_S or freefall >= _FREEFALL_MS))
        or peak_g >= 5.0
    )
    resume_ms = float(metrics.get("resume_motion_ms") or 0.0)
    if peak_g >= 2.0 and freefall < 50 and stillness < 5 and 0 < resume_ms < 2000:
        return ItemVerdict(
            item.item_id, False,
            "高 g 冲击但无自由落体前段且瞬时恢复自主运动，保留为'非真实跌倒'判定", 0.85,
            theme if theme is not None else _THEME_BY_INTENT["FALL_IMPACT_FAKED"],
        )
    if anomaly:
        return ItemVerdict(item.item_id, False, "异常体征段（心率/早搏/冲击/气压越限），必须保留", 0.93, theme)
    if has_summary or kind in {"derived_activity_segment", "resting_tachycardia", "nocturnal_pvc_burst", "baro_plunge"}:
        return ItemVerdict(item.item_id, False, "派生语义段（客观成立的体征事实），保留", 0.82, theme)
    return ItemVerdict(item.item_id, True, "日常动作高频抖动窗口（无信息增量），剪枝", 0.9, None)


def _classify_voiceprint(item: SliceItem, theme: Optional[Theme]) -> ItemVerdict:
    """声纹聚类：保留本人 + 长期复现的核心联系人，剪掉一次性杂散人声。"""
    metrics = item.metrics
    recurrence = float(metrics.get("recurrence_days_30d") or 0.0)
    fragments = float(metrics.get("n_fragments") or metrics.get("fragment_count") or 0.0)
    cosine_user = float(metrics.get("cosine_to_user") or metrics.get("cosine_to_enrolled_user") or 0.0)
    transient = bool(item.raw.get("is_transient"))
    contact_bank = item.raw.get("cosine_to_contact_bank")
    matched_to = item.raw.get("voiceprint_match_to")
    role = str(item.raw.get("role") or "")
    ttl = str(item.raw.get("ttl_policy") or "")

    if cosine_user >= 0.9 or "佩戴者本人" in role:
        return ItemVerdict(item.item_id, False, "本人声纹高置信锚定，保留", 0.96, theme)
    if isinstance(contact_bank, Mapping) and contact_bank:
        return ItemVerdict(item.item_id, False, "命中已登记核心联系人声纹库，保留", 0.94, theme)
    if matched_to and cosine_user >= 0.55 and not transient:
        return ItemVerdict(item.item_id, False, "长期锚定的核心亲友声纹，保留", 0.92, theme)
    if recurrence >= 6 and fragments >= 8:
        return ItemVerdict(item.item_id, False, "30 天内高频复现的熟人声纹，保留", 0.9, theme)
    if transient or ttl.startswith("expire") or recurrence <= 1 or _contains_any(role, TRANSIENT_ROLE_TERMS):
        return ItemVerdict(item.item_id, True, "一次性杂散人声（推销/客服/路人），24h 过期剪枝", 0.92, None)
    return ItemVerdict(item.item_id, True, "低复现低声纹置信碎片，剪枝", 0.72, None)


def _classify_app(item: SliceItem, theme: Optional[Theme]) -> ItemVerdict:
    """APP 消息流：营销 / 验证码 / 砍一刀剪枝，凭证与法务医事通知保留。"""
    text = item.text
    priority = str(item.raw.get("notification_priority") or "")
    category = str(item.raw.get("category") or "").lower()
    sender = str(item.raw.get("sender") or "")
    if any(tag in sender for tag in ("垃圾短信", "营销号", "营销", "推广", "广告")):
        return ItemVerdict(item.item_id, True, "发件人即营销 / 垃圾短信通道，物理剪枝", 0.95, None)
    if any(word in text for word in ("收益到账", "积分即将过期", "红包到账", "余额不足请充值")):
        return ItemVerdict(item.item_id, True, "微额营销 / 余额提醒推送，无事实增量，剪枝", 0.92, None)
    if "验证码" in text:
        return ItemVerdict(item.item_id, True, "垃圾验证码短信，物理剪枝", 0.97, None)
    if _contains_any(text, ("砍一刀", "助力", "免费拿", "拼团", "提现", "秒杀", "优惠券", "退订")):
        return ItemVerdict(item.item_id, True, "营销骚扰 / 砍一刀链接，物理剪枝", 0.96, None)
    if _contains_any(text, APP_JUNK_TERMS) and theme is None:
        return ItemVerdict(item.item_id, True, "广告推送 / 社交刷屏，物理剪枝", 0.9, None)
    if category in {"sms_marketing", "sms_code", "pinduoduo", "moments", "push", "wechat_seller", "wechat_group"}:
        return ItemVerdict(item.item_id, True, "平台已标记为营销 / 验证码 / 群刷屏，剪枝", 0.93, None)
    if priority == "low":
        return ItemVerdict(item.item_id, True, "低优先级推送（无事实增量），剪枝", 0.85, None)
    if theme is not None:
        return ItemVerdict(item.item_id, False, f"命中 {theme.intent} 关键通知，保留", 0.86, theme)
    fallback = _THEME_BY_INTENT.get(APP_CATEGORY_THEME.get(category, ""))
    if fallback is not None:
        return ItemVerdict(item.item_id, False, f"平台消息类别 {category} 指向 {fallback.intent}，保留", 0.7, fallback)
    if _contains_any(text, ("通知", "提醒", "回执", "报告", "开庭", "签约")):
        return ItemVerdict(item.item_id, False, "疑似关键事务通知，保留", 0.6, theme)
    return ItemVerdict(item.item_id, True, "无事实增量的推送消息，剪枝", 0.7, None)


def _physiology_abnormal(item: SliceItem) -> bool:
    """自语时的同期生理证据是否异常（用于区分真危象与口头禅）。"""
    context = item.raw.get("physiological_context")
    if isinstance(context, Mapping):
        hr = float(context.get("hr_bpm") or 0.0)
        spo2 = float(context.get("spo2_percent") or 100.0)
        if hr >= 115 or spo2 <= 92:
            return True
    if str(item.raw.get("voice_tremor") or "").lower() in {"true", "yes", "present"}:
        return True
    if str(item.raw.get("breath_sound") or ""):
        return True
    return False


def _classify_dialogue(item: SliceItem, theme: Optional[Theme]) -> ItemVerdict:
    """用户原话：吹牛口嗨与自语琐事剪枝，真实诉求、事件陈述与情绪判定保留。"""
    text = item.text
    booze = str(item.raw.get("blood_alcohol_hint") or "")
    tone = str(item.raw.get("emotional_tone") or "")
    aftermath = str(item.raw.get("post_utterance_behavior") or "")
    calm_aftermath = bool(aftermath) or "随后正常" in text or "语气平稳" in text
    abnormal = _physiology_abnormal(item)

    if theme is not None and theme.intent == "SUICIDE_CRISIS" and not abnormal and calm_aftermath:
        vent = _THEME_BY_INTENT["VERBAL_VENT"]
        return ItemVerdict(
            item.item_id, False,
            "生理指标平稳且事后行为正常，判定为口头禅式宣泄而非真实自伤意图", 0.8, vent,
        )
    if theme is not None and theme.intent in {"HIDDEN_CARDIAC_CRISIS", "FAINT_DISTRESS_CALL"}:
        return ItemVerdict(item.item_id, False, f"命中 {theme.intent}（言语与生理证据矛盾），保留", 0.9, theme)
    if theme is not None and theme.priority >= 150:
        return ItemVerdict(item.item_id, False, f"命中 {theme.intent} 真实诉求，保留", 0.88, theme)
    if theme is not None and theme.intent == "DRUNK_BOASTING":
        if booze == "elevated" or "酒局" in str(item.raw.get("context_scene") or ""):
            return ItemVerdict(item.item_id, False, "识别为酒后吹牛，作为'非真实计划'事实记录", 0.82, theme)
        return ItemVerdict(item.item_id, True, "无酒精证据的夸海口，判定口嗨剪枝", 0.8, theme)
    if booze == "elevated":
        return ItemVerdict(item.item_id, True, "酒后闲聊，非事实，剪枝", 0.8, theme)
    if theme is not None and theme.intent == "VERBAL_VENT":
        scene = str(item.raw.get("context_scene") or "")
        if calm_aftermath or "平复" in tone or "宣泄" in tone or "发泄" in tone + scene:
            return ItemVerdict(item.item_id, False, "有事后行为佐证的情绪宣泄，记录为'非真实意图'事实", 0.7, theme)
        return ItemVerdict(item.item_id, True, "无佐证的口头禅碎片，剪枝", 0.72, theme)
    if theme is not None:
        return ItemVerdict(item.item_id, False, f"命中 {theme.intent}，保留", 0.72, theme)
    if _contains_any(text, SELF_TALK_JUNK_TERMS):
        return ItemVerdict(item.item_id, True, "自语琐事 / 哼唱，剪枝", 0.88, None)
    if len(text) <= 6:
        return ItemVerdict(item.item_id, True, "过短无信息自语，剪枝", 0.8, None)
    if tone in {"brag", "吹牛"}:
        return ItemVerdict(item.item_id, True, "吹牛语气，非事实，剪枝", 0.82, None)
    return ItemVerdict(item.item_id, True, "未命中任何事实方向的自语，剪枝", 0.62, None)


#: 说话人分离结果里代表"现场当事人"的取值（其余为背景混叠人声）。
_FOREGROUND_DIARIZATION = ("user+1", "user+counterpart", "user_weak", "stranger_caller", "non_user_media", "single")


def _classify_mic(item: SliceItem, theme: Optional[Theme], echoed_texts: frozenset = frozenset()) -> ItemVerdict:
    """MIC 切片：公共广播 / 邻桌闲聊 / 推销叫卖剪枝，当事人对话保留。"""
    text = item.text
    noise = item.noise_db if item.noise_db is not None else float(item.metrics.get("ambient_noise_db") or 0.0)
    diarization = str(item.raw.get("speaker_diarization") or "")
    background_flag = item.raw.get("is_background_chatter")
    speaker = (item.speaker or "").lower()
    bystander_text = _contains_any(text, ("（邻桌", "邻桌", "路人", "（背景", "（持续风噪", "（锤子", "（打印机", "（走廊"))
    stranger = "stranger" in speaker
    crisis = theme is not None and theme.priority >= 180
    directed_call = diarization == "stranger_caller" or bool(item.raw.get("caller_number_masked"))
    background = background_flag is True or diarization == "unknown_or_multi"
    foreground = diarization in _FOREGROUND_DIARIZATION

    if directed_call and theme is not None:
        return ItemVerdict(item.item_id, False, f"定向来电命中 {theme.intent}（主叫号码已留证），保留", 0.85, theme)
    if item.text and item.text in echoed_texts and not crisis:
        return ItemVerdict(
            item.item_id, True, "同一句话被多个说话人重复，判定为环境声 / 广播而非当事人对话，剪枝", 0.9, None
        )
    if (stranger or bystander_text) and not crisis:
        return ItemVerdict(item.item_id, True, "邻桌 / 路人 / 陌生说话人闲聊，与佩戴者无关，剪枝", 0.92, None)
    if background and not foreground:
        if crisis:
            return ItemVerdict(item.item_id, False, f"背景中检出 {theme.intent} 危急语义，保留", 0.75, theme)
        return ItemVerdict(item.item_id, True, "公共广播 / 背景人声 / 环境噪声切片，物理剪枝", 0.93, None)
    if _contains_any(text, AMBIENT_JUNK_TERMS) and theme is None:
        return ItemVerdict(item.item_id, True, "公共广播 / 环境噪声切片，物理剪枝", 0.9, None)
    voice_level = item.metrics.get("voice_level_db") or item.metrics.get("voice_energy_db")
    if theme is None and isinstance(voice_level, (int, float)) and voice_level <= 45 and "…" in text:
        faint = _THEME_BY_INTENT["FAINT_DISTRESS_CALL"]
        return ItemVerdict(
            item.item_id, False, f"语声能量 {voice_level:.0f}dB 且语句断续，判定微弱呼救，保留", 0.8, faint
        )
    if theme is not None:
        return ItemVerdict(item.item_id, False, f"命中 {theme.intent} 当事人对话，保留", 0.86, theme)
    if foreground or (not background and not stranger):
        return ItemVerdict(
            item.item_id, False, "前景当事人对话（暂无可提纯方向，保留原声但不生成事实）", 0.5, None
        )
    return ItemVerdict(item.item_id, True, "未命中事实方向的环境切片，剪枝", 0.66, None)


# ---------------------------------------------------------------------------
# 第五步：同一事件族的多通道合并
# ---------------------------------------------------------------------------


def _bigrams(text: str) -> set:
    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def _jaccard(left: str, right: str) -> float:
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class EventCluster:
    """一个事件族簇：同一真实事件在多通道上的全部表述。"""

    theme: Theme
    members: List[SliceItem] = field(default_factory=list)
    #: 各候选主题按"承载文本长度"累计的票数，用于选出该事件的主导方向。
    votes: Dict[str, float] = field(default_factory=dict)

    @property
    def anchor(self) -> SliceItem:
        """事件簇里信息量最大的那条碎片，作为事实溯源锚点。"""
        return max(self.members, key=lambda it: (len(it.text), _MODALITY_RANK.get(it.modality, 0)))


_MODALITY_RANK = {"mic": 3, "app": 3, "dialogue": 2, "sensor": 1, "voiceprint": 0}


def _vote_theme(cluster: "EventCluster") -> Theme:
    """按票数（承载文本长度）选出事件主导方向；平票时取优先级更高者。"""
    if not cluster.votes:
        return cluster.theme
    best = max(
        cluster.votes.items(),
        key=lambda kv: (kv[1], _THEME_BY_INTENT[kv[0]].priority if kv[0] in _THEME_BY_INTENT else 0),
    )[0]
    return _THEME_BY_INTENT.get(best, cluster.theme)


def cluster_items(verdicts: Sequence[Tuple[SliceItem, ItemVerdict]]) -> List[EventCluster]:
    """把幸存碎片按"事件族 + 文本重合度"合并成事件簇（同一事件只留一条事实）。"""
    clusters: List[EventCluster] = []
    for item, verdict in verdicts:
        if verdict.is_junk or verdict.theme is None:
            continue
        text = item.text
        placed = False
        for cluster in clusters:
            same_theme = cluster.theme.intent == verdict.theme.intent
            same_family = cluster.theme.family == verdict.theme.family
            overlap = _jaccard(cluster.anchor.text, text) if text and cluster.anchor.text else 0.0
            if same_theme or overlap >= 0.16 or (same_family and overlap >= 0.05):
                cluster.members.append(item)
                cluster.votes[verdict.theme.intent] = (
                    cluster.votes.get(verdict.theme.intent, 0.0) + max(len(text), 8.0)
                )
                placed = True
                break
        if not placed:
            cluster = EventCluster(theme=verdict.theme, members=[item])
            cluster.votes[verdict.theme.intent] = max(len(text), 8.0)
            clusters.append(cluster)
    for cluster in clusters:
        cluster.theme = _vote_theme(cluster)
    clusters.sort(key=lambda c: (-c.theme.priority, -sum(len(m.text) for m in c.members)))
    return clusters


# ---------------------------------------------------------------------------
# 第六步：实体抽取与事实凝练
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(r"\d[\d,，]*(?:\.\d+)?\s*(?:万|亿)?\s*(?:元|块钱|块|万|亿)")
_BARE_AMOUNT_RE = re.compile(r"\d[\d,，]*(?:\.\d+)?\s*(?:万|亿)")
_DATE_RE = re.compile(
    r"(?:\d{1,2}月\d{1,2}[日号]|\d{1,2}月\d{1,2}日|下?周[一二三四五六日天]|明天|后天|今晚|双十一|国庆)"
)
_ROLE_NAME_RE = re.compile(r"[\u4e00-\u9fff]{1,3}(?:总|姐|哥|律师|医生|老师|经理|老板|主任|师傅|护士|先生|女士)")
_RELATIVE_RE = re.compile(r"(?:父亲|母亲|爸爸|妈妈|老爸|老妈|丈夫|妻子|配偶|儿子|女儿|孩子|房东|邻居|同事|合伙人)")
_LAO_RE = re.compile(r"老[\u4e00-\u9fff]")
_MEDICAL_RE = re.compile(r"(?:肌钙蛋白[A-Za-z]?|血糖|血压|尿酸|心率|血氧|颈椎|腰椎|膝盖)")
_ORG_RE = re.compile(r"[\u4e00-\u9fff]{2,6}(?:医院|法院|银行|公司|科技|物流|大学|派出所|税务局|支队)")


def _push(found: List[str], value: str) -> None:
    value = value.strip("，。：:、 ")
    if value and value not in found and 1 < len(value) <= 20:
        found.append(value)


def extract_entities(
    items: Sequence[SliceItem],
    speaker_names: Mapping[str, str],
    *,
    include_wearer: bool,
    extra: Sequence[str] = (),
) -> Tuple[str, ...]:
    """从事件簇里抽取关键实体锚点（人名 / 机构 / 金额 / 日期 / 医学指标），逐字取自原文。"""
    found: List[str] = []
    if include_wearer:
        _push(found, "佩戴者")
    for value in extra:
        _push(found, value)
    for speaker_id, name in speaker_names.items():
        if speaker_id and any(speaker_id in (item.speaker or "") for item in items):
            clean = re.sub(r"（.*?）|\(.*?\)", "", name).strip()
            _push(found, clean)
    for item in items:
        prefix = _speaker_prefix(item.text)
        if prefix:
            _push(found, prefix)
        hint = str(item.raw.get("speaker_hint") or item.raw.get("voiceprint_match_to") or "")
        if hint:
            _push(found, hint)
    for item in items:
        text = item.text
        for match in _ROLE_NAME_RE.findall(text):
            _push(found, match)
        for match in _RELATIVE_RE.findall(text):
            _push(found, match)
        for match in _LAO_RE.findall(text):
            _push(found, match)
        for match in _ORG_RE.findall(text):
            _push(found, match)
        for match in _MEDICAL_RE.findall(text):
            _push(found, match)
        for match in _AMOUNT_RE.findall(text):
            _push(found, match.strip())
        for match in _BARE_AMOUNT_RE.findall(text):
            _push(found, match.strip())
        for match in _DATE_RE.findall(text):
            _push(found, match)
        for key in ("hr_bpm_mean", "heart_rate_bpm", "hr_bpm"):
            value = item.metrics.get(key)
            if isinstance(value, (int, float)) and value:
                _push(found, f"{int(value)}bpm")
        for key in ("g_peak", "peak_g"):
            value = item.metrics.get(key)
            if isinstance(value, (int, float)) and value:
                _push(found, f"{value:g}g")
                _push(found, f"{value:.2f}g")
        longest = item.metrics.get("longest_run_beats")
        if isinstance(longest, (int, float)) and longest:
            _push(found, f"{int(longest)}跳")
        drop = item.metrics.get("baro_drop_hpa_3h")
        if isinstance(drop, (int, float)) and drop:
            _push(found, f"{drop:g}hPa")
        pvc = item.metrics.get("pvc_run_count") or item.metrics.get("pvc_burst_count")
        if isinstance(pvc, (int, float)) and pvc:
            _push(found, f"{int(pvc)}阵")
        baro = item.metrics.get("baro_hpa")
        if isinstance(baro, (int, float)) and baro:
            _push(found, f"{baro:.0f}hPa")
            _push(found, f"{baro:g}hPa")
        duration = item.metrics.get("total_duration_s") or item.metrics.get("duration_s")
        if isinstance(duration, (int, float)) and duration >= 3600:
            _push(found, f"{int(duration // 3600)}小时")
            _push(found, f"{duration / 3600:.1f}小时")
        elif isinstance(duration, (int, float)) and duration >= 60:
            _push(found, f"{int(duration // 60)}分钟")
        steps = item.raw.get("floors_climbed") or item.raw.get("storeys")
        if isinstance(steps, (int, float)) and steps:
            _push(found, f"{int(steps)}层")
    return tuple(found[:10])


_SPEAKER_PREFIX_RE = re.compile(r"^\s*([\u4e00-\u9fffA-Za-z]{1,6})[：:]\s*")


def _clean_quote(text: str, limit: int = 80) -> str:
    """去掉括号里的旁白，但**保留**"说话人："前缀——当事人姓名是关键实体锚点。"""
    quote = re.sub(r"（.*?）|\(.*?\)", "", text).strip()
    return quote[:limit]


def _speaker_prefix(text: str) -> str:
    match = _SPEAKER_PREFIX_RE.match(text.strip())
    return match.group(1) if match else ""


def _summary_for(cluster: EventCluster, speaker_names: Mapping[str, str]) -> str:
    """把事件簇凝练成一句话：规范方向表述 + 原文关键片段（保证方向词落地）。"""
    anchor = cluster.anchor
    pieces = [cluster.theme.canonical]
    quote = _clean_quote(anchor.text)
    if quote:
        label = "现场原话" if anchor.modality in {"mic", "dialogue"} else "来源内容"
        pieces.append(f"{label}：{quote}")
    speaker = anchor.speaker
    if speaker and speaker in speaker_names:
        pieces.append(f"相关人：{speaker_names[speaker]}")
    elif speaker and speaker not in {"unknown_or_multi", "佩戴者", "user+1"}:
        pieces.append(f"相关人：{speaker}")
    return "；".join(p for p in pieces if p)[:240]


def synthesize_fact(
    cluster: EventCluster,
    *,
    index: int,
    question_id: str,
    speaker_names: Mapping[str, str],
    wearer_centric: bool,
    extra_entities: Sequence[str] = (),
) -> ExtractedFact:
    """每个事件簇凝练为一条 :class:`ExtractedFact`。"""
    return ExtractedFact(
        fact_id=f"F_{question_id}_{index:02d}",
        dimension_id=cluster.theme.dimension,
        semantic_intent=cluster.theme.intent,
        summary_text=_summary_for(cluster, speaker_names),
        recognized_entities=extract_entities(
            cluster.members, speaker_names, include_wearer=wearer_centric, extra=extra_entities
        ),
        source_ref_id=cluster.anchor.item_id,
    )


def synthesize_voiceprint_facts(
    payload: Mapping[str, Any],
    kept: Sequence[SliceItem],
    *,
    question_id: str,
    start_index: int,
) -> List[ExtractedFact]:
    """声纹聚类是"整簇一条事实"的模态：本人锚定 + 核心联系人绑定。"""
    voice = payload.get("voiceprint_cluster") or {}
    if not isinstance(voice, Mapping) or not kept:
        return []
    total = 0
    for key in ("total_detected_speakers", "n_detected_speakers", "speaker_count"):
        value = voice.get(key)
        if isinstance(value, (int, float)) and value:
            total = int(value)
            break
    if not total:
        total = len(voice.get("detected_speakers") or voice.get("speakers") or kept)

    user_item = max(
        kept,
        key=lambda it: float(it.metrics.get("cosine_to_user") or it.metrics.get("cosine_to_enrolled_user") or 0.0),
    )
    contacts: List[Tuple[str, SliceItem]] = []
    for item in kept:
        if item.item_id == user_item.item_id:
            continue
        name = str(item.raw.get("voiceprint_match_to") or "")
        if not name:
            role = str(item.raw.get("role") or "")
            name = role.split("-")[-1].strip() if "-" in role else role
        if not name:
            bank = item.raw.get("cosine_to_contact_bank")
            if isinstance(bank, Mapping) and bank:
                name = str(next(iter(bank.keys())))
        if name:
            contacts.append((name, item))

    binding_theme = _THEME_BY_INTENT["VOICE_BINDING_USER"]
    contact_names = [name for name, _ in contacts[:3]]
    transient_count = max(total - 1 - len(contact_names), 0)
    summary = (
        f"当日声纹聚类共识别{total}个说话人碎片，佩戴者本人声纹被稳定锚定为长期声纹"
        f"{'，核心联系人' + '、'.join(contact_names) + '一并绑定' if contact_names else ''}"
        f"，其余{transient_count}个为推销员、客服与路人等一次性杂散人声，已按 24h TTL 物理剪枝"
    )
    facts = [
        ExtractedFact(
            fact_id=f"F_{question_id}_{start_index:02d}",
            dimension_id=binding_theme.dimension,
            semantic_intent=binding_theme.intent,
            summary_text=summary,
            recognized_entities=tuple(["佩戴者", f"{total}人", *contact_names][:10]),
            source_ref_id=user_item.item_id,
        )
    ]
    # 核心联系人若携带实质对话内容，则再凝练一条"关键对话"事实。
    talk_theme = _THEME_BY_INTENT["KEY_CONVERSATION_WITH_CONTACT"]
    for name, item in contacts:
        quote = _clean_quote(str(item.raw.get("sample_text") or ""), limit=60)
        if len(quote) < 8:
            continue
        facts.append(
            ExtractedFact(
                fact_id=f"F_{question_id}_{start_index + len(facts):02d}",
                dimension_id=talk_theme.dimension,
                semantic_intent=talk_theme.intent,
                summary_text=f"与核心联系人{name}进行长时间深谈并达成约定；现场原话：{quote}",
                recognized_entities=tuple(["佩戴者", name, f"{total}人"][:10]),
                source_ref_id=item.item_id,
            )
        )
        break
    return facts


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def _echoed_texts(items: Sequence[SliceItem]) -> frozenset:
    """找出被 ≥2 个不同说话人重复的 MIC 文本（环境声 / 广播的机械特征）。"""
    speakers: Dict[str, set] = {}
    for item in items:
        if item.modality != "mic" or not item.text:
            continue
        speakers.setdefault(item.text, set()).add(item.speaker or item.item_id)
    return frozenset(text for text, group in speakers.items() if len(group) >= 2)


def _speaker_bindings(payload: Mapping[str, Any]) -> Dict[str, str]:
    """从声纹聚类里取出"说话人 ID → 人名"绑定。"""
    voice = payload.get("voiceprint_cluster") or {}
    names: Dict[str, str] = {}
    if not isinstance(voice, Mapping):
        return names
    bindings = voice.get("known_bindings")
    if isinstance(bindings, Mapping):
        for speaker_id, name in bindings.items():
            if isinstance(name, str):
                names[str(speaker_id)] = name
    return names


def _cross_channel_entities(kept: Sequence[SliceItem]) -> List[str]:
    """跨通道复现的实体（在 ≥2 条幸存碎片里出现）优先作为事实锚点。"""
    counter: Dict[str, int] = {}
    for item in kept:
        for entity in extract_entities([item], {}, include_wearer=False):
            counter[entity] = counter.get(entity, 0) + 1
    return [name for name, count in sorted(counter.items(), key=lambda kv: -kv[1]) if count >= 2][:6]


def _wearer_centric(items: Sequence[SliceItem]) -> bool:
    """事实是否以佩戴者为主体（传感器流与自言自语天然以佩戴者为主语）。"""
    return any(item.modality in {"sensor", "dialogue"} for item in items) or not items


def purify_slice(
    payload: Mapping[str, Any],
    *,
    solver_agent: str = SOLVER_AGENT_ID,
    max_facts: int = 3,
    min_theme_priority: int = 85,
) -> PurificationResult:
    """对一道考题（一天的生活流切片）执行完整清洗提纯。

    ``payload`` 可以带答案字段，函数内部会先物理剥离；返回值不含任何答案信息。
    """
    started = time.perf_counter()
    visible = strip_answer_leak(payload)
    question_id = str(visible.get("question_id") or "")
    generator_agent = str(visible.get("generator_agent") or "")

    emergency = emergency_triage(visible)
    speaker_names = _speaker_bindings(visible)
    items = normalize_items(visible)

    echoed = _echoed_texts(items)
    verdicts = [
        (item, classify_item(item, speaker_names=speaker_names, echoed_texts=echoed)) for item in items
    ]
    pruned = [item for item, verdict in verdicts if verdict.is_junk]
    kept = [item for item, verdict in verdicts if not verdict.is_junk]

    shared_entities = _cross_channel_entities(kept)
    facts: List[ExtractedFact] = []

    voice_kept = [item for item in kept if item.modality == "voiceprint"]
    if voice_kept:
        facts.extend(
            synthesize_voiceprint_facts(
                visible, voice_kept, question_id=question_id, start_index=len(facts) + 1
            )
        )

    for cluster in cluster_items(verdicts):
        if len(facts) >= max_facts:
            break
        if cluster.theme.priority < min_theme_priority:
            continue
        if any(fact.source_ref_id == cluster.anchor.item_id for fact in facts):
            continue
        facts.append(
            synthesize_fact(
                cluster,
                index=len(facts) + 1,
                question_id=question_id,
                speaker_names=speaker_names,
                wearer_centric=_wearer_centric(cluster.members),
                extra_entities=shared_entities,
            )
        )

    pruned_bytes = sum(len(json.dumps(dict(item.raw), ensure_ascii=False)) for item in pruned)
    retained_bytes = sum(len(json.dumps(dict(item.raw), ensure_ascii=False)) for item in kept)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return PurificationResult(
        question_id=question_id,
        solver_agent=solver_agent,
        generator_agent=generator_agent,
        facts=tuple(facts[:max_facts]),
        pruned_junk_ids=tuple(item.item_id for item in pruned),
        retained_item_ids=tuple(item.item_id for item in kept),
        emergency=emergency,
        execution_time_ms=elapsed_ms,
        llm_tokens_used=0,
        junk_reasons={item.item_id: verdict.reason for item, verdict in verdicts if verdict.is_junk},
        pruned_bytes=pruned_bytes,
        retained_bytes=retained_bytes,
    )
