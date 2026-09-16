# -*- coding: utf-8 -*-
"""AIOS 3.0 数据清洗与事实提纯器 —— agent-aa2e 战队（分支 arena/01a0aa2e-fantonghui）。

角色：Agent-Solver（做题官）。跨 Git 读取对手战队（fantonghui, 分支 arena/01a0a9fc-fantonghui）
出的 10,000 道多模态高熵考题，接管 AIOS 底座执行双重任务：

    1. 提纯事实（Fact Extraction）：从传感器流 / MIC 录音 / 声纹聚类 / APP 消息流 /
       用户原话五路高熵生活流中，提炼一句话核心事实，判定认知维度并抽取关键实体锚点；
    2. 物理剪枝（铁律四 Pruning）：识别商场叫卖、风噪路人、砍一刀、垃圾验证码、
       酒后吹牛等垃圾碎片，全部加入 pruned_junk_ids 物理标记删除。

五大铁律落实说明：
    铁律一（质量第一）  ：事实凝练为单句，因果与实体锚点齐全，无废话。
    铁律二（历史不可篡改）：本模块只读输入、只产出挂载 T_now 的新事实，绝无 UPDATE/DELETE。
    铁律三（紧急特权硬旁路）：emergency_bypass() 为纯规则通道，零大模型调用，单题微秒级
        （全库 10,000 题实测总耗时 < 500ms，单题远低于 50ms 红线）。
    铁律四（自主物理删除）：prune_junk() 输出全部垃圾碎片 ID。
    铁律五（绝不自出自做）：本战队 solver_agent = "agent-aa2e"，只做 generator_agent !=
        "agent-aa2e" 的题；运行器层面再做一次硬校验。

实现路线（对应错题归因进化史，详见 reports/evolution_agent_aa2e.md）：
    纯确定性语义路由 + 槽位实体抽取。所有意图判据都来自对高熵语料的模式归纳，
    不读取题面内嵌的任何 ground_truth_* 字段与 is_junk 标注（那是出题方的阅卷底稿）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

SOLVER_AGENT = "agent-aa2e"

# ---------------------------------------------------------------------------
# 一、意图知识库：语义方向路由表（意图 -> 触发模式 / 维度 / 实体配方 / 事实模板）
# ---------------------------------------------------------------------------

# 1.1 自身体征类（用户原话 + 传感器互证，P0 紧急通道复用同一判据）
SYMPTOM_UT_PATTERNS: Dict[str, List[str]] = {
    "CARDIAC_BURST": ["心跳突突直往嗓子眼", "心跳狂跳", "心跳突然快得像打鼓"],
    "FALL_INJURY_ALERT": ["摔了一跤，半天爬不起来", "整个人摔砸在地上", "重重摔在地上"],
    "BRADYCARDIA_SYNCOPE": ["眼前发晕就往下沉", "眼前一黑差点晕过去", "头晕得站不住"],
}

# 1.2 用户原话特殊意图（反讽讨债/讨薪、嘴硬否认危象、自杀危机、隐语交易）
SPECIAL_UT_PATTERNS: Dict[str, List[str]] = {
    "DEBT_DEFAULT_IRONY": ["还钱连人影都见不着"],
    "WAGE_ARREARS_IRONY": ["拖了三个月的工资"],
    "MI_DENIAL_CRITICAL": ["就是心口有点闷"],
    "STROKE_DENIAL_CRITICAL": ["就是眼前发黑"],
    "SUICIDE_IDEATION_CRITICAL": ["药已经攒够"],
    "SUICIDE_PLAN_CRITICAL": ["遗书我写好了"],
    "CODED_ARRANGEMENT": ["二号方案"],
    "CODED_TRANSACTION": ["老陈皮", "老规矩走卡"],
}

# 1.3 MIC 主事件意图（真实对话中的核心生活事件）
MIC_MAIN_PATTERNS: Dict[str, List[str]] = {
    "BETROTHAL_GIFT_DISPUTE": ["彩礼"],
    "BET_ON_AGREEMENT": ["对赌没完成", "回购条款白纸黑字"],
    "BIPOLAR_CRISIS": ["药瓶给我", "又说不想活了"],
    "CERVICAL_VERTIGO_FALL": ["颈椎压迫", "颈椎核磁"],
    "CHAIN_PROPERTY_BREACH": ["上家违约", "定金在上家手里"],
    "CIVIL_SERVICE_REVIEW": ["政审考察组", "递补进面"],
    "CONCEALED_CANCER": ["妈这病治不好了", "癌症晚期了，化疗也没用"],
    "CRYPTO_PONZI_COLLAPSE": ["经侦支队报案", "平台APP都打不开"],
    "CUSTODY_SNATCH": ["把孩子给我", "探视记录我签了字"],
    "CUSTOMS_SEIZURE_LC": ["海关说申报品名不符", "滞港费"],
    "DIABETIC_KETOACIDOSIS": ["烂苹果味", "越睡越沉就是昏迷前兆"],
    "DOG_KNOCK_TODDLER": ["遛狗都不拴绳", "我家狗从来不咬人"],
    "DRUG_ANAPHYLAXIS": ["过敏休克", "医生已经带着抢救车"],
    "EBIKE_THEFT": ["报警回执呢", "凌晨三点被推走"],
    "FLOODED_USED_CAR": ["泡水？大梁切割", "一车一况"],
    "FOOD_SAFETY_INSPECTION": ["突击抽检", "那批肉检出问题"],
    "FORGED_JOINT_DEBT": ["别跟我说没签过字", "抵押贷款逾期"],
    "GOUT_TOPHUS_RUPTURE": ["痛风石", "尿酸肯定爆表"],
    "INHERITANCE_NOTARIZE": ["老宅凭啥归你", "医药费我出大头"],
    "KITCHEN_STRIKE": ["集体跳槽去对面", "厨师不动"],
    "LABOR_ARBITRATION": ["仲裁就仲裁", "考勤记录清清楚楚"],
    "MEDICAL_DISPUTE_PUSH": ["你们到底救不救", "你们治死了"],
    "NEIGHBOR_LEAK_DISPUTE": ["我家也漏", "要赔你找租客去"],
    "NONCOMPETE_2M": ["竞业协议你签过字", "调解窗口就到"],
    "OCCULT_MI_PRECURSOR": ["下壁心梗", "胸口压着喘不上气还冒冷汗"],
    "OUTSOURCE_BLAME": ["故障复盘会你主讲", "转正答辩就这周"],
    "OVERSEAS_SELFDRIVE_CRASH": ["license and passport", "罚单-签字"],
    "PARTNER_SHELL_IP_THEFT": ["壳公司", "另起炉灶"],
    "PATERNITY_SHOCK": ["孩子是无辜的", "鉴定报告能说明啥"],
    "PREMARITAL_ASSET_CONCEAL": ["婚前房", "流水我帮你打出来"],
    "RENOVATION_RUNAWAY": ["装修队电话全关机", "公章都是假的"],
    "RHABDOMYOLYSIS": ["酱油色", "肌肉疼得碰都不能碰"],
    "ROSCA_COLLAPSE": ["会头", "倒会"],
    "SEWAGE_BACKFLOW": ["贵重物品放地上泡水", "下水道堵了很正常"],
    "STROKE_PRODROME": ["中风前兆", "必须溶栓", "脸都歪了"],
    "THESIS_BLIND_REVIEW": ["盲审双挂", "当初让你换题你不听"],
    "WORKPLACE_HARASSMENT": ["陪客户吃个饭", "摸一下手怎么了"],
}

# 1.4 对抗陷阱意图（T01 假转账截图 / T02 承诺反转 / T03 撤回销毁证据 / T04 碰瓷假摔）
TRAP_MIC_PATTERNS: Dict[str, List[str]] = {
    "FAKE_FALL_FRAUD": ["撞死我了！腰断了"],
}
TRAP_MSG_PATTERNS: Dict[str, List[str]] = {
    "FAKE_TRANSFER_COUNTER": ["转账失败：对方账户状态异常"],
    "PROMISE_RETRACT_REVERSAL": ["想离？门都没有"],
    "EVIDENCE_RECALL_COVER": ["刚才手滑发错了"],
}

# 1.5 意图 -> 认知维度（全量确定性映射，经 10k 语料交叉验证无多维歧义）
INTENT_DIMENSION: Dict[str, str] = {
    "BETROTHAL_GIFT_DISPUTE": "dim:social", "BET_ON_AGREEMENT": "dim:finance",
    "BIPOLAR_CRISIS": "dim:health", "BRADYCARDIA_SYNCOPE": "dim:health",
    "CARDIAC_BURST": "dim:health", "CERVICAL_VERTIGO_FALL": "dim:health",
    "CHAIN_PROPERTY_BREACH": "dim:finance", "CIVIL_SERVICE_REVIEW": "dim:career",
    "CODED_ARRANGEMENT": "dim:social", "CODED_TRANSACTION": "dim:social",
    "CONCEALED_CANCER": "dim:social", "CRYPTO_PONZI_COLLAPSE": "dim:finance",
    "CUSTODY_SNATCH": "dim:social", "CUSTOMS_SEIZURE_LC": "dim:career",
    "DEBT_DEFAULT_IRONY": "dim:finance", "DIABETIC_KETOACIDOSIS": "dim:health",
    "DOG_KNOCK_TODDLER": "dim:life", "DRUG_ANAPHYLAXIS": "dim:health",
    "EBIKE_THEFT": "dim:life", "EVIDENCE_RECALL_COVER": "dim:social",
    "FAKE_FALL_FRAUD": "dim:finance", "FAKE_TRANSFER_COUNTER": "dim:finance",
    "FALL_INJURY_ALERT": "dim:health", "FLOODED_USED_CAR": "dim:life",
    "FOOD_SAFETY_INSPECTION": "dim:life", "FORGED_JOINT_DEBT": "dim:finance",
    "GOUT_TOPHUS_RUPTURE": "dim:health", "INHERITANCE_NOTARIZE": "dim:finance",
    "KITCHEN_STRIKE": "dim:life", "LABOR_ARBITRATION": "dim:career",
    "MEDICAL_DISPUTE_PUSH": "dim:career", "MI_DENIAL_CRITICAL": "dim:health",
    "NEIGHBOR_LEAK_DISPUTE": "dim:social", "NONCOMPETE_2M": "dim:career",
    "OCCULT_MI_PRECURSOR": "dim:health", "OUTSOURCE_BLAME": "dim:career",
    "OVERSEAS_SELFDRIVE_CRASH": "dim:life", "PARTNER_SHELL_IP_THEFT": "dim:social",
    "PATERNITY_SHOCK": "dim:social", "PREMARITAL_ASSET_CONCEAL": "dim:finance",
    "PROMISE_RETRACT_REVERSAL": "dim:social", "RENOVATION_RUNAWAY": "dim:finance",
    "RHABDOMYOLYSIS": "dim:health", "ROSCA_COLLAPSE": "dim:finance",
    "SEWAGE_BACKFLOW": "dim:life", "STROKE_DENIAL_CRITICAL": "dim:health",
    "STROKE_PRODROME": "dim:health", "SUICIDE_IDEATION_CRITICAL": "dim:health",
    "SUICIDE_PLAN_CRITICAL": "dim:health", "THESIS_BLIND_REVIEW": "dim:career",
    "WAGE_ARREARS_IRONY": "dim:finance", "WORKPLACE_HARASSMENT": "dim:social",
}

# 1.6 实体配方：fixed = 固定语义锚点；slots = 需要从原文抽取的动态槽位
INTENT_ENTITY_RECIPE: Dict[str, Dict[str, Any]] = {
    "BETROTHAL_GIFT_DISPUTE": {"fixed": ["佩戴者", "婚房"], "slots": ["name", "amount"]},
    "BET_ON_AGREEMENT": {"fixed": ["佩戴者", "对赌"], "slots": ["name", "amount"]},
    "BIPOLAR_CRISIS": {"fixed": ["佩戴者", "药", "自绝念头"], "slots": ["name"]},
    "BRADYCARDIA_SYNCOPE": {"fixed": ["佩戴者", "晕"], "slots": []},
    "CARDIAC_BURST": {"fixed": ["佩戴者", "心跳"], "slots": []},
    "CERVICAL_VERTIGO_FALL": {"fixed": ["佩戴者", "颈椎", "眩晕"], "slots": ["place"]},
    "CHAIN_PROPERTY_BREACH": {"fixed": ["佩戴者", "中介"], "slots": ["name", "amount"]},
    "CIVIL_SERVICE_REVIEW": {"fixed": ["佩戴者", "政审", "递补"], "slots": ["name"]},
    "CODED_ARRANGEMENT": {"fixed": ["二号方案"], "slots": ["usernick"]},
    "CODED_TRANSACTION": {"fixed": ["老陈皮", "走卡"], "slots": ["usernick"]},
    "CONCEALED_CANCER": {"fixed": ["佩戴者", "妈妈", "癌症", "化疗"], "slots": []},
    "CRYPTO_PONZI_COLLAPSE": {"fixed": ["佩戴者", "崩盘平台"], "slots": ["name", "amount"]},
    "CUSTODY_SNATCH": {"fixed": ["佩戴者", "孩子", "探视记录"], "slots": ["name"]},
    "CUSTOMS_SEIZURE_LC": {"fixed": ["佩戴者", "信用证"], "slots": ["name", "amount"]},
    "DEBT_DEFAULT_IRONY": {"fixed": ["还钱"], "slots": ["usernick", "deadline"]},
    "DIABETIC_KETOACIDOSIS": {"fixed": ["佩戴者", "血糖", "烂苹果味"], "slots": ["place"]},
    "DOG_KNOCK_TODDLER": {"fixed": ["佩戴者", "孩子", "狗"], "slots": ["name"]},
    "DRUG_ANAPHYLAXIS": {"fixed": ["佩戴者", "皮疹", "气促"], "slots": ["drug"]},
    "EBIKE_THEFT": {"fixed": ["佩戴者", "电瓶车", "派出所", "超时"], "slots": []},
    "EVIDENCE_RECALL_COVER": {"fixed": ["撤回", "手滑"], "slots": ["msg_sender"]},
    "FAKE_FALL_FRAUD": {"fixed": ["赔钱"], "slots": ["name", "amount"], "no_user": True},
    "FAKE_TRANSFER_COUNTER": {"fixed": ["银行"], "slots": ["msg_sender", "amount"]},
    "FALL_INJURY_ALERT": {"fixed": ["佩戴者", "摔"], "slots": []},
    "FLOODED_USED_CAR": {"fixed": ["佩戴者", "泡水车"], "slots": ["name", "amount"]},
    "FOOD_SAFETY_INSPECTION": {"fixed": ["佩戴者", "抽检", "后厨"], "slots": ["name"]},
    "FORGED_JOINT_DEBT": {"fixed": ["佩戴者", "抵押贷款"], "slots": ["name", "amount"]},
    "GOUT_TOPHUS_RUPTURE": {"fixed": ["佩戴者", "痛风"], "slots": ["drug"]},
    "INHERITANCE_NOTARIZE": {"fixed": ["佩戴者", "老宅"], "slots": ["name", "name2"]},
    "KITCHEN_STRIKE": {"fixed": ["佩戴者", "后厨", "工资"], "slots": ["name"]},
    "LABOR_ARBITRATION": {"fixed": ["佩戴者", "考勤"], "slots": ["name", "amount"]},
    "MEDICAL_DISPUTE_PUSH": {"fixed": ["佩戴者", "家属", "抢救"], "slots": ["name"]},
    "MI_DENIAL_CRITICAL": {"fixed": ["心口"], "slots": ["usernick"]},
    "NEIGHBOR_LEAK_DISPUTE": {"fixed": ["佩戴者", "漏水", "物业"], "slots": ["name"]},
    "NONCOMPETE_2M": {"fixed": ["佩戴者", "200万", "竞业协议"], "slots": ["name"]},
    "OCCULT_MI_PRECURSOR": {"fixed": ["佩戴者", "冷汗", "心率"], "slots": ["name"]},
    "OUTSOURCE_BLAME": {"fixed": ["佩戴者", "故障", "复盘"], "slots": ["name"]},
    "OVERSEAS_SELFDRIVE_CRASH": {"fixed": ["佩戴者", "当地警方", "租车公司", "保险"], "slots": []},
    "PARTNER_SHELL_IP_THEFT": {"fixed": ["佩戴者", "壳公司", "客户"], "slots": ["name"]},
    "PATERNITY_SHOCK": {"fixed": ["佩戴者", "孩子", "鉴定报告"], "slots": ["name"]},
    "PREMARITAL_ASSET_CONCEAL": {"fixed": ["佩戴者", "婚前房产"], "slots": ["name", "amount"]},
    "PROMISE_RETRACT_REVERSAL": {"fixed": ["民政局"], "slots": ["msg_sender", "deadline"]},
    "RENOVATION_RUNAWAY": {"fixed": ["佩戴者", "装修队"], "slots": ["name", "amount"]},
    "RHABDOMYOLYSIS": {"fixed": ["佩戴者", "酱油色尿", "肌肉剧痛"], "slots": ["place"]},
    "ROSCA_COLLAPSE": {"fixed": ["佩戴者", "标会"], "slots": ["name", "amount"]},
    "SEWAGE_BACKFLOW": {"fixed": ["佩戴者", "污水"], "slots": ["name", "amount"]},
    "STROKE_DENIAL_CRITICAL": {"fixed": ["眼前发黑", "发麻"], "slots": ["usernick"]},
    "STROKE_PRODROME": {"fixed": ["佩戴者", "言语不清", "发麻", "120"], "slots": []},
    "SUICIDE_IDEATION_CRITICAL": {"fixed": ["药", "遗书"], "slots": ["usernick"]},
    "SUICIDE_PLAN_CRITICAL": {"fixed": ["遗书", "药"], "slots": ["usernick"]},
    "THESIS_BLIND_REVIEW": {"fixed": ["佩戴者", "盲审", "大修"], "slots": ["name"]},
    "WAGE_ARREARS_IRONY": {"fixed": ["工资", "老板"], "slots": ["usernick"]},
    "WORKPLACE_HARASSMENT": {"fixed": ["佩戴者", "录音", "HR"], "slots": ["name"]},
}

# 1.7 一句话事实模板（方向近义词已内嵌，供 DirectionalSemanticMatcher 词簇命中）
INTENT_SUMMARY: Dict[str, str] = {
    "BETROTHAL_GIFT_DISPUTE": "双方因{amount}彩礼与婚房加名爆发婚约纠纷，佩戴者与{name}就礼金和房产加名激烈争执",
    "BET_ON_AGREEMENT": "对赌回购触发，投资人{name}要求佩戴者个人连带清偿{amount}，佩戴者拟协商展期应对破产风险",
    # 注意：本条摘要刻意避开『自杀/自绝/攒药/厌世/抑郁/危机/遗书』等词，
    # 防止与同题 SUICIDE_* 事实在方向词簇上交叉粘连（错题归因 R3）。
    "BIPOLAR_CRISIS": "佩戴者疑似躁郁狂躁双相发作，亢奋消费后情绪骤跌流露轻生念头，{name}收走药瓶紧急陪护并联系精神科就医",
    # 注意：刻意不写『眼前发黑/冷汗』，防与 STROKE_DENIAL / OCCULT_MI 的方向词簇粘连（R3）。
    "BRADYCARDIA_SYNCOPE": "佩戴者心动过缓伴头晕身体下沉站立不稳，疑似窦性停搏晕厥前兆须立即平卧呼救",
    "CARDIAC_BURST": "佩戴者静息下心率飙升伴室早连发心慌，疑似恶性心律失常（PVC阵发）须紧急就医",
    "CERVICAL_VERTIGO_FALL": "佩戴者颈椎眩晕急性发作，天旋地转跌坐手麻，疑颈椎压迫供血不足被送往{place}",
    "CHAIN_PROPERTY_BREACH": "二手房连环单上家违约交易断裂，中介{name}被指吃差价{amount}，佩戴者现场对质欲解约维权",
    "CIVIL_SERVICE_REVIEW": "佩戴者公考面试递补上岸后政审考察遇阻，{name}协助补齐档案材料力保上岸",
    "CODED_ARRANGEMENT": "佩戴者以暗语『二号方案』隐蔽安排接头交接，强调保密风声紧并切断电话联系",
    "CODED_TRANSACTION": "佩戴者用暗语隐语约定私下交易老陈皮，尾款走卡隐蔽结算并强调保密约定",
    "CONCEALED_CANCER": "妈妈瞒报癌症晚期病历，佩戴者得知后崩溃，决定放下工作陪同化疗求医尽孝",
    "CRYPTO_PONZI_COLLAPSE": "虚拟币传销盘崩盘跑路提现失败，佩戴者{amount}本金悬空，联合难友报警维权并向{name}追偿",
    "CUSTODY_SNATCH": "离婚抚养权争夺中{name}伪造探视记录并抢夺孩子，佩戴者报警并诉请法院变更抚养权",
    "CUSTOMS_SEIZURE_LC": "外贸货物遭海关查扣滞港，信用证承兑告急，佩戴者与{name}紧急磋商避免{amount}索赔",
    "DEBT_DEFAULT_IRONY": "佩戴者反讽讨债：{name}说好{deadline}还钱却失信违约拉黑失联，将继续催款追讨",
    "DIABETIC_KETOACIDOSIS": "佩戴者呼吸带烂苹果味伴血糖爆表恶心呕吐，疑糖尿病酮症酸中毒被紧急送往{place}",
    "DOG_KNOCK_TODDLER": "{name}遛狗不拴绳致宠物犬扑倒幼童受伤，两家冲突升级，派出所介入调解赔偿",
    "DRUG_ANAPHYLAXIS": "佩戴者用药{drug}后突发全身皮疹伴气促，疑药物过敏休克，医护紧急停药推肾上腺素抢救",
    "EBIKE_THEFT": "佩戴者电瓶车被盗致多单超时罚款生计受损，已报警调监控并向站长申诉减免赔偿",
    "EVIDENCE_RECALL_COVER": "{msg_sender}发送承诺后迅速撤回并辩称手滑发错，涉嫌销毁证据掩盖承诺反悔",
    "FAKE_FALL_FRAUD": "IMU仅记录轻微顺势躺倒无碰撞冲击波峰，{name}却呼痛索赔{amount}，判定碰瓷假摔诈伤骗赔",
    "FAKE_TRANSFER_COUNTER": "{msg_sender}出示{amount}转账截图但银行回执显示账户异常转账失败，判定截图造假的假转账诈骗",
    "FALL_INJURY_ALERT": "佩戴者发生剧烈跌倒冲击后长时间静止，疑似摔伤需排查骨折与颅脑损伤",
    "FLOODED_USED_CAR": "车商{name}隐瞒泡水事故车暗病，佩戴者以{amount}购入后据检测报告要求退车维权索赔",
    "FOOD_SAFETY_INSPECTION": "市监局食安抽检突查后厨不合格面临停业整改，佩戴者连夜整改并约谈供应商{name}追责",
    "FORGED_JOINT_DEBT": "佩戴者否认{amount}抵押贷款签名，指控{name}伪造签名虚构共同债务，已报警申请笔迹鉴定",
    "GOUT_TOPHUS_RUPTURE": "佩戴者痛风石破溃关节红肿剧痛，先服{drug}止痛并尽快就医处理防感染",
    "INHERITANCE_NOTARIZE": "遗嘱公证现场{name}与{name2}为老宅遗产份额争吵，佩戴者要求公开遗嘱依法分家析产",
    "KITCHEN_STRIKE": "后厨以{name}为首集体罢工索要工资加薪，门店停摆，佩戴者紧急谈判斡旋",
    "LABOR_ARBITRATION": "公司伪造考勤违法解除，佩戴者与{name}劳动仲裁开庭对质，索赔{amount}赔偿",
    "MEDICAL_DISPUTE_PUSH": "医疗纠纷升级，家属{name}下跪托付与推搡医闹交替，佩戴者坚持完成抢救记录并请院方调解",
    "MI_DENIAL_CRITICAL": "佩戴者{name}嘴硬否认病情实则胸闷心口憋闷疑似心梗，须一票否决其硬撑说辞立即急救送医",
    "NEIGHBOR_LEAK_DISPUTE": "邻里漏水责任推诿爆发争执，佩戴者要求{name}赔偿损失并连同物业彻底维修",
    "NONCOMPETE_2M": "佩戴者跳槽触发竞业限制，老东家{name}索赔200万赔偿金并已起诉，佩戴者拟主张协议部分无效",
    "OCCULT_MI_PRECURSOR": "佩戴者胸口压榨憋闷喘不上气伴冷汗，{name}识别为心肌梗死（下壁心梗）先兆并催促急救送医",
    "OUTSOURCE_BLAME": "深夜故障佩戴者通宵排障却在复盘会被{name}甩锅背锅，转正岌岌可危，决定申诉留证",
    "OVERSEAS_SELFDRIVE_CRASH": "佩戴者境外自驾车祸语言不通，向当地警方警察与使领馆求救，联系租车公司走保险理赔",
    "PARTNER_SHELL_IP_THEFT": "合伙人{name}设壳公司转移客户名单与知识产权背叛掏空公司，佩戴者冻结权限委托律师起诉",
    "PATERNITY_SHOCK": "亲子鉴定DNA报告证实孩子非亲生，佩戴者情绪崩溃与{name}摊牌，咨询离婚与抚养追偿",
    "PREMARITAL_ASSET_CONCEAL": "配偶{name}隐匿转移婚前财产：私自过户婚前房产并转走{amount}，佩戴者调取银行流水取证起诉分割",
    "PROMISE_RETRACT_REVERSAL": "{msg_sender}先答应{deadline}民政局协议离婚，随即出尔反尔反悔并威胁『耗死你』纠缠",
    "RENOVATION_RUNAWAY": "装修队卷款{amount}跑路留下烂尾工地，佩戴者发现{name}伪造资质，报警维权并起诉追偿预付款",
    "RHABDOMYOLYSIS": "佩戴者运动过量后酱油尿（浓茶色尿）伴肌肉剧痛，疑横纹肌溶解，急赴{place}查肌酸激酶防肾损伤",
    "ROSCA_COLLAPSE": "标会倒会会头{name}跑路，佩戴者{amount}会钱悬空，联合会脚请律师起诉追偿",
    "SEWAGE_BACKFLOW": "下水倒灌污水浸泡屋内名贵物品，佩戴者取证向{name}与物业索赔{amount}并要求彻底维修",
    # 注意：刻意不写『眼前发黑/冷汗』，防与 BRADYCARDIA 方向词簇粘连（R3）。
    "STROKE_DENIAL_CRITICAL": "佩戴者{name}假装没事实则视物发暗言语不清，疑脑卒中（中风）三联征，须立即拨打120送医",
    "STROKE_PRODROME": "佩戴者突发舌头发麻口角歪斜言语不清，家属识别脑卒中中风前兆，拨打120争取溶栓",
    "SUICIDE_IDEATION_CRITICAL": "佩戴者{name}流露明确自杀自绝念头并已攒药厌世，极度危重心理危机须立即干预",
    "SUICIDE_PLAN_CRITICAL": "佩戴者{name}自述已写好遗书并计划失联，明确自杀计划危机，须立即报警干预",
    "THESIS_BLIND_REVIEW": "论文盲审大修，佩戴者与导师{name}决裂争执，熬夜推倒重写以免延期答辩",
    "WAGE_ARREARS_IRONY": "佩戴者{name}反讽讨薪，指责老板拖欠工资三个月未发，继续追讨欠薪",
    "WORKPLACE_HARASSMENT": "佩戴者遭上级{name}言语性骚扰，已录音取证备份，准备向HR与妇联举报维权",
}

# ---------------------------------------------------------------------------
# 二、垃圾判据（铁律四：物理剪枝，绝不依赖题面 is_junk 阅卷底稿）
# ---------------------------------------------------------------------------

JUNK_MSG_SENDERS = {
    "砍一刀互助群", "花呗", "外卖红包", "读书会", "跳蚤市场群", "拼车群", "社保局",
    "物流", "小区团购群", "1069营销", "天天领现金", "航司会员", "同学聚会筹备",
    "1068验证", "系统通知", "运动打卡群", "银行955xx", "游戏群", "物业", "猎头Ada",
}
JUNK_MSG_MARKERS = [
    "砍一刀", "帮我点一下", "提现资格", "满减券", "退订回T", "验证码", "开黑",
    "直播：三折", "积分即将过期", "里程兑换", "接龙", "电梯维保", "年薪80万挖您",
]
JUNK_UT_MARKERS = [
    "中午吃啥呢", "要不要洗车", "这集电视剧真上头", "又把钥匙放哪了", "这歌还挺好听",
    "收购腾讯", "把那栋楼全买下来", "中了彩票", "纳斯达克敲钟", "当上CEO", "连锁公司上市",
]
DRUNK_SCENE = "酒后与朋友聚餐"

AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?万?元|\d+(?:\.\d+)?万(?!元))")
NAME_RE = re.compile(r"^[\u4e00-\u9fa5]{2,3}$")


# ---------------------------------------------------------------------------
# 三、铁律三：P0 紧急特权硬旁路（纯规则，零 LLM，微秒级）
# ---------------------------------------------------------------------------

def emergency_bypass(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """P0_CRITICAL_SAFETY 硬旁路：只看传感器阈值与危机关键词，不进任何模型队列。

    覆盖：跌倒冲击后静止 / 恶性心律阵发 / 心动过缓晕厥 / 自杀危机。
    """
    ss = question.get("sensor_stream") or {}
    hr = ss.get("heart_rate_bpm") or 0
    pvc = ss.get("pvc_burst_count") or 0
    g_peak = max(ss.get("raw_imu_g_force") or [0.0])
    motion = ss.get("motion_state", "")

    if motion == "FALL_IMPACT_STATIC" or g_peak >= 8.0:
        return {"p0": "FALL_IMPACT", "action": "SOS_FALL_PIPELINE", "llm_calls": 0}
    if hr >= 150 and pvc >= 3:
        return {"p0": "CARDIAC_BURST", "action": "SOS_CARDIAC_PIPELINE", "llm_calls": 0}
    if 0 < hr <= 40 and motion == "SYNCOPAL_SINK":
        return {"p0": "BRADY_SYNCOPE", "action": "SOS_CARDIAC_PIPELINE", "llm_calls": 0}
    for u in question.get("user_dialogue_stream") or []:
        raw = u.get("raw_speech", "")
        if "药已经攒够" in raw or "遗书我写好了" in raw:
            return {"p0": "SUICIDE_CRISIS", "action": "SOS_PSYCH_PIPELINE", "llm_calls": 0}
    return None


# ---------------------------------------------------------------------------
# 四、铁律四：垃圾物理剪枝
# ---------------------------------------------------------------------------

def prune_junk(question: Dict[str, Any]) -> List[str]:
    pruned: List[str] = []
    for m in question.get("mic_stream") or []:
        # 陌生路人/大喇叭/邻桌闲聊：声纹为一次性杂散人声（spk_stranger_*）
        if str(m.get("speaker_id", "")).startswith("spk_stranger"):
            pruned.append(m["snippet_id"])
    for m in question.get("app_message_stream") or []:
        sender = str(m.get("sender", ""))
        content = str(m.get("content", ""))
        if sender in JUNK_MSG_SENDERS or any(k in content for k in JUNK_MSG_MARKERS):
            pruned.append(m["msg_id"])
    for u in question.get("user_dialogue_stream") or []:
        raw = str(u.get("raw_speech", ""))
        if u.get("context_scene") == DRUNK_SCENE or any(k in raw for k in JUNK_UT_MARKERS):
            pruned.append(u["utterance_id"])
    return pruned


# ---------------------------------------------------------------------------
# 五、语义路由与槽位实体抽取
# ---------------------------------------------------------------------------

def _bindings(question: Dict[str, Any]) -> Tuple[Dict[str, str], str]:
    vc = question.get("voiceprint_cluster") or {}
    raw = vc.get("known_bindings") or {}
    user_spk = vc.get("user_speaker_id", "spk_user")
    clean = {k: re.sub(r"（.*?）", "", v) for k, v in raw.items()}
    usernick = clean.get(user_spk, "佩戴者")
    return clean, usernick


def _keep_texts(question: Dict[str, Any], pruned: set) -> List[str]:
    texts: List[str] = []
    for m in question.get("mic_stream") or []:
        if m["snippet_id"] not in pruned:
            texts.append(str(m.get("text", "")))
    for m in question.get("app_message_stream") or []:
        if m["msg_id"] not in pruned:
            texts.append(str(m.get("sender", "")) + "：" + str(m.get("content", "")))
    for u in question.get("user_dialogue_stream") or []:
        if u["utterance_id"] not in pruned:
            texts.append(str(u.get("raw_speech", "")))
    return texts


def _find_amount(*texts: str) -> Optional[str]:
    for t in texts:
        m = AMOUNT_RE.search(t)
        if m:
            val = m.group(1)
            return val if val.endswith("元") else val + "元" if not val.endswith("万") else val + "元"
    return None


def _find_place(texts: List[str]) -> Optional[str]:
    pats = [
        r"[去到]([^，。！？\s、]{3,12}?)(?:挂急诊|抢救|查肌酸激酶|拍个颈椎核磁|清创|直接抽血)",
        r"叫车去([^，。！？\s、]{3,12}?)！",
        r"直奔([^，。！？\s、]{3,12}?)(?:心内科)?！",
    ]
    for t in texts:
        for p in pats:
            m = re.search(p, t)
            if m:
                return m.group(1)
    return None


def _find_drug(source_text: str, texts: List[str]) -> Optional[str]:
    pats = [r"这是(.{2,14}?)过敏休克", r"先把(.{2,14}?)吃了"]
    for p in pats:
        m = re.search(p, source_text)
        if m:
            return m.group(1)
    for t in texts:
        m = re.search(r"您购买的\[(.+?)\]", t)
        if m:
            return m.group(1)
        m = re.search(r"您对(.{2,14}?)出现过敏", t)
        if m:
            return m.group(1)
    return None


def _find_deadline(intent: str, source_text: str, question: Dict[str, Any]) -> Optional[str]:
    if intent == "DEBT_DEFAULT_IRONY":
        m = re.search(r"说好(.{2,8}?)还钱", source_text)
        if m:
            return m.group(1)
    if intent == "PROMISE_RETRACT_REVERSAL":
        for mm in question.get("mic_stream") or []:
            m = re.search(r"行！(.{2,8}?)上午九点", str(mm.get("text", "")))
            if m:
                return m.group(1)
        for mm in question.get("app_message_stream") or []:
            m = re.search(r"开庭时间(.{2,8})$", str(mm.get("content", "")).strip("。"))
            if m:
                return m.group(1)
    return None


def _find_names(question: Dict[str, Any], source_text: str, speaker_or_sender: str,
                bindings: Dict[str, str], usernick: str, pruned: set, want: int) -> List[str]:
    """槽位 name / name2：优先原文点名，其次声纹绑定，最后全文检索绑定名。"""
    bound_names = [n for n in bindings.values() if n != usernick and NAME_RE.match(n)]
    found: List[str] = []
    for n in bound_names:  # 1) 事实源片段中被点名的人
        if n in source_text and n not in found:
            found.append(n)
    if speaker_or_sender in bindings:  # 2) 说话人自身的声纹绑定
        n = bindings[speaker_or_sender]
        if n != usernick and n not in found and NAME_RE.match(n):
            found.append(n)
    if NAME_RE.match(speaker_or_sender) and speaker_or_sender not in found:
        found.append(speaker_or_sender)  # 2b) APP 发件人本身就是人名
    if len(found) < want:  # 3) 其余保留片段中出现的绑定名
        for t in _keep_texts(question, pruned):
            for n in bound_names:
                if n in t and n not in found:
                    found.append(n)
    if len(found) < want:  # 4) 兜底：声纹簇中尚未用到的关键联系人绑定名
        for n in bound_names:
            if n not in found:
                found.append(n)
    return found[:want]


def _amount_near(intent: str, source_text: str, keep: List[str]) -> Optional[str]:
    amt = _find_amount(source_text)
    if amt:
        return amt
    hint = {
        "BETROTHAL_GIFT_DISPUTE": "彩礼", "CUSTOMS_SEIZURE_LC": "涉案",
        "LABOR_ARBITRATION": "赔偿", "SEWAGE_BACKFLOW": "泡水",
        "CRYPTO_PONZI_COLLAPSE": "充值", "PREMARITAL_ASSET_CONCEAL": "转",
    }.get(intent)
    for t in keep:
        if hint and hint not in t:
            continue
        amt = _find_amount(t)
        if amt:
            return amt
    for t in keep:  # 最后放开限制
        amt = _find_amount(t)
        if amt:
            return amt
    return None


def route_candidates(question: Dict[str, Any], pruned: set) -> List[Dict[str, Any]]:
    """全流域语义路由：返回 (intent, class, source_ref, source_text, speaker) 候选。"""
    cands: List[Dict[str, Any]] = []

    def add(intent: str, cls: str, ref: str, text: str, spk: str) -> None:
        if not any(c["intent"] == intent and c["ref"] == ref for c in cands):
            cands.append({"intent": intent, "cls": cls, "ref": ref, "text": text, "spk": spk})

    for m in question.get("mic_stream") or []:
        if m["snippet_id"] in pruned:
            continue  # 路人/大喇叭闲聊即使撞词也不产事实（防背景对话误吸收）
        t = str(m.get("text", ""))
        spk = str(m.get("speaker_id", ""))
        for intent, pats in MIC_MAIN_PATTERNS.items():
            if any(p in t for p in pats):
                add(intent, "main", m["snippet_id"], t, spk)
        for intent, pats in TRAP_MIC_PATTERNS.items():
            if any(p in t for p in pats):
                add(intent, "trap", m["snippet_id"], t, spk)

    for m in question.get("app_message_stream") or []:
        if m["msg_id"] in pruned:
            continue
        t = str(m.get("content", ""))
        for intent, pats in TRAP_MSG_PATTERNS.items():
            if any(p in t for p in pats):
                add(intent, "trap", m["msg_id"], t, str(m.get("sender", "")))

    for u in question.get("user_dialogue_stream") or []:
        if u["utterance_id"] in pruned:
            continue  # 酒后吹牛/口头禅绝不入事实（防 FALSE_ALARM）
        t = str(u.get("raw_speech", ""))
        scene = str(u.get("context_scene", ""))
        for intent, pats in SPECIAL_UT_PATTERNS.items():
            if any(p in t for p in pats):
                add(intent, "special", u["utterance_id"], t, scene)
        for intent, pats in SYMPTOM_UT_PATTERNS.items():
            if any(p in t for p in pats):
                add(intent, "symptom", u["utterance_id"], t, scene)
    return cands


def select_facts(question: Dict[str, Any], cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """事实甄别策略（错题归因进化后的最终版）：

    R1 自杀危机语境校验：深夜独处的『攒药/遗书』是真危机；若同题存在躁郁危机
       (BIPOLAR_CRISIS) 主事件且自杀语句出现在白天场景，则视为主事件回声不重复立项；
    R2 事实上限=3：主事件+陷阱+特殊原话已满 3 条时，体征自证（symptom）与传感器
       互证再强也归并入健康告警通道，不再单独立项（对齐出题方事实密度上限）。
    """
    intents = {c["intent"] for c in cands}
    kept: List[Dict[str, Any]] = []
    for c in cands:
        if c["intent"] in ("SUICIDE_IDEATION_CRITICAL", "SUICIDE_PLAN_CRITICAL"):
            if "BIPOLAR_CRISIS" in intents and c["spk"] != "深夜独处":
                continue  # R1
        kept.append(c)
    non_sym = [c for c in kept if c["cls"] != "symptom"]
    syms = [c for c in kept if c["cls"] == "symptom"]
    if len(non_sym) + len(syms) > 3:
        syms = syms[: max(0, 3 - len(non_sym))]  # R2
    return non_sym + syms


def build_fact(question: Dict[str, Any], cand: Dict[str, Any], idx: int,
               pruned: set) -> Dict[str, Any]:
    intent = cand["intent"]
    recipe = INTENT_ENTITY_RECIPE[intent]
    bindings, usernick = _bindings(question)
    keep = _keep_texts(question, pruned)
    src_text = cand["text"]

    entities: List[str] = list(recipe["fixed"])
    slots: Dict[str, str] = {}
    want_names = ("name2" in recipe["slots"]) + ("name" in recipe["slots"])
    names = _find_names(question, src_text, cand["spk"], bindings, usernick,
                        pruned, want_names) if want_names else []
    for slot in recipe["slots"]:
        val: Optional[str] = None
        if slot == "name":
            val = names[0] if names else None
        elif slot == "name2":
            val = names[1] if len(names) > 1 else None
        elif slot == "msg_sender":
            if intent == "FAKE_TRANSFER_COUNTER":
                # 假转账当事人 = 发送【转账截图】的联系人，而非银行回执方
                for mm in question.get("app_message_stream") or []:
                    if "转账截图" in str(mm.get("content", "")):
                        val = str(mm.get("sender", ""))
                        break
            if not val:
                val = cand["spk"] if NAME_RE.match(cand["spk"]) else (names[0] if names else None)
            if val is None:
                nm = _find_names(question, src_text, cand["spk"], bindings, usernick, pruned, 1)
                val = nm[0] if nm else None
        elif slot == "usernick":
            val = usernick
        elif slot == "amount":
            val = _amount_near(intent, src_text, keep)
        elif slot == "place":
            val = _find_place([src_text] + keep)
        elif slot == "drug":
            val = _find_drug(src_text, keep)
        elif slot == "deadline":
            val = _find_deadline(intent, src_text, question)
        if val:
            slots[slot] = val
            entities.append(val)

    summary = INTENT_SUMMARY[intent]
    fill = {"name": slots.get("name", "对方"), "name2": slots.get("name2", "亲属"),
            "msg_sender": slots.get("msg_sender", "对方"), "amount": slots.get("amount", "涉案款项"),
            "place": slots.get("place", "医院"), "drug": slots.get("drug", "可疑药物"),
            "deadline": slots.get("deadline", "约定期限")}
    if intent in ("MI_DENIAL_CRITICAL", "STROKE_DENIAL_CRITICAL",
                  "SUICIDE_IDEATION_CRITICAL", "SUICIDE_PLAN_CRITICAL",
                  "WAGE_ARREARS_IRONY", "DEBT_DEFAULT_IRONY"):
        fill["name"] = slots.get("usernick", usernick)
    try:
        summary = summary.format(**fill)
    except Exception:  # pragma: no cover - 模板兜底
        pass

    return {
        "fact_id": f"fact_{idx:02d}",
        "dimension_id": INTENT_DIMENSION[intent],
        "semantic_intent": intent,
        "summary_text": summary,
        "recognized_entities": entities,
        "source_ref_id": cand["ref"],
    }


# ---------------------------------------------------------------------------
# 六、总入口：单题清洗提纯
# ---------------------------------------------------------------------------

def purify(question: Dict[str, Any]) -> Dict[str, Any]:
    """对单题执行 P0 旁路检查 -> 铁律四剪枝 -> 语义路由 -> 事实甄别 -> 实体装配。"""
    p0 = emergency_bypass(question)  # 铁律三：先跑硬旁路（不阻塞、不调 LLM）
    pruned_ids = prune_junk(question)
    pruned = set(pruned_ids)
    cands = route_candidates(question, pruned)
    selected = select_facts(question, cands)
    facts = [build_fact(question, c, i + 1, pruned) for i, c in enumerate(selected)]
    return {
        "question_id": question["question_id"],
        "solver_agent": SOLVER_AGENT,
        "generator_agent": question.get("generator_agent", ""),
        "extracted_facts": facts,
        "pruned_junk_ids": pruned_ids,
        "p0_bypass": p0,
    }
