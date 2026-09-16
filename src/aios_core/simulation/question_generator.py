"""Seven-dimensional high-entropy cleaning-question generator.

The cleaning arena deliberately keeps question generation local and deterministic.  A
question is made from one factor in each of the seven dimensions described by the
arena brief: a persona, an event, a sensor waveform, an acoustic environment, a
linguistic style, a speaker topology, and an adversarial counter-factual.

This module is an *examiner* and does not call an LLM or an external service.  The
same ``generator_agent`` and seed produce byte-for-byte equivalent JSON records,
which makes it useful both for the distributed arena and for local regression
tests.  Generation is streaming; creating a 10,000-question set does not require
keeping the whole set in memory.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .cleaning_arena_protocol import (
    CleaningQuestion,
    DifficultyLevel,
    DirectionalSemanticFact,
)

UTC = timezone.utc
DEFAULT_SEED = 20260916
DEFAULT_QUESTION_COUNT = 10_000
DEFAULT_START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)

__all__ = [
    "ADVERSARIAL_TRAPS",
    "AMBIENT_ACOUSTIC_TOPOLOGIES",
    "CORE_EVENT_SPECTRUM",
    "CleaningQuestionGenerator",
    "ACOUSTIC_ENVIRONMENTS",
    "DEMOGRAPHIC_FACTORS",
    "EVENT_FACTORS",
    "LANGUAGE_PROFILES",
    "SENSOR_FACTORS",
    "SPEAKER_VOICEPRINT_TOPOLOGIES",
    "TRAP_FACTORS",
    "DEFAULT_QUESTION_COUNT",
    "DEFAULT_SEED",
    "DEMOGRAPHIC_PERSONAS",
    "DatasetPaths",
    "EventFactor",
    "PersonaFactor",
    "SensorFactor",
    "AcousticFactor",
    "LinguisticFactor",
    "SpeakerTopology",
    "TrapFactor",
    "EVENT_DOMAINS",
    "HighEntropyQuestionGenerator",
    "LifeSpectrumQuestionGenerator",
    "LINGUISTIC_PROFILES",
    "QuestionGenerator",
    "QuestionGeneratorConfig",
    "SENSOR_WAVEFORM_MODALITIES",
    "SEVEN_DIMENSION_NAMES",
    "SPEAKER_TOPOLOGIES",
    "SevenDimensionQuestionGenerator",
    "generate_cleaning_dataset",
]


# ---------------------------------------------------------------------------
# Factor catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersonaFactor:
    code: str
    label: str
    age: int
    focus: str
    situation: str
    likely_roles: tuple[str, ...]

    @property
    def persona_tag(self) -> str:
        return f"{self.code}_{self.label}_{self.age}岁_{self.focus}"


@dataclass(frozen=True, slots=True)
class EventFactor:
    code: str
    domain: str
    domain_label: str
    title: str
    semantic_intent: str
    source_channel: str
    keywords: tuple[str, ...]
    core_template: str
    anchor_template: tuple[str, ...]
    counterparty_roles: tuple[str, ...]
    amount_kind: str = "none"


@dataclass(frozen=True, slots=True)
class SensorFactor:
    code: str
    label: str
    motion_state: str
    profile: str


@dataclass(frozen=True, slots=True)
class AcousticFactor:
    code: str
    label: str
    noise_db: float
    topology: str
    noise_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinguisticFactor:
    code: str
    label: str
    register: str
    opening_lines: tuple[str, ...]
    pragmatic_note: str


@dataclass(frozen=True, slots=True)
class SpeakerTopology:
    code: str
    label: str
    roles: tuple[str, ...]
    overlapping: bool


@dataclass(frozen=True, slots=True)
class TrapFactor:
    code: str
    label: str
    description: str
    semantic_intent: str
    dimension: str
    keywords: tuple[str, ...]


DEMOGRAPHIC_PERSONAS: tuple[PersonaFactor, ...] = (
    PersonaFactor("D01", "高三复读生", 17, "失眠焦虑与家庭高压", "备考期间失眠、躯体化焦虑，和父母共用一间陪读房", ("spk_user", "spk_parent", "spk_teacher")),
    PersonaFactor("D02", "互联网外包工程师", 24, "通宵排障与合租纠纷", "连续夜班排查故障，租住的隔断间漏水并被主管甩锅", ("spk_user", "spk_boss", "spk_roommate")),
    PersonaFactor("D03", "孕晚期准妈妈", 28, "胎动记录与产检危机", "记录胎动和妊娠期血糖，家人围绕月嫂安排意见不一", ("spk_user", "spk_spouse", "spk_doctor")),
    PersonaFactor("D04", "长途重卡司机", 32, "疲劳驾驶与高原运输", "长途运输经过高海拔路段，遇到堵车、别车和油卡异常", ("spk_user", "spk_dispatcher", "spk_police")),
    PersonaFactor("D05", "失业离异二房东", 36, "租金抚养费与胃出血", "原房东起诉、租客欠租，另一边还要处理孩子抚养费和胃部急症", ("spk_user", "spk_landlord", "spk_ex_spouse")),
    PersonaFactor("D06", "急诊科住院总医师", 42, "连轴值班与医疗纠纷", "连续值班后处理高暴露风险，急诊分诊台还有家属和纠纷当事人", ("spk_user", "spk_doctor", "spk_family")),
    PersonaFactor("D07", "建筑工地钢筋班包工头", 48, "痛风并发讨薪", "管理钢筋班和结算工资，工人围堵讨薪时脚趾痛风发作", ("spk_user", "spk_worker", "spk_contractor")),
    PersonaFactor("D08", "民营企业财务总监", 53, "假发票稽查与更年期", "核对大额发票时税务稽查突然到访，还要处理家庭礼金争执", ("spk_user", "spk_tax_officer", "spk_boss")),
    PersonaFactor("D09", "初老退休教师", 65, "养老买房与认知变化", "候鸟养老房投资受挫，参加保健品讲座并陪伴老伴做眼科手术", ("spk_user", "spk_spouse", "spk_salesperson")),
    PersonaFactor("D10", "独居空巢老人", 78, "走失风险与居家安全", "骨质疏松且偶有忘事，家中煤气和邻里漏水都需要留意", ("spk_user", "spk_neighbor", "spk_child")),
    PersonaFactor("D11", "户外越野攀岩者", 30, "悬崖自救与失温", "在卫星电话盲区发生悬挂险情，需要处理脱水、失温和骨折", ("spk_user", "spk_climbing_partner", "spk_rescuer")),
    PersonaFactor("D12", "乡村外卖骑手", 22, "暴雨送单与车辆纠纷", "暴雨中送单遭遇超时罚款，电瓶车和商户冲突同时出现", ("spk_user", "spk_merchant", "spk_customer")),
    PersonaFactor("D13", "中式餐饮连锁店主", 45, "抽检危机与供应商催款", "食品安全抽检、厨师罢工和供应商欠款在同一周集中爆发", ("spk_user", "spk_chef", "spk_supplier")),
    PersonaFactor("D14", "远洋轮机长", 38, "海上航行与幽闭耳鸣", "连续航行四十天，卫星断网后还要处理机舱噪声和幽闭不适", ("spk_user", "spk_captain", "spk_family")),
    PersonaFactor("D15", "自由插画师", 26, "版权维权与宠物急症", "颈椎压迫导致手麻，甲方反复改稿，家中宠物还出现重症", ("spk_user", "spk_client", "spk_vet")),
)


# The event catalogue is intentionally broader than the old benchmark's five
# stories.  The 26 entries are shuffled as one balanced cycle by the generator;
# therefore the smallest domain (daily contracts) still exceeds 15% in a 10K set.
CORE_EVENT_SPECTRUM: tuple[EventFactor, ...] = (
    # health / physiology
    EventFactor("H01", "dim:health", "健康生理", "隐匿性下壁心肌梗死先兆", "HIDDEN_CARDIAC_ISCHEMIA", "mic", ("上腹不适", "冷汗", "胸闷", "急诊评估", "心肌梗死先兆"), "{subject}原以为是胃部消化不良，{time_phrase}却出现持续上腹压迫感、冷汗和气短；{clinician}提醒这组表现不能按普通胃痛处理，不能排除下壁心肌梗死先兆，应立即做心电图和心肌标志物检查。", ("佩戴者", "上腹压迫感", "冷汗", "心肌梗死先兆"), ("急诊医生", "家属")),
    EventFactor("H02", "dim:health", "健康生理", "痛风石破溃感染", "INFECTED_GOUT_TOPHUS", "dialogue", ("痛风急性发作", "脚趾红肿", "痛风石破溃", "伤口感染", "无法着地"), "{subject}的{body_part}红肿灼痛，痛风石破溃后有渗液和发热；{clinician}说这不只是忍痛走路的问题，需要尽快清创并排查感染，不能自行加量止痛。", ("佩戴者", "红肿灼痛", "痛风石破溃", "渗液和发热"), ("社区医生", "家人"), "small_money"),
    EventFactor("H03", "dim:health", "健康生理", "颈椎压迫性眩晕跌坐", "CERVICAL_COMPRESSION_DIZZINESS", "mic", ("颈椎压迫", "眩晕", "眼球震颤", "跌坐", "不是绊倒"), "{subject}转头后突然天旋地转并跌坐在椅边，旁人发现有短暂眼球震颤；佩戴者强调并不是被地面绊倒，{clinician}建议评估颈椎和神经体征。", ("佩戴者", "转头后", "眼球震颤", "跌坐"), ("康复医生", "同事")),
    EventFactor("H04", "dim:health", "健康生理", "药物过敏性休克", "DRUG_ALLERGY_SHOCK", "mic", ("药物过敏", "皮疹", "气促", "过敏性休克", "停药就医"), "{subject}用药后先起大片风团，随后声音嘶哑、气促和头晕；{clinician}将其作为疑似严重药物过敏处理，要求立即停用可疑药物并呼叫急救，而不是继续观察。", ("佩戴者", "大片风团", "气促", "疑似严重药物过敏"), ("急诊护士", "陪同者")),
    EventFactor("H05", "dim:health", "健康生理", "运动后横纹肌溶解风险", "EXERTIONAL_RHABDOMYOLYSIS", "dialogue", ("剧烈运动", "浓茶色尿", "肌肉酸痛", "横纹肌溶解", "补液检查"), "{subject}完成高强度训练后肌肉异常酸痛，尿色像浓茶；{clinician}提醒这不是普通运动后酸胀，需要检查肌酸激酶、肾功能并及时补液。", ("佩戴者", "高强度训练", "尿色像浓茶", "肌酸激酶"), ("运动医学医生", "训练伙伴"), "small_money"),
    EventFactor("H06", "dim:health", "健康生理", "狂躁与抑郁交替风险", "BIPOLAR_EPISODE_RISK", "dialogue", ("狂躁期", "冲动消费", "抑郁期", "自伤念头", "精神科评估"), "{subject}连续几天几乎不睡、异常兴奋并冲动消费，随后又说不想醒来；{clinician}认为这是需要尽快进行精神科风险评估的情绪交替，不应被当作单纯任性或玩笑。", ("佩戴者", "几乎不睡", "冲动消费", "不想醒来"), ("精神科医生", "家属"), "small_money"),
    # finance / civil and commercial law
    EventFactor("F01", "dim:finance", "财务民商", "婚前财产隐匿转移", "HIDDEN_PREMARITAL_ASSET_TRANSFER", "app", ("婚前财产", "隐匿转移", "共同账户", "财产分割", "流水取证"), "{subject}在协议离婚前发现{counterparty}把一笔婚前存款绕转到亲属账户；律师建议先固定银行流水和时间线，再区分婚前个人财产与婚后共同财产。", ("佩戴者", "婚前存款", "亲属账户", "银行流水"), ("配偶", "律师"), "large_money"),
    EventFactor("F02", "dim:finance", "财务民商", "遗嘱公证现场争执", "INHERITANCE_WILL_DISPUTE", "mic", ("遗嘱公证", "遗产争议", "分家析产", "继承人争执", "公证处"), "{subject}在{counterparty}的遗嘱公证现场，几名继承人围绕房产和存款份额争吵；公证员要求先核验行为能力、遗嘱形式和分家析产协议，不能靠现场喊价决定继承。", ("佩戴者", "遗嘱公证", "继承人", "分家析产协议"), ("公证员", "兄弟姐妹"), "large_money"),
    EventFactor("F03", "dim:finance", "财务民商", "虚拟货币传销盘崩盘", "CRYPTO_PONZI_COLLAPSE", "app", ("虚拟货币", "传销盘", "崩盘跑路", "追偿", "资金链断裂"), "{subject}参与的所谓数字资产项目突然停止提现，群管理员称系统升级后失联；聊天和充值流水显示它更像层级返利盘，{counsel}建议保存证据并通过正规渠道报案追偿。", ("佩戴者", "停止提现", "层级返利", "充值流水"), ("项目管理员", "法律援助人员"), "large_money"),
    EventFactor("F04", "dim:finance", "财务民商", "天使轮对赌连带清偿", "INVESTMENT_GUARANTEE_LIABILITY", "app", ("天使轮融资", "对赌失败", "无限连带责任", "清偿通知", "股东协议"), "{subject}收到天使轮对赌目标未达成的连带清偿通知，投资文件把个人保证、公司债务和回购条件混在一起；{counsel}要求逐页核对签名页和责任范围，不能只看催收短信下结论。", ("佩戴者", "对赌目标", "个人保证", "清偿通知"), ("投资方", "律师"), "large_money"),
    EventFactor("F05", "dim:finance", "财务民商", "二手房连环单违约", "SECOND_HAND_HOME_CHAIN_DEFAULT", "mic", ("二手房交易", "连环单违约", "中介吃差价", "定金", "退房维权"), "{subject}买卖二手房时发现上家、下家和中介被串成连环单，中介隐瞒差价导致一方无法按期过户；{counsel}建议核对网签、定金收据和违约条款，不要在争吵中私下改合同。", ("佩戴者", "网签", "定金收据", "隐瞒差价"), ("中介", "交易对手"), "large_money"),
    EventFactor("F06", "dim:finance", "财务民商", "装修队卷款跑路", "RENOVATION_CONTRACTOR_ABSCONDS", "app", ("装修合同", "卷款跑路", "预付款", "烂尾", "违约索赔"), "{subject}支付装修预付款后，装修队负责人拆完水电便停止联系，现场留下无法居住的烂摊子；合同、转账记录和施工照片应当一并留存，再按约主张退款或违约责任。", ("佩戴者", "装修预付款", "施工照片", "违约责任"), ("装修队负责人", "物业"), "medium_money"),
    # family and interpersonal games
    EventFactor("R01", "dim:social", "家庭人际", "亲子鉴定结果冲击", "NONPATERNITY_DISCLOSURE", "mic", ("亲子鉴定", "非亲生", "养育关系", "家庭冲击", "亲子沟通"), "报告宣读时显示{subject}养育了十年的孩子与其不存在生物学亲子关系；在事实确认后，家人仍需要把孩子的生活照护与情绪安全和成年人的婚姻争议分开处理。", ("佩戴者", "养育了十年", "报告宣读", "孩子"), ("配偶", "鉴定人员")),
    EventFactor("R02", "dim:social", "家庭人际", "父母隐瞒癌症病情", "CONCEALED_TERMINAL_ILLNESS", "dialogue", ("癌症晚期", "隐瞒病历", "异地求医", "家属崩溃", "医疗决定"), "{subject}从整理病历时才知道{counterparty}已经是癌症晚期，家人此前隐瞒病历、用‘只是普通炎症’搪塞；佩戴者需要与正规医院核对诊疗信息，再讨论异地求医、陪诊和治疗选择。", ("佩戴者", "癌症晚期", "隐瞒病历", "异地求医"), ("父母", "主治医生")),
    EventFactor("R03", "dim:social", "家庭人际", "职场言语性骚扰取证", "WORKPLACE_VERBAL_HARASSMENT", "mic", ("言语性骚扰", "职场权力", "录音取证", "下属", "投诉"), "{subject}的直属上级在单独谈话中反复发表带有性意味的言语，并暗示影响排班；佩戴者在同事重叠说话的环境里保留了原始录音取证、聊天和时间线，准备通过正式渠道投诉。", ("佩戴者", "直属上级", "带有性意味的言语", "录音取证"), ("直属上级", "同事")),
    EventFactor("R04", "dim:social", "家庭人际", "合伙人设壳转移客户", "PARTNER_SHELL_COMPANY_TRANSFER", "app", ("合伙人", "壳公司", "知识产权", "客户名单", "转移资产"), "{subject}发现多年合伙人另设壳公司，悄悄把核心代码、客户名单和合同机会迁走；应先核对版本库权限、保密协议和客户往来，区分已证实转移与猜测。", ("佩戴者", "壳公司", "核心代码", "客户名单"), ("创业合伙人", "客户")),
    EventFactor("R05", "dim:social", "家庭人际", "抚养权与伪造探视记录", "CUSTODY_VISITATION_FABRICATION", "mic", ("抚养权", "探视记录", "抢夺孩子", "监护安排", "法院调解"), "{subject}在抚养权争议中发现对方提交了疑似伪造的探视记录，现场还出现强行带走孩子的冲突；记录原件和孩子的安全应交给法院及公安处理，不能自行抢回。", ("佩戴者", "抚养权", "疑似伪造的探视记录", "安全"), ("前配偶", "调解员")),
    # career / education and turning points
    EventFactor("C01", "dim:career", "职业学业", "学位论文盲审大修", "THESIS_BLIND_REVIEW_REVISION", "app", ("论文盲审", "大修", "导师决裂", "学位答辩", "学术记录"), "{subject}收到硕士或博士论文双盲大修意见后，与导师在署名和研究路线问题上决裂；盲审意见、版本差异和沟通记录需要分开归档，不能把情绪争执当作学术结论。", ("佩戴者", "双盲大修", "版本差异", "导师"), ("导师", "学院秘书")),
    EventFactor("C02", "dim:career", "职业学业", "劳动仲裁考勤对质", "LABOR_ARBITRATION_ATTENDANCE_DISPUTE", "mic", ("劳动仲裁", "考勤记录", "加班", "HR伪造", "举证"), "劳动仲裁开庭时{subject}拿出门禁记录和项目日志，与公司HR提交的考勤表逐项对质；佩戴者主张加班事实，仲裁庭要求说明每份电子记录的来源和完整性，而不是只听双方口头指责。", ("佩戴者", "劳动仲裁", "门禁记录", "考勤表"), ("仲裁员", "公司HR"), "medium_money"),
    EventFactor("C03", "dim:career", "职业学业", "竞业限制追偿诉讼", "NONCOMPETE_REPAYMENT_LITIGATION", "app", ("竞业限制", "追偿", "二百万元", "补偿金", "诉讼"), "{subject}离职后收到竞业限制追偿诉状，金额主张约二百万元；合同是否有效、公司是否持续支付补偿金以及新工作是否属于竞争业务，都需要由证据和法律程序确认。", ("佩戴者", "竞业限制追偿诉状", "二百万元", "补偿金"), ("原公司", "代理律师"), "large_money"),
    EventFactor("C04", "dim:career", "职业学业", "公职考试递补政审", "CIVIL_SERVICE_BACKUP_BACKGROUND_CHECK", "app", ("公职考试", "面试递补", "政审", "材料核验", "通知期限"), "{subject}在国家公职考试面试递补后，政审通知要求在很短期限内补交异地经历材料并完成材料核验；佩戴者需要按官方通知核验渠道和期限，不把群聊里的‘内定消息’当成正式结果。", ("佩戴者", "面试递补", "政审通知", "材料核验"), ("招录机关", "亲属")),
    EventFactor("C05", "dim:career", "职业学业", "外贸订单海关查扣", "CUSTOMS_DETENTION_LETTER_OF_CREDIT", "app", ("外贸订单", "海关查扣", "信用证", "承兑危机", "单证不符"), "{subject}的核心外贸货物被海关查扣，境外买方又提示信用证单证不符；报关单、提单、银行承兑和查扣文书必须分别核验，不能凭供应商一句‘马上放行’安排发货。", ("佩戴者", "海关查扣", "信用证", "报关单"), ("报关行", "境外买方"), "large_money"),
    # daily contracts and accidents
    EventFactor("L01", "dim:life", "生活契约", "租屋下水倒灌索赔", "RENTAL_SEWAGE_FLOOD_CLAIM", "mic", ("租房", "下水倒灌", "物品浸泡", "房屋索赔", "物业责任"), "{subject}租住的房屋夜间发生下水管道倒灌，摄影器材和收藏品被污水浸泡；佩戴者保留物业报修时间、物品清单和现场影像，和房东、物业协商责任范围。", ("佩戴者", "下水管道倒灌", "摄影器材", "物业报修"), ("房东", "物业人员"), "large_money"),
    EventFactor("L02", "dim:life", "生活契约", "宠物犬扑倒幼童调解", "PET_DOG_CHILD_INJURY_MEDIATION", "mic", ("宠物犬", "幼童", "扑倒", "派出所调解", "责任争议"), "{subject}外出遛犬时，宠物扑倒路边幼童，双方家长在派出所围绕牵引绳和医疗费用争执；后续应以监控、就诊单和饲养规定厘清责任，避免现场升级。", ("佩戴者", "宠物", "幼童", "派出所"), ("幼童家长", "民警"), "medium_money"),
    EventFactor("L03", "dim:life", "生活契约", "泡水二手车退车维权", "FLOODED_USED_CAR_RETURN", "app", ("二手车", "泡水事故车", "第三方检测", "退车", "隐蔽瑕疵"), "{subject}购买的二手车被第三方检测发现曾经泡水，卖家此前只说是‘轻微维修’；检测报告、合同披露和付款记录构成退车或索赔谈判的证据链。", ("佩戴者", "曾经泡水", "第三方检测", "退车"), ("二手车商", "检测员"), "large_money"),
    EventFactor("L04", "dim:life", "生活契约", "境外自驾事故求救", "OVERSEAS_DRIVING_ACCIDENT_ASSISTANCE", "dialogue", ("境外自驾", "交通事故", "当地警方", "语言不通", "紧急求救"), "{subject}在境外自驾发生车辆碰撞，与当地警方沟通时存在语言障碍；应先确认人身安全、呼叫当地急救和警方，再通过保险公司或翻译协助处理责任与记录。", ("佩戴者", "境外自驾", "车辆碰撞", "警方"), ("当地警员", "保险救援人员"), "large_money"),
)


SENSOR_WAVEFORM_MODALITIES: tuple[SensorFactor, ...] = (
    SensorFactor("S01", "高G剧烈冲击后静止", "IMPACT_THEN_STILL", "15G至35G冲击峰，随后姿态长时间近乎不变，优先检查严重坠落或车祸"),
    SensorFactor("S02", "虚假冲击对冲", "IMPACT_WITH_CONTINUOUS_MOTION", "单峰磕碰或扣杀峰值，但之后保持连续挥拍、鼓掌或步行，不能只凭一个峰值判定跌倒"),
    SensorFactor("S03", "夜间恶性心律失常", "NIGHT_REST_TACHY_PVC", "静止夜间心率从约60突升至210，伴连续PVC阵发，和运动性心率升高不同"),
    SensorFactor("S04", "缓慢性心脏停搏", "SINUS_PAUSE_BALANCE_LOSS", "窦性停搏约3.8秒，心率下探至32并伴失衡下沉，需要与普通坐下区分"),
    SensorFactor("S05", "气压海拔骤变", "BARO_DROP_WEATHER_SHIFT", "低气压和暴风雨来临前气压约下降20hPa，温湿度及体感同步变化"),
    SensorFactor("S06", "跑步正常基线偏移", "RUNNING_NORMAL_BASELINE", "配速约4分30秒、心率165且规律摆臂，属于运动基线，不应误报心梗或抽搐"),
)


AMBIENT_ACOUSTIC_TOPOLOGIES: tuple[AcousticFactor, ...] = (
    AcousticFactor("A01", "早晚高峰地铁换乘通道", 85.0, "轨道啸叫、循环广播、密集踏步、摊贩叫卖", ("下一站换乘请注意脚下", "轨道摩擦声盖过了半句话", "有摊主在通道边喊扫码优惠", "人群脚步连续经过")),
    AcousticFactor("A02", "露天海鲜农贸市场", 78.0, "剁骨刀、方言讨价还价、塑料袋撕拉", ("鲜活海鱼刚到货要不要看一下", "砧板重击声一阵接一阵", "老板和顾客隔着摊位讨价还价", "塑料袋被迅速撕开")),
    AcousticFactor("A03", "冲压车间与机加工厂房", 90.0, "气阀排气、金属切削尖啸、工人隔空喊话", ("安全帽戴好再进这条线", "金属切削声把前半句盖住", "气阀排气突然冲了一声", "远处工人在喊停机检查")),
    AcousticFactor("A04", "三甲医院急诊分诊台", 65.0, "监护仪哔声、救护车警报、哭号推搡、叫号", ("请三十六号到二号分诊台", "监护仪在背景里规律发出提示音", "救护车警报从门外由远及近", "家属在分诊台请求解释")),
    AcousticFactor("A05", "深夜高速长途大巴", 50.0, "发动机低频共振、鼾声、手机短视频外放", ("前方服务区停车十五分钟", "发动机低频嗡鸣持续不断", "后排手机短视频漏出一段对白", "车厢里有人打着鼾")),
    AcousticFactor("A06", "婚庆宴席大厅", 80.0, "司仪混响回授、敬酒猜拳、碗盘碰撞、儿童奔跑", ("请新人面向来宾举杯", "音响回授突然尖啸", "邻桌猜拳和劝酒声重叠", "瓷盘被奔跑的孩子碰得一响")),
    AcousticFactor("A07", "暴风雨夜户外营地", 70.0, "雨点密砸帐篷、风绳呼啸、远近闷雷", ("风绳又被吹松了一根", "雨点打在帆布上像连续敲击", "闷雷在山谷里滚过去", "有人隔着帐篷喊检查电源")),
)


LINGUISTIC_PROFILES: tuple[LinguisticFactor, ...] = (
    LinguisticFactor("LNG01", "四川口语", "四川话", ("我把话给你摆清楚哈：", "硬是不能把这个当小事："), "语气直接、带地方口头助词；事实仍以时间线和证据为准"),
    LinguisticFactor("LNG02", "东北口语", "东北话", ("别搁这儿跟我绕弯子：", "我就问你一句实在的："), "夸张语气可能是表达方式，不能把气话自动当成现实行动"),
    LinguisticFactor("LNG03", "粤语口语", "粤语", ("阿叔，今次真系要讲清楚：", "唔好净系话冇事："), "方言中的身体不适和求助仍需结合传感器及就医线索"),
    LinguisticFactor("LNG04", "陕西口语", "陕西方言", ("额把证据和话都摆到这儿：", "甭跟额装糊涂，这事得照记录来："), "地方词汇可能隐含合同、土地或家事关系，需保留实体"),
    LinguisticFactor("LNG05", "上海口语", "上海话", ("侬先不要急，事情一桩桩讲：", "阿拉先把凭据对一遍："), "家庭和产权争执中的反问不等于事实承认"),
    LinguisticFactor("LNG06", "正式法律文书", "法务书面语", ("现就事实与证据作如下说明：", "根据现有材料，先区分已证实事项："), "重视举证、责任范围和保留意见，不替当事人扩张结论"),
    LinguisticFactor("LNG07", "网络反讽", "反讽口吻", ("行啊，你可真是‘安排得明明白白’：", "好一个‘没问题’，那就看记录吧："), "正话反说是主要对抗点，必须结合后续行为与反证"),
    LinguisticFactor("LNG08", "医院交班黑话", "医疗交班语", ("交班先报重点，不绕弯：", "这个信号要按急症路径看："), "不能因为患者说没事就忽略客观危险指标"),
    LinguisticFactor("LNG09", "职场缓和话术", "职场委婉语", ("我们先把口径对齐一下：", "这件事可以再‘优化’一下，但记录要留着："), "委婉词可能遮掩拒绝、甩锅或变更承诺"),
    LinguisticFactor("LNG10", "乡土日常口语", "乡土俚语", ("咱不说虚的，就按眼前这件事：", "乡里乡亲也得把账算明白："), "亲熟称呼不等于法律授权或付款已经发生"),
)


SPEAKER_TOPOLOGIES: tuple[SpeakerTopology, ...] = (
    SpeakerTopology("V01", "三人核心对话", ("spk_user", "spk_interlocutor", "spk_stranger_noise"), False),
    SpeakerTopology("V02", "家庭四人重叠", ("spk_user", "spk_spouse", "spk_parent", "spk_stranger_noise"), True),
    SpeakerTopology("V03", "职场六人会议", ("spk_user", "spk_boss", "spk_hr", "spk_colleague", "spk_witness", "spk_stranger_noise"), True),
    SpeakerTopology("V04", "医院八人分诊", ("spk_user", "spk_doctor", "spk_nurse", "spk_family", "spk_security", "spk_patient", "spk_clerk", "spk_stranger_noise"), True),
    SpeakerTopology("V05", "市场十二人混声", ("spk_user", "spk_vendor", "spk_creditor", "spk_customer", "spk_child", "spk_neighbor", "spk_delivery", "spk_police", "spk_bystander_01", "spk_bystander_02", "spk_bystander_03", "spk_stranger_noise"), True),
    SpeakerTopology("V06", "法律调解十五人", ("spk_user", "spk_lawyer", "spk_mediator", "spk_counterparty", "spk_witness", "spk_family", "spk_clerk", "spk_police", "spk_expert", "spk_observer_01", "spk_observer_02", "spk_observer_03", "spk_stranger_01", "spk_stranger_02", "spk_stranger_noise"), True),
    SpeakerTopology("V07", "工地十八人抢话", tuple(["spk_user", "spk_boss", "spk_worker_01", "spk_worker_02", "spk_worker_03", "spk_creditor", "spk_safety", "spk_security", "spk_family", "spk_supplier", "spk_police", "spk_observer_01", "spk_observer_02", "spk_bystander_01", "spk_bystander_02", "spk_stranger_01", "spk_stranger_02", "spk_stranger_noise"]), True),
    SpeakerTopology("V08", "大型公共空间二十四人", tuple(["spk_user", "spk_spouse", "spk_doctor", "spk_boss", "spk_creditor", "spk_lawyer", "spk_police", "spk_vendor", "spk_neighbor", "spk_customer", "spk_family", "spk_nurse", "spk_hr", "spk_colleague", "spk_witness", "spk_child", "spk_delivery", "spk_security", "spk_bystander_01", "spk_bystander_02", "spk_bystander_03", "spk_stranger_01", "spk_stranger_02", "spk_stranger_noise"]), True),
)


ADVERSARIAL_TRAPS: tuple[TrapFactor, ...] = (
    TrapFactor("T01", "转账截图与银行失败反转", "先出现一张十万元转账截图，随后银行应用显示对方账户状态异常、实际转账失败。", "TRANSFER_SCREENSHOT_REVERSED_BY_BANK_FAILURE", "dim:finance", ("转账截图", "银行失败", "账户状态异常", "未实际到账", "反事实核验")),
    TrapFactor("T02", "先同意离婚后短信反悔", "录音中答应次日九点协议离婚，两个小时后短信改口拒绝，承诺和后续反悔都要保留。", "PROMISE_RETRACTED_AFTER_AGREEMENT", "dim:social", ("协议离婚承诺", "反悔短信", "先承认", "后拒绝", "时间线冲突")),
    TrapFactor("T03", "撤回承诺与手滑说辞", "群聊发出违规或付款承诺后很快撤回，再私聊称误发；撤回不等于事件从未发生。", "RETRACTED_MESSAGE_REMAINS_EVIDENCE", "dim:career", ("撤回消息", "违规承诺", "手滑说辞", "原始记录", "证据保全")),
    TrapFactor("T04", "无冲击假摔碰瓷", "IMU只有平稳顺势躺倒而无碰撞波峰，麦克风却大声呼痛并索赔五万元，需识别证据冲突。", "FRAUDULENT_INJURY_CLAIM_WITHOUT_IMPACT", "dim:life", ("无碰撞波峰", "顺势躺倒", "呼痛索赔", "五万元", "传感器与语音冲突")),
)

EVENT_DOMAINS: tuple[str, ...] = ("dim:health", "dim:finance", "dim:social", "dim:career", "dim:life")
SEVEN_DIMENSION_NAMES: tuple[str, ...] = (
    "demographic_persona",
    "core_event_spectrum",
    "sensor_waveform",
    "ambient_acoustic",
    "linguistic_profile",
    "speaker_topology",
    "adversarial_trap",
)


# Compatibility names used by the arena dispatch and by small local scripts.
DEMOGRAPHIC_FACTORS = DEMOGRAPHIC_PERSONAS
EVENT_FACTORS = CORE_EVENT_SPECTRUM
SENSOR_FACTORS = SENSOR_WAVEFORM_MODALITIES
ACOUSTIC_ENVIRONMENTS = AMBIENT_ACOUSTIC_TOPOLOGIES
LANGUAGE_PROFILES = LINGUISTIC_PROFILES
SPEAKER_VOICEPRINT_TOPOLOGIES = SPEAKER_TOPOLOGIES
TRAP_FACTORS = ADVERSARIAL_TRAPS


# ---------------------------------------------------------------------------
# Generator implementation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QuestionGeneratorConfig:
    generator_agent: str
    seed: int = DEFAULT_SEED
    count: int = DEFAULT_QUESTION_COUNT
    start_timestamp: datetime = DEFAULT_START

    def __post_init__(self) -> None:
        if not self.generator_agent or not self.generator_agent.strip():
            raise ValueError("generator_agent must not be empty")
        if self.count < 1:
            raise ValueError("count must be positive")
        if self.start_timestamp.tzinfo is None:
            raise ValueError("start_timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DatasetPaths:
    questions: Path
    ground_truth: Path
    count: int


@dataclass(frozen=True, slots=True)
class _Selection:
    persona: PersonaFactor
    event: EventFactor
    sensor: SensorFactor
    acoustic: AcousticFactor
    linguistic: LinguisticFactor
    speakers: SpeakerTopology
    trap: TrapFactor


class SevenDimensionQuestionGenerator:
    """Deterministic, streaming seven-factor question generator.

    ``generate`` uses a shuffled cyclic schedule rather than independent random
    choices.  This gives reproducibility *and* guarantees coverage: 15 personas,
    all 26 events, all six waveforms, all seven acoustic scenes, all ten language
    profiles, all eight speaker topologies and all four traps appear repeatedly in
    a standard 10K run.  A question's seven factor IDs are included in
    ``factor_ids`` so an auditor can verify the Cartesian-product construction.
    """

    def __init__(
        self,
        generator_agent: str | None = None,
        *,
        agent_id: str | None = None,
        generator_id: str | None = None,
        seed: int = DEFAULT_SEED,
        start_timestamp: datetime = DEFAULT_START,
        count: int = DEFAULT_QUESTION_COUNT,
    ) -> None:
        aliases = [value for value in (agent_id, generator_id) if value is not None]
        if len(set(aliases)) > 1:
            raise ValueError("agent_id and generator_id disagree")
        alias = aliases[0] if aliases else None
        if generator_agent is None:
            generator_agent = alias
        elif alias is not None and generator_agent != alias:
            raise ValueError("generator_agent and agent_id disagree")
        if generator_agent is None:
            raise TypeError("generator_agent (or agent_id/generator_id) is required")
        self.config = QuestionGeneratorConfig(
            generator_agent=generator_agent,
            seed=seed,
            count=count,
            start_timestamp=start_timestamp,
        )
        self._orders = self._build_orders(seed)

    @staticmethod
    def _build_orders(seed: int) -> Mapping[str, tuple[int, ...]]:
        rng = random.Random(seed)
        pools: Mapping[str, int] = {
            "persona": len(DEMOGRAPHIC_PERSONAS),
            "event": len(CORE_EVENT_SPECTRUM),
            "sensor": len(SENSOR_WAVEFORM_MODALITIES),
            "acoustic": len(AMBIENT_ACOUSTIC_TOPOLOGIES),
            "linguistic": len(LINGUISTIC_PROFILES),
            "speakers": len(SPEAKER_TOPOLOGIES),
            "trap": len(ADVERSARIAL_TRAPS),
        }
        result: dict[str, tuple[int, ...]] = {}
        for name, size in pools.items():
            order = list(range(size))
            rng.shuffle(order)
            result[name] = tuple(order)
        return result

    def _pick(self, name: str, index: int) -> Any:
        order = self._orders[name]
        return order[index % len(order)]

    def _selection(self, zero_based_index: int) -> _Selection:
        return _Selection(
            persona=DEMOGRAPHIC_PERSONAS[self._pick("persona", zero_based_index)],
            event=CORE_EVENT_SPECTRUM[self._pick("event", zero_based_index)],
            sensor=SENSOR_WAVEFORM_MODALITIES[self._pick("sensor", zero_based_index)],
            acoustic=AMBIENT_ACOUSTIC_TOPOLOGIES[self._pick("acoustic", zero_based_index)],
            linguistic=LINGUISTIC_PROFILES[self._pick("linguistic", zero_based_index)],
            speakers=SPEAKER_TOPOLOGIES[self._pick("speakers", zero_based_index)],
            trap=ADVERSARIAL_TRAPS[self._pick("trap", zero_based_index)],
        )

    @staticmethod
    def _stable_number(text: str) -> int:
        """A process-independent small hash (built-in ``hash`` is randomized)."""

        return sum((position + 1) * ord(char) for position, char in enumerate(text))

    def _counterparty(self, selection: _Selection, index: int) -> str:
        pools: Mapping[str, tuple[str, ...]] = {
            "急诊医生": ("周医生", "梁医生", "值班医生"),
            "社区医生": ("许医生", "社区护士"),
            "康复医生": ("康复师林老师", "神经科医生"),
            "急诊护士": ("分诊护士", "急救医生"),
            "运动医学医生": ("运动医学张医生", "急诊医生"),
            "精神科医生": ("精神科医生", "心理治疗师"),
            "配偶": ("陈女士", "赵先生", "配偶"),
            "公证员": ("公证员", "继承调解员"),
            "项目管理员": ("项目管理员阿凯", "群主"),
            "投资方": ("投资方代表", "基金法务"),
            "中介": ("房产中介周某", "交易中介"),
            "装修队负责人": ("装修队负责人", "施工队老板"),
            "父母": ("母亲", "父亲"),
            "上级": ("直属主管", "部门负责人"),
            "创业合伙人": ("创业合伙人赵某", "原合伙人"),
            "前配偶": ("前配偶", "孩子另一方监护人"),
            "导师": ("导师", "课题组负责人"),
            "仲裁员": ("仲裁员", "庭审记录员"),
            "原公司": ("原公司法务", "原雇主"),
            "招录机关": ("招录机关工作人员", "政审联系人"),
            "报关行": ("报关行顾问", "境外买方"),
            "房东": ("房东", "物业经理"),
            "幼童家长": ("幼童家长", "现场民警"),
            "二手车商": ("二手车商", "卖家"),
            "当地警员": ("当地警员", "保险救援人员"),
        }
        role = selection.event.counterparty_roles[(index + self._stable_number(selection.event.code)) % len(selection.event.counterparty_roles)]
        choices = pools.get(role, (role,))
        return choices[(index + self._stable_number(selection.persona.code)) % len(choices)]

    def _amount(self, kind: str, index: int) -> str:
        if kind == "large_money":
            return f"{(index % 17 + 2) * 10}万元"
        if kind == "medium_money":
            return f"{(index % 9 + 2) * 1000}元"
        if kind == "small_money":
            return f"{(index % 6 + 1) * 500}元"
        return ""

    def _render_event(self, selection: _Selection, index: int) -> tuple[str, list[str], str, str]:
        event = selection.event
        counterparty = self._counterparty(selection, index)
        clinician = counterparty
        amount = self._amount(event.amount_kind, index)
        body_part = ("右脚第一跖趾关节", "左脚拇趾", "足背")[index % 3]
        time_phrase = ("午饭后", "夜班结束后", "清晨醒来时", "长途停车时")[index % 4]
        text = event.core_template.format(
            subject="佩戴者",
            counterparty=counterparty,
            clinician=clinician,
            counsel=counterparty,
            body_part=body_part,
            time_phrase=time_phrase,
            amount=amount,
        )
        if amount and amount not in text:
            text += f"相关记录中的金额约为{amount}。"
        if counterparty not in text:
            text += f"相关记录中的关键联系人标注为{counterparty}。"
        opening = selection.linguistic.opening_lines[index % len(selection.linguistic.opening_lines)]
        # The opening makes language style observable without changing the event's
        # factual payload.  It is deliberately not used as a fact by itself.
        rendered = f"{opening}{text}"
        anchors: list[str] = []
        for anchor in event.anchor_template:
            anchors.append(anchor.format(subject="佩戴者", counterparty=counterparty, amount=amount))
        if counterparty not in anchors:
            anchors.append(counterparty)
        if amount and amount not in anchors:
            anchors.append(amount)
        return rendered, anchors, counterparty, amount

    def _sensor_stream(self, selection: _Selection, index: int) -> tuple[dict[str, Any], DirectionalSemanticFact]:
        sensor = selection.sensor
        packet_id = "sensor_01"
        phase = (index % 9) / 9.0
        # T04 is an explicit counterfactual override: its defining evidence is the
        # absence of an impact peak even if S01 happened to be selected.  The
        # selected S-code remains visible in factor_ids for auditability.
        if selection.trap.code == "T04":
            raw_imu = [1.01, 0.99, 1.03, 1.00, 1.02]
            stream: dict[str, Any] = {
                "sensor_packet_id": packet_id,
                "raw_imu_g_force": raw_imu,
                "peak_g_force": 1.03,
                "heart_rate_bpm": 96 + index % 12,
                "pvc_burst_count": 0,
                "baro_hpa": round(1008.0 - phase * 2.0, 1),
                "motion_state": "CONTROLLED_SIT_TO_FLOOR",
                "waveform_factor": sensor.code,
                "waveform_label": sensor.label,
                "counterfactual_override": "T04_NO_IMPACT_PEAK",
                "is_junk": False,
            }
            fact = DirectionalSemanticFact(
                fact_id="fact_sensor",
                dimension_id="dim:life",
                semantic_intent="FRAUDULENT_INJURY_CLAIM_WITHOUT_IMPACT",
                anchor_entities=["佩戴者", "无碰撞波峰", "顺势躺倒"],
                directional_keywords=["无碰撞波峰", "低G", "顺势躺倒", "传感器冲突", "假摔"],
                core_content="IMU峰值约1.03G且没有撞击波形，佩戴者是平稳顺势躺倒；这与麦克风中的五万元呼痛索赔相冲突，不能仅凭喊痛认定受伤。",
                source_ref_id=packet_id,
            )
            return stream, fact
        if sensor.code == "S01":
            raw_imu = [18.2, 24.7, 31.4, 22.1, 16.9]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": max(raw_imu), "heart_rate_bpm": 128, "pvc_burst_count": 1, "baro_hpa": 1007.2, "motion_state": "HIGH_IMPACT_THEN_STILL", "waveform_factor": sensor.code, "post_impact_still_s": 46.0, "is_junk": False}
            intent, keywords, content = "SEVERE_IMPACT_WITH_POST_IMPACT_STILLNESS", ["高G冲击", "撞击峰", "长时间静止", "跌倒风险", "急救评估"], "传感器记录到约31G的剧烈冲击，随后姿态近乎静止46秒；这是需要优先核查人身安全的高风险波形，不能当作普通磕碰。"
        elif sensor.code == "S02":
            raw_imu = [1.0, 1.1, 6.8, 1.2, 1.4, 1.0, 1.3]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": 6.8, "heart_rate_bpm": 142, "pvc_burst_count": 0, "baro_hpa": 1009.1, "motion_state": "CONTINUOUS_SWINGING", "waveform_factor": sensor.code, "continuous_motion_s": 18.0, "is_junk": False}
            intent, keywords, content = "FALSE_IMPACT_DURING_CONTINUOUS_MOTION", ["单峰冲击", "连续挥动", "没有静止", "普通磕碰", "非跌倒"], "IMU只有一个约6.8G峰值，但前后持续挥拍或鼓掌18秒且没有倒地后的静止段；它更符合虚假冲击，不足以证明跌倒。"
        elif sensor.code == "S03":
            raw_imu = [0.99, 1.01, 1.00, 1.02, 1.00]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": 1.02, "heart_rate_bpm": 210, "heart_rate_baseline_bpm": 60, "pvc_burst_count": 9, "baro_hpa": 1011.3, "motion_state": "NIGHT_REST", "heart_rate_transition_s": 12.0, "is_junk": False}
            intent, keywords, content = "NIGHT_TACHYCARDIA_PVC_BURST", ["静息心率飙升", "210bpm", "室性早搏", "PVC阵发", "心律失常"], "夜间静止时心率由约60升到210bpm并出现9次PVC阵发；这是心律异常信号，不应被背景噪声或‘只是紧张’的说法覆盖。"
        elif sensor.code == "S04":
            raw_imu = [1.0, 0.98, 1.04, 1.01, 0.99]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": 1.04, "heart_rate_bpm": 32, "heart_rate_baseline_bpm": 68, "pvc_burst_count": 0, "sinus_pause_s": 3.8, "baro_hpa": 1006.6, "motion_state": "BALANCE_LOSS_SLOW_SINK", "is_junk": False}
            intent, keywords, content = "SINUS_PAUSE_WITH_BALANCE_LOSS", ["窦性停搏", "3.8秒", "心率32", "失衡下沉", "短暂停搏"], "监测到约3.8秒窦性停搏，心率下探至32bpm并伴随身体失衡下沉；这不同于主动坐下，应作为危险体征核验。"
        elif sensor.code == "S05":
            raw_imu = [1.0, 1.02, 0.99, 1.01, 1.0]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": 1.02, "heart_rate_bpm": 104, "pvc_burst_count": 0, "baro_hpa": 988.2, "baro_baseline_hpa": 1008.2, "temperature_c": 12.4, "humidity_pct": 94.0, "motion_state": "WEATHER_EXPOSURE", "is_junk": False}
            intent, keywords, content = "BAROMETRIC_STORM_SHIFT", ["气压骤降", "20hPa", "暴风雨", "湿度突变", "失温风险"], "气压从约1008.2hPa降到988.2hPa，湿度升高且体感转冷；这是暴风雨和失温风险的环境信号，不是跌倒波形。"
        else:
            raw_imu = [1.02, 1.08, 1.12, 1.06, 1.01]
            stream = {"sensor_packet_id": packet_id, "raw_imu_g_force": raw_imu, "peak_g_force": 1.12, "heart_rate_bpm": 165, "pvc_burst_count": 0, "baro_hpa": 1010.4, "motion_state": "RUNNING_STEADY_BASELINE", "pace_min_per_km": 4.5, "arm_swing": "REGULAR", "is_junk": False}
            intent, keywords, content = "NORMAL_EXERCISE_BASELINE_NOT_CARDIAC_EVENT", ["跑步基线", "规律摆臂", "165bpm运动心率", "配速4分30秒", "非心梗"], "配速约4分30秒、心率165bpm并伴随规律摆臂和正弦波动；它符合跑步运动基线，不能仅凭心率把正常运动误报为心梗。"
        stream["waveform_factor"] = sensor.code
        stream["waveform_label"] = sensor.label
        fact = DirectionalSemanticFact(
            fact_id="fact_sensor",
            dimension_id="dim:health",
            semantic_intent=intent,
            anchor_entities=["佩戴者", sensor.label, str(stream.get("heart_rate_bpm", "")), sensor.motion_state],
            directional_keywords=keywords,
            core_content=content,
            source_ref_id=packet_id,
        )
        return stream, fact

    @staticmethod
    def _key_speaker(selection: _Selection) -> str:
        """Choose a non-noise speaker that is guaranteed in the topology."""

        for speaker in selection.speakers.roles:
            if speaker != "spk_user" and not any(token in speaker for token in ("stranger", "bystander", "ambient")):
                return speaker
        return selection.speakers.roles[1]

    @staticmethod
    def _background_speaker(selection: _Selection) -> str:
        """Choose a topology member suitable for an ambient audio fragment."""

        for speaker in selection.speakers.roles:
            if speaker != "spk_user" and any(token in speaker for token in ("stranger", "bystander", "ambient")):
                return speaker
        return selection.speakers.roles[-1]

    def _noise_snippets(self, selection: _Selection, index: int) -> tuple[list[dict[str, Any]], list[str]]:
        snippets: list[dict[str, Any]] = []
        junk_ids: list[str] = []
        # Four independent noise clips keep the environmental channel genuinely
        # cluttered while keeping a 10K JSONL file practical.
        background_speaker = self._background_speaker(selection)
        for offset in range(4):
            snippet_id = f"mic_noise_{offset + 1:02d}"
            line = selection.acoustic.noise_texts[(index + offset) % len(selection.acoustic.noise_texts)]
            speaker = background_speaker
            snippets.append({
                "snippet_id": snippet_id,
                "speaker_id": speaker,
                "ambient_noise_db": round(selection.acoustic.noise_db + ((index + offset) % 5 - 2) * 0.5, 1),
                "text": line,
                "duration_s": round(1.2 + offset * 0.7, 1),
                "overlap": bool(selection.speakers.overlapping and offset % 2 == 0),
                "is_junk": True,
            })
            junk_ids.append(snippet_id)
        return snippets, junk_ids

    def _app_noise(self, selection: _Selection, index: int) -> tuple[list[dict[str, Any]], list[str]]:
        lines = (
            "恭喜获得会员体验券，点击链接领取，退订回复T。",
            "验证码 483921，五分钟内有效，请勿向任何人透露。",
            "限时直播间满减，转发三位好友即可抽奖。",
            "社区群通知：本周末团购水果，接龙截止今晚八点。",
        )
        messages: list[dict[str, Any]] = []
        junk_ids: list[str] = []
        for offset, line in enumerate(lines):
            msg_id = f"msg_noise_{offset + 1:02d}"
            messages.append({
                "msg_id": msg_id,
                "app": ("SMS", "WeChat", "ShortVideo")[offset % 3],
                "sender": ("营销平台", "验证码服务", "直播商家", "社区群")[offset],
                "content": line,
                "timestamp": self._timestamp(index, offset + 1),
                "is_junk": True,
            })
            junk_ids.append(msg_id)
        return messages, junk_ids

    def _dialogue_noise(self, selection: _Selection, index: int) -> tuple[list[dict[str, Any]], list[str]]:
        lines = (
            "我先去买杯水，等会儿再说。",
            "今天路上真堵，手机也快没电了。",
        )
        utterances: list[dict[str, Any]] = []
        junk_ids: list[str] = []
        for offset, line in enumerate(lines):
            utterance_id = f"ut_noise_{offset + 1:02d}"
            utterances.append({
                "utterance_id": utterance_id,
                "speaker_id": "spk_user" if offset == 0 else self._background_speaker(selection),
                "raw_speech": line,
                "context_scene": selection.acoustic.label,
                "emotional_tone": "routine",
                "is_junk": True,
            })
            junk_ids.append(utterance_id)
        return utterances, junk_ids

    def _trap_streams(
        self,
        selection: _Selection,
        index: int,
        mic: list[dict[str, Any]],
        app: list[dict[str, Any]],
        dialogue: list[dict[str, Any]],
    ) -> tuple[list[DirectionalSemanticFact], list[str]]:
        trap = selection.trap
        facts: list[DirectionalSemanticFact] = []
        junk_ids: list[str] = []
        if trap.code == "T01":
            app.extend([
                {"msg_id": "msg_trap_01", "app": "WeChat", "sender": "交易对方", "content": "我刚给你转了100000元，截图在这儿，别再催了。", "attachment": "transfer_screenshot.png", "is_junk": False},
                {"msg_id": "msg_trap_02", "app": "BankApp", "sender": "银行", "content": "转账失败：对方账户状态异常，款项未实际到账。", "is_junk": False},
            ])
            facts.append(DirectionalSemanticFact(fact_id="fact_trap", dimension_id=trap.dimension, semantic_intent=trap.semantic_intent, anchor_entities=["佩戴者", "十万元", "转账截图", "银行失败", "未实际到账"], directional_keywords=list(trap.keywords), core_content="对方先发十万元转账截图，但银行应用紧接着显示对方账户状态异常、转账失败；应以银行失败记录为事实，不能认定十万元已经到账。", source_ref_id="msg_trap_02"))
        elif trap.code == "T02":
            mic.append({"snippet_id": "mic_trap_01", "speaker_id": self._key_speaker(selection), "ambient_noise_db": selection.acoustic.noise_db, "text": "明早九点去民政局协议离婚，这次我答应了。", "overlap": selection.speakers.overlapping, "is_junk": False})
            app.extend([
                {"msg_id": "msg_trap_01", "app": "SMS", "sender": "对方", "content": "想离门都没有，耗死你。", "timestamp": self._timestamp(index, 4), "is_junk": False},
            ])
            facts.append(DirectionalSemanticFact(fact_id="fact_trap", dimension_id=trap.dimension, semantic_intent=trap.semantic_intent, anchor_entities=["佩戴者", "明早九点", "民政局", "协议离婚", "反悔短信"], directional_keywords=list(trap.keywords), core_content="电话中对方先答应次日九点去民政局协议离婚，约两小时后又发短信拒绝；这是一条先承诺后反悔的冲突时间线，不能抹掉前一段录音。", source_ref_id="msg_trap_01"))
        elif trap.code == "T03":
            app.extend([
                {"msg_id": "msg_trap_01", "app": "WorkChat", "sender": "佩戴者", "content": "我保证本周内把未授权的客户名单发给外部合作方。", "retracted": True, "retracted_after_s": 118, "is_junk": False},
                {"msg_id": "msg_trap_02", "app": "WorkChat", "sender": "同事", "content": "你刚才发错群了？", "is_junk": False},
                {"msg_id": "msg_trap_03", "app": "PrivateChat", "sender": "佩戴者", "content": "刚才手滑发错了，别当真。", "is_junk": False},
            ])
            facts.append(DirectionalSemanticFact(fact_id="fact_trap", dimension_id=trap.dimension, semantic_intent=trap.semantic_intent, anchor_entities=["佩戴者", "未授权客户名单", "撤回消息", "手滑说辞"], directional_keywords=list(trap.keywords), core_content="佩戴者在工作群发出向外部合作方发送未授权客户名单的承诺，约118秒后撤回并称手滑；撤回动作不等于原始消息从未发生，应保留时间线并核查权限。", source_ref_id="msg_trap_01"))
        else:
            mic.append({"snippet_id": "mic_trap_01", "speaker_id": self._key_speaker(selection), "ambient_noise_db": selection.acoustic.noise_db + 1.0, "text": "哎哟我被撞倒了！没有五万块今天别想走！", "overlap": selection.speakers.overlapping, "is_junk": False})
            facts.append(DirectionalSemanticFact(fact_id="fact_trap", dimension_id=trap.dimension, semantic_intent=trap.semantic_intent, anchor_entities=["佩戴者", "无碰撞波峰", "呼痛", "五万元索赔"], directional_keywords=list(trap.keywords), core_content="麦克风记录大声呼痛并索赔五万元，但IMU仅显示平稳顺势躺倒、没有碰撞峰；这是传感器与话语相冲突的疑似假摔索赔，不能把喊痛直接当成受伤事实。", source_ref_id="mic_trap_01"))
        return facts, junk_ids

    def _timestamp(self, index: int, offset: int = 0) -> str:
        # Seven-minute spacing prevents duplicate timestamps while keeping a
        # standard 10K run within one realistic multi-week exam window.
        stamp = self.config.start_timestamp.astimezone(UTC) + timedelta(minutes=index * 7 + offset)
        return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")

    def _difficulty(self, selection: _Selection) -> DifficultyLevel:
        if selection.trap.code in {"T01", "T04"} or selection.sensor.code in {"S03", "S04"}:
            return DifficultyLevel.ADVERSARIAL
        if selection.speakers.overlapping or selection.sensor.code in {"S01", "S02", "S05"}:
            return DifficultyLevel.HARD
        if selection.event.domain in {"dim:finance", "dim:social", "dim:career"}:
            return DifficultyLevel.MEDIUM
        return DifficultyLevel.HARD

    def build_question(self, index: int) -> CleaningQuestion:
        """Build one question using a zero-based index."""

        if index < 0:
            raise ValueError("index must be non-negative")
        selection = self._selection(index)
        event_text, event_anchors, _counterparty, _amount = self._render_event(selection, index)
        sensor_stream, sensor_fact = self._sensor_stream(selection, index)
        mic_stream, junk_ids = self._noise_snippets(selection, index)
        app_stream, app_junk = self._app_noise(selection, index)
        dialogue_stream, dialogue_junk = self._dialogue_noise(selection, index)
        junk_ids.extend(app_junk)
        junk_ids.extend(dialogue_junk)

        event_ref: str
        if selection.event.source_channel == "mic":
            event_ref = "mic_core_01"
            mic_stream.append({"snippet_id": event_ref, "speaker_id": self._key_speaker(selection), "ambient_noise_db": selection.acoustic.noise_db, "text": event_text, "overlap": selection.speakers.overlapping, "is_junk": False})
        elif selection.event.source_channel == "app":
            event_ref = "msg_core_01"
            app_stream.append({"msg_id": event_ref, "app": "WorkChat", "sender": "关键联系人", "content": event_text, "is_junk": False})
        else:
            event_ref = "ut_core_01"
            dialogue_stream.append({"utterance_id": event_ref, "speaker_id": "spk_user", "raw_speech": event_text, "context_scene": selection.acoustic.label, "emotional_tone": "urgent_or_material", "is_junk": False})

        event_fact = DirectionalSemanticFact(
            fact_id="fact_event",
            dimension_id=selection.event.domain,
            semantic_intent=selection.event.semantic_intent,
            anchor_entities=event_anchors,
            directional_keywords=list(selection.event.keywords),
            core_content=event_text,
            source_ref_id=event_ref,
        )
        trap_facts, trap_junk = self._trap_streams(selection, index, mic_stream, app_stream, dialogue_stream)
        junk_ids.extend(trap_junk)

        detected = list(selection.speakers.roles)
        key_speaker = self._key_speaker(selection)
        background_speaker = self._background_speaker(selection)
        segments = [
            {"speaker_id": "spk_user", "role": "wearer", "source_ref_id": event_ref, "confidence": 0.97},
            {"speaker_id": key_speaker, "role": "key_interlocutor", "source_ref_id": event_ref, "confidence": 0.88},
        ]
        if selection.speakers.overlapping:
            segments.append({"speaker_id": background_speaker, "role": "background_overlap", "source_ref_id": "mic_noise_02", "confidence": 0.61})
        voiceprint_cluster = {
            "topology_id": selection.speakers.code,
            "topology_label": selection.speakers.label,
            "user_speaker_id": "spk_user",
            "detected_speakers": detected,
            "speaker_count": len(detected),
            "overlapping_speech": selection.speakers.overlapping,
            "speaker_roles": {speaker: ("wearer" if speaker == "spk_user" else "background_or_interlocutor") for speaker in detected},
            "segments": segments,
            "junk_speaker_ids": [speaker for speaker in detected if "stranger" in speaker or "bystander" in speaker or "ambient" in speaker],
        }

        factor_ids = {
            "demographic": selection.persona.code,
            "core_event": selection.event.code,
            "sensor": selection.sensor.code,
            "acoustic": selection.acoustic.code,
            "linguistic": selection.linguistic.code,
            "speaker_topology": selection.speakers.code,
            "trap": selection.trap.code,
        }
        question_number = index + 1
        question_id = f"Q_{self.config.generator_agent}_{question_number:05d}"
        all_facts = [sensor_fact, event_fact, *trap_facts]
        # Ground truth source references are all present in one of the five
        # streams (or the sensor packet); this invariant catches accidental
        # evidence loss before a file is handed to another agent.
        return CleaningQuestion(
            question_id=question_id,
            generator_agent=self.config.generator_agent,
            timestamp_utc=self._timestamp(index),
            difficulty=self._difficulty(selection),
            persona_tag=selection.persona.persona_tag,
            factor_ids=factor_ids,
            sensor_stream=sensor_stream,
            mic_stream=mic_stream,
            voiceprint_cluster=voiceprint_cluster,
            app_message_stream=app_stream,
            user_dialogue_stream=dialogue_stream,
            ground_truth_junk_ids=sorted(set(junk_ids)),
            ground_truth_facts=all_facts,
        )

    def generate(self, count: int | None = None) -> Iterator[CleaningQuestion]:
        """Yield ``count`` questions (default: configured 10,000)."""

        total = self.config.count if count is None else count
        if total < 1:
            raise ValueError("count must be positive")
        for index in range(total):
            yield self.build_question(index)

    # Friendly aliases used by local scripts and older arena notes.
    iter_questions = generate

    def generate_questions(self, count: int | None = None) -> list[CleaningQuestion]:
        """Materialise a run for callers that prefer a list over a stream."""

        return list(self.generate(count))

    generate_all = generate_questions

    def question_at(self, number: int) -> CleaningQuestion:
        """Return a one-based question number."""

        if number < 1:
            raise ValueError("question number is one-based")
        return self.build_question(number - 1)

    @staticmethod
    def ground_truth_record(question: CleaningQuestion) -> dict[str, Any]:
        """Return the compact answer-key line for the separate GT JSONL file."""

        dumped = question.model_dump(mode="json")
        return {
            "question_id": dumped["question_id"],
            "generator_agent": dumped["generator_agent"],
            "timestamp_utc": dumped["timestamp_utc"],
            "difficulty": dumped["difficulty"],
            "persona_tag": dumped.get("persona_tag"),
            "factor_ids": dumped.get("factor_ids", {}),
            "ground_truth_junk_ids": dumped["ground_truth_junk_ids"],
            "ground_truth_facts": dumped["ground_truth_facts"],
        }

    @staticmethod
    def _file_token(generator_agent: str) -> str:
        token = "".join(char if char.isalnum() or char in "._-" else "_" for char in generator_agent)
        token = token.replace("-", "_") or "agent"
        if not token.lower().startswith("agent"):
            token = f"agent_{token}"
        return token

    def write_jsonl(self, path: str | Path, *, count: int | None = None) -> Path:
        """Write only the question stream to ``path`` and return that path."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as file:
            for question in self.generate(count):
                file.write(json.dumps(question.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) + "\n")
        return destination

    def write_ground_truth_jsonl(self, path: str | Path, *, count: int | None = None) -> Path:
        """Write only the compact answer-key stream to ``path``."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as file:
            for question in self.generate(count):
                file.write(json.dumps(self.ground_truth_record(question), ensure_ascii=False, separators=(",", ":")) + "\n")
        return destination

    def write_dataset(
        self,
        output_dir: str | Path,
        *,
        count: int | None = None,
        questions_path: str | Path | None = None,
        ground_truth_path: str | Path | None = None,
    ) -> DatasetPaths:
        """Stream questions and the corresponding compact GT to two JSONL files."""

        total = self.config.count if count is None else count
        if total < 1:
            raise ValueError("count must be positive")
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        token = self._file_token(self.config.generator_agent)
        q_path = Path(questions_path) if questions_path is not None else root / f"questions_{token}.jsonl"
        gt_path = Path(ground_truth_path) if ground_truth_path is not None else root / f"gt_{token}.jsonl"
        q_path.parent.mkdir(parents=True, exist_ok=True)
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with q_path.open("w", encoding="utf-8", newline="\n") as questions_file, gt_path.open("w", encoding="utf-8", newline="\n") as gt_file:
            for question in self.generate(total):
                question_json = question.model_dump(mode="json")
                questions_file.write(json.dumps(question_json, ensure_ascii=False, separators=(",", ":")) + "\n")
                gt_file.write(json.dumps(self.ground_truth_record(question), ensure_ascii=False, separators=(",", ":")) + "\n")
                written += 1
        return DatasetPaths(q_path, gt_path, written)

    generate_files = write_dataset

    def validate_coverage(self, count: int | None = None) -> dict[str, Any]:
        """Summarise factor/domain coverage without retaining question objects."""

        counters: dict[str, dict[str, int]] = {name: {} for name in SEVEN_DIMENSION_NAMES}
        domain_counts: dict[str, int] = {domain: 0 for domain in EVENT_DOMAINS}
        seen_ids: set[str] = set()
        for question in self.generate(count):
            seen_ids.add(question.question_id)
            for field, key in (("demographic", "demographic_persona"), ("core_event", "core_event_spectrum"), ("sensor", "sensor_waveform"), ("acoustic", "ambient_acoustic"), ("linguistic", "linguistic_profile"), ("speaker_topology", "speaker_topology"), ("trap", "adversarial_trap")):
                value = question.factor_ids.get(field, "")
                counters[key][value] = counters[key].get(value, 0) + 1
            for fact in question.ground_truth_facts:
                if fact.fact_id == "fact_event":
                    domain_counts[fact.dimension_id] = domain_counts.get(fact.dimension_id, 0) + 1
        return {"count": sum(counters["demographic_persona"].values()), "unique_question_ids": len(seen_ids), "factor_counts": counters, "event_domain_counts": domain_counts}


def generate_cleaning_dataset(
    generator_agent: str,
    *,
    output_dir: str | Path = "benchmarks/data_cleaning",
    count: int = DEFAULT_QUESTION_COUNT,
    seed: int = DEFAULT_SEED,
) -> DatasetPaths:
    """Convenience entry point used by the command line script and tests."""

    root = Path(output_dir)
    generator = SevenDimensionQuestionGenerator(generator_agent, seed=seed, count=count)
    return generator.write_dataset(
        root / "questions",
        count=count,
        ground_truth_path=root / "ground_truth" / f"gt_{generator._file_token(generator_agent)}.jsonl",
    )


# Public aliases: the arena brief and older worktrees use all three names.
HighEntropyQuestionGenerator = SevenDimensionQuestionGenerator
LifeSpectrumQuestionGenerator = SevenDimensionQuestionGenerator
CleaningQuestionGenerator = SevenDimensionQuestionGenerator
QuestionGenerator = SevenDimensionQuestionGenerator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic AIOS cleaning-arena JSONL questions")
    parser.add_argument("--generator-agent", "--generator-id", "--agent-id", dest="generator_agent", required=True)
    parser.add_argument("--count", type=int, default=DEFAULT_QUESTION_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/data_cleaning"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.output_dir
    generator = SevenDimensionQuestionGenerator(args.generator_agent, seed=args.seed, count=args.count)
    paths = generator.write_dataset(
        root / "questions",
        count=args.count,
        ground_truth_path=root / "ground_truth" / f"gt_{generator._file_token(args.generator_agent)}.jsonl",
    )
    print(json.dumps({"questions": str(paths.questions), "ground_truth": str(paths.ground_truth), "count": paths.count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
