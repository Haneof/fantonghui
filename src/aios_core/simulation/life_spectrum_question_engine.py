"""AIOS 3.0 顶级全人生谱系高熵出卷引擎 (Universal Life-Spectrum Question Generator Engine).

实现【七维随机因子拓扑组合引擎】：
- 维度 1：千人千面的佩戴者身份与人生阶段 (D01~D15)
- 维度 2：五大认知域的极限事件谱系 (健康/财务/人际/职业/契约)
- 维度 3：外部物理传感器高熵波形库 (S01~S06)
- 维度 4：声学真实环境拓扑与极端噪声源 (A01~A07)
- 维度 5：语言修辞、真实方言与人际伪装 (川/粤/东北/陕/沪方言 + 吹牛/反讽/嘴硬卒中/暗语/隐喻)
- 维度 6：声纹聚类与混杂说话人拓扑 (3~24 说话人动态消歧)
- 维度 7：真假对抗与事实反转陷阱 (T01~T04 假转账/反悔/撤回/碰瓷 + T00自然态)

严格遵守 CleaningQuestion 规范，生成具有方向性同义词簇 (directional_keywords) 的标答底稿。
严禁模板化、五大认知域均衡覆盖 (各 >= 15%)。
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion,
    DifficultyLevel,
    DirectionalSemanticFact,
)

UTC = timezone.utc


# ==============================================================================
# 维度 1: 千人千面的佩戴者身份与人生阶段 (Demographic Personas)
# ==============================================================================

@dataclass(frozen=True)
class PersonaDefinition:
    tag_id: str
    name: str
    character_name: str
    call_names: List[str]
    age: int
    role: str
    persona_tag: str
    background_traits: List[str]
    typical_apps: List[str]
    user_spk_prefix: str = "spk_user"
    default_dialect: str = "MANDARIN"


PERSONAS: List[PersonaDefinition] = [
    PersonaDefinition(
        tag_id="D01",
        name="17岁高三复读生",
        character_name="林晓峰",
        call_names=["晓峰", "林晓峰", "峰峰"],
        age=17,
        role="高三复读学生",
        persona_tag="D01_高三复读生_17岁_焦虑躯体化与高压陪读",
        background_traits=["重度失眠", "焦虑躯体化", "父母高压陪读", "文具借还", "模考失利", "胃痉挛"],
        typical_apps=["WeChat", "Zhihu", "DingTalk", "XiaoHongShu"],
        default_dialect="SHAANXI"
    ),
    PersonaDefinition(
        tag_id="D02",
        name="24岁大厂互联网外包",
        character_name="周宇",
        call_names=["小周", "宇哥", "周宇"],
        age=24,
        role="IT运维外包工程师",
        persona_tag="D02_大厂外包_24岁_连轴排障与合租隔断漏水",
        background_traits=["连续通宵排查故障", "被主管甩锅", "租房隔断间漏水", "合租纠纷", "转正名额被砍"],
        typical_apps=["Feishu", "WeChat", "Meituan", "BankApp"],
        default_dialect="NORTHEAST"
    ),
    PersonaDefinition(
        tag_id="D03",
        name="28岁孕晚期准妈妈",
        character_name="苏婉",
        call_names=["婉婉", "苏婉", "小苏"],
        age=28,
        role="孕妇/准妈妈",
        persona_tag="D03_孕晚期准妈_28岁_妊娠高血糖与月嫂争执",
        background_traits=["妊娠期高血糖", "胎动监测异常", "婆媳关于月嫂争执", "急症产检排队", "早产先兆宫缩"],
        typical_apps=["BabyTree", "WeChat", "HospitalApp", "JingDong"],
        default_dialect="SHANGHAI"
    ),
    PersonaDefinition(
        tag_id="D04",
        name="32岁长途重卡货运司机",
        character_name="赵铁柱",
        call_names=["铁柱", "赵师傅", "老赵"],
        age=32,
        role="长途半挂车司机",
        persona_tag="D04_重卡司机_32岁_连续疲劳驾驶与路怒扣油",
        background_traits=["连续疲劳驾驶18小时", "高海拔缺氧头痛", "路怒别车摩擦", "油卡盗刷", "高速大堵车"],
        typical_apps=["FreightHelp", "WeChat", "Amap", "TrafficPolice12123"],
        default_dialect="NORTHEAST"
    ),
    PersonaDefinition(
        tag_id="D05",
        name="36岁失业离异二房东",
        character_name="孙立强",
        call_names=["老孙", "孙立强", "孙哥"],
        age=36,
        role="个体租赁经营者",
        persona_tag="D05_失业离异二房东_36岁_房东起诉与胃溃疡出血",
        background_traits=["被大房东起诉腾退", "租客抱团拖欠房租", "孩子抚养费强制执行", "胃溃疡急性出血", "网贷逾期催收"],
        typical_apps=["WeChat", "BankApp", "CourtCivilNotice", "Lianjia"],
        default_dialect="SICHUAN"
    ),
    PersonaDefinition(
        tag_id="D06",
        name="42岁急诊科住院总医师",
        character_name="陈博文",
        call_names=["陈大夫", "陈总", "博文", "陈医生"],
        age=42,
        role="急诊外科住院总",
        persona_tag="D06_急诊住院总_42岁_高暴露连轴与医患推搡",
        background_traits=["连续当班24小时", "抢救室医患纠纷推搡", "针刺暴露高风险", "家属下跪托付", "猝死急诊胸外按压"],
        typical_apps=["HospitalHIS", "WeChat", "MedicalLiterature", "PhoneCall"],
        default_dialect="CANTONESE"
    ),
    PersonaDefinition(
        tag_id="D07",
        name="48岁建筑工地钢筋班包工头",
        character_name="李建国",
        call_names=["老李", "李老板", "建国", "李头儿"],
        age=48,
        role="建筑工地劳务班组长",
        persona_tag="D07_钢筋包工头_48岁_痛风急性发作与讨薪围堵",
        background_traits=["工人高空坠落险情", "民工讨薪围堵堵门", "总包方阴阳合同拒付", "痛风急性发作下不了地", "材料商封门逼债"],
        typical_apps=["WeChat", "BankApp", "Douyin", "GovernmentPetitionApp"],
        default_dialect="SICHUAN"
    ),
    PersonaDefinition(
        tag_id="D08",
        name="53岁更年期民企财务总监",
        character_name="王春兰",
        call_names=["王总", "春兰", "王总监", "王会计"],
        age=53,
        role="民企CFO",
        persona_tag="D08_民企CFO_53岁_假发票稽查与礼金争端",
        background_traits=["大额假发票对账暴雷", "税务稽查突击上门封账", "失眠盗汗潮热", "女儿出嫁高额礼金对质", "股东虚抽资本追偿"],
        typical_apps=["TaxOfficeApp", "WeChat", "EnterpriseWeChat", "BankCorporateApp"],
        default_dialect="SHANGHAI"
    ),
    PersonaDefinition(
        tag_id="D09",
        name="65岁初老退休中学教师",
        character_name="张茂林",
        call_names=["张老师", "老张", "张老"],
        age=65,
        role="退休高级教师",
        persona_tag="D09_初老退休教师_65岁_传销洗脑套牢与轻度脑萎缩",
        background_traits=["轻度脑萎缩记忆倒错", "候鸟式海景房买房被套", "保健品养生会销被洗脑", "老伴白内障急需手术费", "学生借款不还"],
        typical_apps=["WeChat", "Toutiao", "HospitalGuahao", "RetirementPensionApp"],
        default_dialect="SHAANXI"
    ),
    PersonaDefinition(
        tag_id="D10",
        name="78岁独居空巢老人",
        character_name="郑桂芬",
        call_names=["郑奶奶", "郑大妈", "桂芬", "老太太"],
        age=78,
        role="独居高龄老人",
        persona_tag="D10_独居空巢老人_78岁_煤气遗忘与阿尔茨海默走失",
        background_traits=["骨质疏松髋关节骨裂脆弱", "轻度阿尔茨海默黄昏走失", "厨房煤气遗忘未关", "老旧小区水管漏水吵闹", "降压药漏服"],
        typical_apps=["WeChatVoice", "CommunityElderService", "NeighborhoodAlert"],
        default_dialect="SHANGHAI"
    ),
    PersonaDefinition(
        tag_id="D11",
        name="30岁户外越野与极限攀岩者",
        character_name="顾飞",
        call_names=["阿飞", "顾领队", "顾飞", "飞哥"],
        age=30,
        role="极限户外领队",
        persona_tag="D11_极限攀岩者_30岁_失足滑坠脱水与盲区骨折自救",
        background_traits=["失足滑坠崖壁悬挂", "失温脱水体力耗尽", "卫星电话盲区失联", "开放性骨折单手自救固定", "暴风雪迫近"],
        typical_apps=["OutdoorToolbox", "GarminConnect", "TwoStepOutdoor", "EmergencySMS"],
        default_dialect="SICHUAN"
    ),
    PersonaDefinition(
        tag_id="D12",
        name="22岁乡村外卖骑手",
        character_name="马小宝",
        call_names=["小马", "马小宝", "小宝"],
        age=22,
        role="专送外卖骑手",
        persona_tag="D12_乡村外卖骑手_22岁_暴雨超时电瓶被盗与滑囊炎",
        background_traits=["暴雨狂风天连环超时扣款", "配送途中电瓶车电池被盗", "与出餐拖延商家肢体争执", "膝关节滑囊炎积液", "差评威胁"],
        typical_apps=["MeituanRider", "ElemeRider", "WeChat", "Kuaishou"],
        default_dialect="NORTHEAST"
    ),
    PersonaDefinition(
        tag_id="D13",
        name="45岁中式餐饮连锁店主",
        character_name="黄大胜",
        call_names=["黄老板", "老黄", "黄大胜", "黄师傅"],
        age=45,
        role="个体餐饮企业老板",
        persona_tag="D13_餐饮连锁店主_45岁_食安突查与厨师罢工催料款",
        background_traits=["市监局突击食安抽检危机", "后厨主厨集体罢工撂挑子", "生鲜供应商堵门催要货款", "沸腾热油严重烫伤", "顾客讹诈封店"],
        typical_apps=["MeituanMerchant", "WeChat", "SupplyChainApp", "IndustryCommerceApp"],
        default_dialect="CANTONESE"
    ),
    PersonaDefinition(
        tag_id="D14",
        name="38岁海员远洋轮机长",
        character_name="韩海生",
        call_names=["韩轮机长", "韩工", "海生", "老韩"],
        age=38,
        role="集装箱远洋货轮大管轮",
        persona_tag="D14_远洋轮机长_38岁_航行幽闭断网与机舱耳鸣火警",
        background_traits=["远洋航行42天深海漂泊", "高轨卫星断网7天后家信", "主机高分贝剧烈轰鸣耳鸣", "幽闭恐怖焦虑狂躁", "辅锅炉突发火警险情"],
        typical_apps=["MaritimeSatelliteMail", "ShipMonitoringSystem", "WhatsApp", "VoiceMemo"],
        default_dialect="NORTHEAST"
    ),
    PersonaDefinition(
        tag_id="D15",
        name="26岁独立自由插画师",
        character_name="宋思琪",
        call_names=["思琪", "宋老师", "琪琪", "思琪酱"],
        age=26,
        role="自由职业原画师",
        persona_tag="D15_自由插画师_26岁_甲方法务毁约与重度腹膜炎猫咪",
        background_traits=["颈椎C4-C6压迫手部发麻", "头部甲方白嫖改图恶意毁约", "原创画作被某游戏剽窃维权", "爱猫猫传腹病危急需五万", "被房东强退"],
        typical_apps=["WeChat", "Weibo", "Xiaohongshu", "VeterinaryHospitalApp"],
        default_dialect="SHANGHAI"
    )
]


# ==============================================================================
# 维度 2: 五大认知域的极限事件谱系 (Core Event Spectrum)
# ==============================================================================

class CognitiveDomain(StrEnum):
    HEALTH = "dim:health"
    FINANCE = "dim:finance"
    SOCIAL = "dim:social"
    CAREER = "dim:career"
    CONTRACT = "dim:contract"


@dataclass
class EventArchetype:
    event_id: str
    domain: CognitiveDomain
    title: str
    semantic_intent: str
    core_content_template: str
    anchor_entities_templates: List[str]
    directional_keywords: List[str]
    difficulty: DifficultyLevel
    dialogue_prompt_hints: List[str]
    medical_or_legal_terms: List[str]


EVENT_ARCHETYPES: List[EventArchetype] = [
    # ---------------- 域 1: 健康生理与危机域 (dim:health) ----------------
    EventArchetype(
        event_id="EVT_H01",
        domain=CognitiveDomain.HEALTH,
        title="隐匿性下壁心肌梗死先兆",
        semantic_intent="ACUTE_MYOCARDIAL_INFARCTION_PRECURSOR",
        core_content_template="{persona_name}发生隐匿性下壁心肌梗死先兆，胃部绞痛灼热误以为消化不良，伴冷汗淋漓与心率骤降，亟需急救转运",
        anchor_entities_templates=["{persona_name}", "胃部绞痛", "下壁心梗先兆", "冷汗淋漓", "急送医院抢救"],
        directional_keywords=["心肌梗死", "下壁心梗", "心梗先兆", "胃痛误判", "胸骨后冷汗", "急救送医", "突发心血管危机", "急诊转运"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["以为是吃了冷馒头烧胃，实际上胸口像秤砣压住，后背湿透一大片", "快叫120，这不是胃痉挛！"],
        medical_or_legal_terms=["心电图ST段抬高", "肌钙蛋白I", "阿司匹林肠溶片", "硝酸甘油", "心室颤动风险"]
    ),
    EventArchetype(
        event_id="EVT_H02",
        domain=CognitiveDomain.HEALTH,
        title="痛风石破溃继发蜂窝织炎感染",
        semantic_intent="GOUT_TOPI_RUPTURE_INFECTION",
        core_content_template="{persona_name}第一跖趾关节痛风石破溃化脓引发急性蜂窝织炎，患肢灼痛红肿无法触地，伴高热寒战",
        anchor_entities_templates=["{persona_name}", "第一跖趾痛风石", "破溃化脓", "蜂窝织炎", "头孢抗感染"],
        directional_keywords=["痛风破溃", "痛风石感染", "蜂窝织炎", "关节红肿流脓", "抗生素输液", "痛风急性恶化", "下肢无法承重"],
        difficulty=DifficultyLevel.MEDIUM,
        dialogue_prompt_hints=["脚大拇指烂出白色石灰渣子了，周围通红滚烫，碰一下钻心疼", "不能再硬挺了，必须清创引流！"],
        medical_or_legal_terms=["高尿酸血症", "双氯芬酸钠", "秋水仙碱", "清创引流", "白细胞危象"]
    ),
    EventArchetype(
        event_id="EVT_H03",
        domain=CognitiveDomain.HEALTH,
        title="糖尿病酮症酸中毒呼吸烂苹果味",
        semantic_intent="DIABETIC_KETOACIDOSIS_DKA",
        core_content_template="{persona_name}因漏打胰岛素突发糖尿病酮症酸中毒(DKA)，呼吸深快带有烂苹果味，意识嗜睡瞻望",
        anchor_entities_templates=["{persona_name}", "血糖超标", "烂苹果味呼气", "酮症酸中毒", "急诊静滴小剂量胰岛素"],
        directional_keywords=["糖尿病酮症酸中毒", "DKA危象", "烂苹果气味", "严重高血糖", "神志模糊嗜睡", "胰岛素静滴补液", "代谢性酸中毒"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["闻着他嘴里一股烂苹果醋酸味，整个人迷迷糊糊叫不醒", "血糖仪显示高至爆表Hi，赶紧打胰岛素送重症！"],
        medical_or_legal_terms=["血酮体", "二氧化碳结合力", "小剂量胰岛素静脉滴注", "补钾补液", "渗透性利尿"]
    ),
    EventArchetype(
        event_id="EVT_H04",
        domain=CognitiveDomain.HEALTH,
        title="急性中药/抗生素药物过敏性休克",
        semantic_intent="ANAPHYLACTIC_SHOCK_EMERGENCY",
        core_content_template="{persona_name}在私立诊所输注抗生素后发生I型超敏过敏性休克，喉头水肿窒息伴血压骤降至休克压",
        anchor_entities_templates=["{persona_name}", "药物过敏", "喉头水肿窒息", "血压骤降休克", "肾上腺素肌肉注射"],
        directional_keywords=["过敏性休克", "药物剧烈超敏", "喉头水肿", "呼吸骤停窒息", "肾上腺素急救", "血压暴跌", "抢救生命危象"],
        difficulty=DifficultyLevel.ADVERSARIAL,
        dialogue_prompt_hints=["刚打上吊针两分钟，脖子身上全是红风团，喘不上气手脚冰凉！", "护士快拔针！拿1毫克肾上腺素打大腿！"],
        medical_or_legal_terms=["盐酸肾上腺素", "气管插管", "地塞米松", "声门闭塞", "循环衰竭"]
    ),
    EventArchetype(
        event_id="EVT_H05",
        domain=CognitiveDomain.HEALTH,
        title="剧烈脱水劳力性横纹肌溶解综合征",
        semantic_intent="EXERTIONAL_RHABDOMYOLYSIS",
        core_content_template="{persona_name}剧烈运动或超负荷劳作后突发横纹肌溶解，尿液呈深浓茶酱油色，双下肢肌肉肿胀坏死",
        anchor_entities_templates=["{persona_name}", "酱油色浓茶尿", "横纹肌溶解", "肌酸激酶暴增", "急性肾衰竭风险"],
        directional_keywords=["横纹肌溶解", "浓茶酱油尿", "肌红蛋白尿", "肌肉溶解坏死", "急性格力肌溶", "急性肾损伤透析", "碱化尿液补液"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["连尿都尿不出来了，排出来的一口全是酱油一样的黑尿", "肌肉硬得像石头，肌酸激酶好几万，小心肾衰竭！"],
        medical_or_legal_terms=["肌酸激酶CK", "肌红蛋白", "水化碱化", "急性肾小管坏死", "血液透析指征"]
    ),
    EventArchetype(
        event_id="EVT_H06",
        domain=CognitiveDomain.HEALTH,
        title="急性脑卒中中风前兆言语不利",
        semantic_intent="ACUTE_ISCHEMIC_STROKE_TIA",
        core_content_template="{persona_name}突发急性缺血性脑卒中(中风)先兆，单侧肢体麻木无力且言语含糊，本人嘴硬隐瞒但伴随口角歪斜",
        anchor_entities_templates=["{persona_name}", "口角歪斜流涎", "半边肢体瘫软", "中风脑卒中先兆", "静脉溶栓时间窗"],
        directional_keywords=["急性脑卒中", "脑梗死中风", "短暂性脑缺血TIA", "口角歪斜失语", "肢体偏瘫麻木", "溶栓绿色通道", "神经功能缺损"],
        difficulty=DifficultyLevel.ADVERSARIAL,
        dialogue_prompt_hints=["嘴硬嘟囔说没事就是舌头打结，结果水杯从右手直接滑落摔碎，右脸笑不起来", "这是大面积脑中风先兆，4.5小时黄金溶栓时间窗绝不能耽误！"],
        medical_or_legal_terms=["FAST原则", "rt-PA静脉溶栓", "颅脑急诊CT排颅内出血", "巴宾斯基征", "颈动脉狭窄"]
    ),

    # ---------------- 域 2: 财务债务与民商法域 (dim:finance) ----------------
    EventArchetype(
        event_id="EVT_F01",
        domain=CognitiveDomain.FINANCE,
        title="总包方恶意扣押劳务工程款讨薪对质",
        semantic_intent="WAGE_ARREARS_CONTRACT_CONFRONTATION",
        core_content_template="{counterpart_name}作为发包方恶意拖欠{amount}万劳务款，{persona_name}带领班组堵门对质并向住建清欠办投诉",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "{amount}万元劳务款", "住建清欠办", "还款承诺书"],
        directional_keywords=["欠薪讨薪", "劳务纠纷", "拖欠工程款", "住建局投诉", "农民工工资欠条", "对质交涉", "强力追讨款项"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["三十个工人的血汗钱被你们卡了半年，后天不把款打入监管账户，大家直接住建局见！", "白纸黑字盖了章的结算单，你们休想赖账！"],
        medical_or_legal_terms=["《保障农民工工资支付条例》", "工程款清算单", "总包代发专户", "连带清偿责任", "劳动保障监察大队"]
    ),
    EventArchetype(
        event_id="EVT_F02",
        domain=CognitiveDomain.FINANCE,
        title="天使轮对赌失败触发无限连带无限追索",
        semantic_intent="VENTURE_CAPITAL_VAM_REPURCHASE_DEMAND",
        core_content_template="{counterpart_name}投资机构正式送达对赌失败回购通知书，要求{persona_name}承担{amount}万元投资款本息个人无限连带担保责任",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}资本", "对赌失败回购函", "{amount}万元无限连带责任", "司法冻结个人资产"],
        directional_keywords=["投资对赌清算", "股份回购纠纷", "个人无限连带责任", "天使投资索赔", "商业纠纷追偿", "资产保全查封", "破产连带清偿"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["由于今年净利润未达到承诺的1500万，依据补充协议第8条，即刻启动创始团队无限连带连带回购条款", "法院诉前财产保全通知已经寄到你家里了！"],
        medical_or_legal_terms=["估值调整协议VAM", "无限连带担保", "诉前财产保全", "失信被执行人", "破产清算优先受偿权"]
    ),
    EventArchetype(
        event_id="EVT_F03",
        domain=CognitiveDomain.FINANCE,
        title="虚拟币传销杀猪盘崩盘跑路维权",
        semantic_intent="CRYPTO_PONZI_SCHEME_COLLAPSE",
        core_content_template="{counterpart_name}操控的虚拟币质押分红盘彻底崩盘关网跑路，{persona_name}被套牢损失{amount}万元并前往经侦支队报案",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "{amount}万元血汗钱", "质押分红关网跑路", "经侦支队刑事立案"],
        directional_keywords=["传销盘崩盘", "虚拟币杀猪盘", "非吸跑路", "经侦报案追赃", "非法集资诈骗", "崩盘归零血本无归", "投资诈骗维权"],
        difficulty=DifficultyLevel.MEDIUM,
        dialogue_prompt_hints=["APP根本登录不上去显示404，操盘手群全解散了，把我投进去的三十万养老钱卷光了！", "所有受害者带上转账记录，去市公安局经侦大队排队做笔录！"],
        medical_or_legal_terms=["非法吸收公众存款罪", "集资诈骗罪", "涉案虚拟货币去向穿透", "追赃挽损", "刑事附带民事"]
    ),
    EventArchetype(
        event_id="EVT_F04",
        domain=CognitiveDomain.FINANCE,
        title="二手房连环单恶意违约中介吃差价",
        semantic_intent="REAL_ESTATE_CHAIN_BREACH_OF_CONTRACT",
        core_content_template="{counterpart_name}在二手房连环置换交易中恶意毁约拒不配合过户，并与黑中介串通吃差价{amount}万元",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "二手房买卖合同", "{amount}万元违约金", "房产诉讼保全"],
        directional_keywords=["房屋买卖违约", "连环单毁约", "中介吃差价纠纷", "房屋买卖纠纷", "双倍返还定金", "强制作出网签过户", "违约金追索"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["房价涨了二十万你就想反悔毁约？定金我付了网签办了，下周一不上房管局，我法庭告你双倍赔偿！", "黑中介两头吃差价，咱们法庭上见！"],
        medical_or_legal_terms=["定金罚则", "网签撤销权", "实际损失赔偿", "二手房买卖居间合同", "不动产登记中心保全"]
    ),

    # ---------------- 域 3: 家庭情感与人际博弈域 (dim:social) ----------------
    EventArchetype(
        event_id="EVT_S01",
        domain=CognitiveDomain.SOCIAL,
        title="十年抚养之子司法亲子鉴定非亲生宣读",
        semantic_intent="PATERNITY_TEST_NON_BIOLOGICAL_REVELATION",
        core_content_template="司法鉴定所正式出具DNA亲子鉴定报告，确认{persona_name}抚养十年的孩子与其不存在亲子血缘关系，引发抚养费追偿与婚姻破裂",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "孩子血缘关系排除", "司法DNA鉴定文书", "起诉欺诈性抚养赔偿"],
        directional_keywords=["非亲生鉴定", "亲子关系排除", "司法鉴定通报", "抚养权欺诈索赔", "婚姻破裂诉讼", "身世真相爆发", "欺诈性抚养纠纷"],
        difficulty=DifficultyLevel.ADVERSARIAL,
        dialogue_prompt_hints=["报告第4页白纸黑字写着‘排除父子亲缘关系’！整整十年我捧在手心的孩子，你到底跟谁生的？", "你瞒了我整整十年，十年的抚养费、精神抚慰金一分都不能少！"],
        medical_or_legal_terms=["STR位点分型基因检测", "排除相对生物学父子关系", "欺诈性抚养侵权损害赔偿", "精神损害赔偿金", "民法典第一千零九十一条"]
    ),
    EventArchetype(
        event_id="EVT_S02",
        domain=CognitiveDomain.SOCIAL,
        title="父母隐匿胰腺癌晚期病历异地崩溃求医",
        semantic_intent="PARENTAL_CANCER_CONCEALMENT_CRISIS",
        core_content_template="{persona_name}偶然在老家柜底搜出父母瞒报的胰腺癌晚期转移病历，异地痛哭质问并连夜联系三甲医院专家急诊加号",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "胰腺癌晚期多发转移", "病历隐瞒", "连夜急诊特需加号"],
        directional_keywords=["瞒报癌症晚期", "胰腺癌恶性转移", "家属重疾就医", "隐瞒病情对质", "异地崩溃寻医", "肿瘤特需急诊", "重特大疾病家庭危局"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["拿个胃溃疡的药盒瞒了我大半年，CT单子上都写着胰腺占位肝转移了！爸，你为什么不告诉我！", "今晚收拾东西，明天一早跟我去上海肿瘤医院看特需门诊！"],
        medical_or_legal_terms=["胰腺体尾部腺癌", "CA19-9肿瘤标志物", "多发肝转移", "姑息性化疗", "晚期癌痛镇痛治疗"]
    ),
    EventArchetype(
        event_id="EVT_S03",
        domain=CognitiveDomain.SOCIAL,
        title="职场直属主管性骚扰言语胁迫录音取证",
        semantic_intent="WORKPLACE_SEXUAL_HARASSMENT_RECORDING",
        core_content_template="{counterpart_name}在私密商务宴请借考评晋升对{persona_name}实施言语性骚扰与潜规则暗示，佩戴者手环启动隐蔽录音取证",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "绩效考核胁迫潜规则", "手环录音取证", "向集团纪委与妇联控告"],
        directional_keywords=["职场性骚扰", "潜规则胁迫", "言语骚扰录音", "考评威胁", "取证维权举报", "反职场侵害控诉", "固定骚扰证据"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["这次大区经理的位置我给你留着，今晚别回去了，把房卡收下...你也不想年终奖打D吧？", "李总请你自重！你刚才说的每一句话我都已经录下来了！"],
        medical_or_legal_terms=["民法典第一千零一十条性骚扰认定", "职场优势地位胁迫", "电子视听资料证据链", "企业合规调查举报", "名誉权与劳动保护"]
    ),
    EventArchetype(
        event_id="EVT_S04",
        domain=CognitiveDomain.SOCIAL,
        title="创业联合创始人转移核心技术资产另立门户",
        semantic_intent="COFOUNDER_IP_THEFT_BREACH_OF_LOYALTY",
        core_content_template="{counterpart_name}作为联合创始人暗中私设壳公司，转移核心代码库与大客户订单，{persona_name}当面掀桌对质并追责",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "暗设影子外包公司", "转移核心自研代码", "侵犯商业秘密诉讼"],
        directional_keywords=["合伙人背叛背刺", "转移公司资产客户", "另设壳公司倒卖业务", "商业秘密侵权", "股东合伙散伙决裂", "对质交涉维权", "背信损害上市公司利益"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["拿着团队通宵三年的底层架构代码，私底下挂在你小舅子皮包公司名下卖给竞品，你还是不是人！", "下周经侦和知识产权法庭会同时找你，等着赔个倾家荡产吧！"],
        medical_or_legal_terms=["侵犯商业秘密罪", "职务侵占罪", "竞业禁止与忠实勤勉义务", "非关联化资产转移", "股东知情权与代表诉讼"]
    ),

    # ---------------- 域 4: 职业学业与重大转折域 (dim:career) ----------------
    EventArchetype(
        event_id="EVT_C01",
        domain=CognitiveDomain.CAREER,
        title="博士学位论文双盲外审不及格与导师决裂",
        semantic_intent="DISSERTATION_BLIND_REVIEW_REJECTION",
        core_content_template="{persona_name}博士学位论文教育部双盲外审遭给出两个D级不合格，与长期压榨挂名的导师{counterpart_name}爆发剧烈言语冲突与学术决裂",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}教授", "博士盲审两个D延毕", "强行挂名一作", "学术委员会申诉"],
        directional_keywords=["博士盲审挂科", "毕业延期危机", "师生学术决裂", "导师压榨课题", "学术委员会复核", "学位申请受阻", "学术争执冲突"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["五年我给你干了七个横向课题，最后把我核心创新点全逼我送给你关系户，现在盲审大修延毕，你把我的前途全毁了！", "我要去校学术道德委员会提交所有原始实验日志实名举报你！"],
        medical_or_legal_terms=["教育部学位论文抽检", "盲审意见复核申诉", "第一作者知识产权署名争议", "学术不端行为认定", "博士培养年限预警"]
    ),
    EventArchetype(
        event_id="EVT_C02",
        domain=CognitiveDomain.CAREER,
        title="劳动仲裁庭审HR伪造离职考勤当庭戳穿",
        semantic_intent="LABOR_ARBITRATION_FORGED_ATTENDANCE",
        core_content_template="{counterpart_name}公司HR在劳动仲裁庭审出示伪造的考勤旷工记录拒付N+1，{persona_name}当庭出示钉钉原始基站导出数据正面打脸",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}公司HR", "伪造旷工扣发补偿", "劳动人事仲裁委员会", "当庭调取原始证据"],
        directional_keywords=["劳动仲裁对质", "伪造考勤打卡记录", "非法解除劳动合同", "追索违法辞退赔偿金", "克扣经济补偿金", "仲裁庭当面对质", "劳资纠纷胜诉"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["仲裁员同志，被申请人提交的纸质考勤表签字全是我离职后被仿冒的，我这里有服务器后台带时间戳的原始打卡日志！", "恶意伪造证据拒付赔偿，我要求顶格双倍赔偿！"],
        medical_or_legal_terms=["违法解除劳动合同2N赔偿", "举证责任倒置", "民事诉讼法妨害民事诉讼惩戒", "加班费差额补齐", "离职证明扣留损害赔偿"]
    ),
    EventArchetype(
        event_id="EVT_C03",
        domain=CognitiveDomain.CAREER,
        title="竞业限制诉讼索赔两百万与调查取证",
        semantic_intent="NON_COMPETE_LAWSUIT_TWO_MILLION",
        core_content_template="{counterpart_name}前东家提起劳动仲裁与诉讼，以违反竞业协议为由向{persona_name}索赔违约金{amount}万元并指控入职竞对",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}网络", "竞业协议限制赔偿", "{amount}万元高额索赔", "商业间谍取证反驳"],
        directional_keywords=["竞业限制违约纠纷", "索赔天价违约金", "竞业协议起诉", "竞对公司穿透认定", "商业竞争仲裁", "离职竞业限制抗辩", "劳动合同违约诉讼"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["你离职后通过第三方人力换皮去敌对公司做相同模块，竞业补偿金我们月月打卡，现在索赔两百万违约金！", "新公司经营范围和你们完全不同，你们恶意跟踪偷拍侵犯隐私！"],
        medical_or_legal_terms=["竞业限制协议", "实际出资与控制人认定", "违约金畸高调减", "侵犯公民个人信息抗辩", "同业竞争实质审查"]
    ),
    EventArchetype(
        event_id="EVT_C04",
        domain=CognitiveDomain.CAREER,
        title="海关突击查扣核心外贸货柜与信用证承兑",
        semantic_intent="CUSTOMS_SEIZURE_LETTER_OF_CREDIT_CRISIS",
        core_content_template="{persona_name}企业出口的五个高货值集装箱因报关单HS编码争议遭海关扣押，导致不可撤销远期信用证面临{amount}万到期拒付违约",
        anchor_entities_templates=["{persona_name}", "黄埔海关缉私局", "五个货柜查扣滞港", "HS海关编码争议", "{amount}万元信用证违约"],
        directional_keywords=["海关货物查扣", "不可撤销信用证拒付", "外贸订单违约危机", "退运罚款风险", "海关查验滞港", "外贸供应链断裂", "涉嫌违规走私稽查"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["五个柜子在码头被亮红灯全部查扣开箱，海关质疑申报商品归类，后天信用证交单期一过，两百万全完蛋！", "赶紧找报关行出具技术成分分析公函，申请保全放行！"],
        medical_or_legal_terms=["HS编码归类行政争议", "信用证不可撤销交单期限UCP600", "滞港仓储费", "海关行政复议", "货运提单提货权"]
    ),

    # ---------------- 域 5: 生活契约与日常意外域 (dim:contract) ----------------
    EventArchetype(
        event_id="EVT_L01",
        domain=CognitiveDomain.CONTRACT,
        title="高层主排污管老化倒灌浸泡名贵财产索赔",
        semantic_intent="SEWAGE_BACKFLOW_PROPERTY_DAMAGE_CLAIM",
        core_content_template="{persona_name}租住房主下水排污管突发严重反水倒灌，数万元名贵物品与地板全遭粪水浸泡，与物业和楼上多户发生激烈索赔冲突",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}物业", "主下水排污管反水", "财产损失{amount}万元", "起诉全楼业主连带侵权"],
        directional_keywords=["排污管反水倒灌", "房屋财产被泡受损", "物业失职索赔", "全楼业主共同侵权责任", "淹水清点定损", "排污倒灌纠纷", "公用管道破裂维权"],
        difficulty=DifficultyLevel.MEDIUM,
        dialogue_prompt_hints=["进门臭水淹到脚踝，满屋子的原画手稿和名贵乐器全泡烂了！物业三个月不通管子，你们必须全额赔偿！", "楼上几户私自改动下水管道的，一个都跑不了！"],
        medical_or_legal_terms=["民法典公用设施维修义务", "财产损失价格公证", "连带赔偿责任", "不可抗力免责排查", "侵权责任法环境卫生损害"]
    ),
    EventArchetype(
        event_id="EVT_L02",
        domain=CognitiveDomain.CONTRACT,
        title="烈性大型犬外出未牵绳扑倒幼童撕咬调解",
        semantic_intent="OFF_LEASH_DOG_ATTACK_TODDLER_DISPUTE",
        core_content_template="{counterpart_name}饲养的大型罗威纳犬在小区未牵绳扑倒并撕咬幼童，{persona_name}挺身相救与狗主人在派出所发生激烈争执",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}", "大型烈性犬未牵绳", "幼童面部撕咬抓伤", "派出所行政拘留处罚"],
        directional_keywords=["未牵绳恶犬伤人", "扑倒儿童撕咬", "狂犬疫苗注射与急救", "派出所治安调解", "饲养动物损害责任", "烈性犬违规饲养追责", "激烈肢体口角纠纷"],
        difficulty=DifficultyLevel.MEDIUM,
        dialogue_prompt_hints=["你养大型烈性犬出门连个牵引绳嘴套都不带，把邻居家四岁孩子脸都咬破了，还敢嘴硬说狗只是在玩？", "民警同志，坚决不调解！必须行政拘留并且强制没收恶犬！"],
        medical_or_legal_terms=["民法典第一千二百四十七条禁止饲养烈性犬致害无过错责任", "狂犬疫苗及免疫球蛋白接种", "治安管理处罚法第七十五条", "人身损害赔偿标准", "面部瘢痕伤残鉴定"]
    ),
    EventArchetype(
        event_id="EVT_L03",
        domain=CognitiveDomain.CONTRACT,
        title="二手事故泡水车第三方检测实锤退一赔三",
        semantic_intent="FLOODED_VEHICLE_FRAUD_CLAIM_THREE_TIMES",
        core_content_template="{persona_name}购买的二手SUV经中国检验认证集团复核确认为重大泡水全损事故车，{counterpart_name}车商涉嫌欺诈面临退一赔三诉讼",
        anchor_entities_templates=["{persona_name}", "{counterpart_name}二手车行", "全损重大泡水事故车", "消法退一赔三诉讼", "中检集团司法鉴定"],
        directional_keywords=["二手车隐瞒泡水事故", "全损车欺诈销售", "消费者权益保护法退一赔三", "第三方检测报告实锤", "车商欺诈维权", "二手车维权退车", "涉嫌消费欺诈诉讼"],
        difficulty=DifficultyLevel.HARD,
        dialogue_prompt_hints=["卖车时拍胸脯保证原版原漆零出险，今天拆开底盘地毯里全是泥沙锈迹，保险公司查出去年特大暴雨全损赔付！", "合同写得明明白白非泡水车，退一赔三，今天不把车款和赔偿打过来，直接封你店！"],
        medical_or_legal_terms=["消费者权益保护法第五十五条退一赔三", "严重水泡车认定标准GB/T 30323", "二手车鉴定评估技术规范", "民事欺诈构成要件", "车辆行驶电脑ECU浸水记录"]
    ),
    EventArchetype(
        event_id="EVT_L04",
        domain=CognitiveDomain.CONTRACT,
        title="境外偏远公路自驾严重车祸与语言不通救援",
        semantic_intent="OVERSEAS_ROAD_ACCIDENT_EMERGENCY_RESCUE",
        core_content_template="{persona_name}在境外偏远盘山公路遭遇严重侧翻车祸车身变形卡压，面对当地警方语言不通，通过手环全球紧急卫星短报文求援",
        anchor_entities_templates=["{persona_name}", "境外盘山公路侧翻", "车体变形双腿卡压", "中国驻当地使领馆", "全球应急救援SOS"],
        directional_keywords=["境外自驾严重车祸", "车辆翻滚卡压受困", "卫星短报文SOS求援", "领事保护热线12308", "跨国道路交通事故", "急重症紧急救援", "破拆逃生救治"],
        difficulty=DifficultyLevel.ADVERSARIAL,
        dialogue_prompt_hints=["车子翻下路基滚了两圈，驾驶室严重变形双腿被卡住，当地警察在外面说话听不懂，手环赶紧呼叫领馆12308！", "失血发冷，发卫星经纬度坐标请求重型液压破拆！"],
        medical_or_legal_terms=["双侧下肢骨折失血性休克", "外交部全球领事保护应急热线12308", "国际SOS空中救援直升机", "液压剪切钳破拆", "跨国交通事故责任认定公证"]
    )
]


# ==============================================================================
# 维度 3: 外部物理传感器高熵波形库 (Sensor Waveform Modalities S01~S06)
# ==============================================================================

@dataclass
class SensorWaveformProfile:
    code: str
    name: str
    generate_fn_name: str
    description: str


def generate_sensor_s01_high_g() -> Dict[str, Any]:
    """S01: 高 G 值剧烈冲击: 15G~35G 撞击后长时间静止 (严重坠落、翻车)。"""
    peak = round(random.uniform(15.2, 34.8), 2)
    # 前期正常, 骤升冲击, 随后长期静止 (近 1.0G 无震动)
    g_wave = [1.02, 1.15, round(random.uniform(3.5, 6.0), 2), peak, 1.80, 0.98, 1.00, 1.00, 1.01]
    return {
        "sensor_profile": "S01_HIGH_G_IMPACT_STILLNESS",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(128, 165),
        "pvc_burst_count": random.randint(1, 3),
        "baro_hpa": round(random.uniform(995.0, 1018.0), 1),
        "motion_state": "PROLONGED_MOTIONLESS",
        "accel_variance": 0.002,
        "impact_peak_g": peak
    }


def generate_sensor_s02_false_impact() -> Dict[str, Any]:
    """S02: 虚假冲击对冲: 手环磕碰、大力鼓掌、羽毛球扣杀 (单峰高G伴剧烈连续挥拍运动)。"""
    peak = round(random.uniform(9.0, 16.5), 2)
    # 冲击后紧随大幅度周期震荡
    g_wave = [peak, 4.2, 3.8, 4.5, 3.2, 2.9, 3.6, 2.8]
    return {
        "sensor_profile": "S02_FALSE_IMPACT_ACTIVE_MOVEMENT",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(130, 155),
        "pvc_burst_count": 0,
        "baro_hpa": round(random.uniform(1005.0, 1020.0), 1),
        "motion_state": "CONTINUOUS_HIGH_FREQUENCY_ARM_SWING",
        "accel_variance": 2.45,
        "impact_peak_g": peak
    }


def generate_sensor_s03_malignant_arrhythmia() -> Dict[str, Any]:
    """S03: 心律失常恶性事件: 夜间静止状态心率突然飙升至 190~220bpm 伴频发室性早搏。"""
    g_wave = [0.99, 1.01, 1.00, 0.98, 1.01, 0.99, 1.00]
    return {
        "sensor_profile": "S03_NOCTURNAL_MALIGNANT_ARRHYTHMIA",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(188, 225),
        "pvc_burst_count": random.randint(8, 26),
        "baro_hpa": round(random.uniform(1010.0, 1016.0), 1),
        "motion_state": "NOCTURNAL_REST_CRITICAL_CARDIO",
        "accel_variance": 0.004,
        "ecg_r_peak_interval_ms": 280
    }


def generate_sensor_s04_sinus_arrest() -> Dict[str, Any]:
    """S04: 缓慢性心脏停搏: 窦性停搏 3.8 秒，心率骤降至 32bpm 伴随身体失衡下沉失速。"""
    # 先失速降为 0.2G，后跌倒触地
    g_wave = [1.01, 0.22, 0.18, 2.85, 1.05, 1.00, 1.00]
    return {
        "sensor_profile": "S04_SINUS_ARREST_SYNCOPE",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(28, 36),
        "pvc_burst_count": 0,
        "sinus_pause_seconds": 3.85,
        "baro_hpa": round(random.uniform(1008.0, 1015.0), 1),
        "motion_state": "SUDDEN_POSTURAL_COLLAPSE",
        "accel_variance": 0.08
    }


def generate_sensor_s05_baro_plunge() -> Dict[str, Any]:
    """S05: 气压与海拔骤变: 短时间内气压骤降 20hPa，伴随大风与体温体感突降。"""
    g_wave = [1.12, 1.25, 1.18, 1.30, 1.22, 1.15]
    return {
        "sensor_profile": "S05_BAROMETRIC_PRESSURE_PLUNGE",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(95, 125),
        "pvc_burst_count": 0,
        "baro_hpa": round(random.uniform(970.0, 992.0), 1),
        "delta_baro_hpa_last_hour": -22.4,
        "motion_state": "RAPID_EVACUATION_WALKING",
        "accel_variance": 0.35
    }


def generate_sensor_s06_normal_running() -> Dict[str, Any]:
    """S06: 跑步运动基线正常偏移: 配速 4分30秒 剧烈摆臂，心率 165bpm 正弦波动 (非危象)。"""
    # 规律正弦震荡
    g_wave = [1.85, 0.45, 1.92, 0.40, 1.88, 0.48, 1.82]
    return {
        "sensor_profile": "S06_STEADY_RUNNING_BASELINE_SHIFT",
        "raw_imu_g_force": g_wave,
        "heart_rate_bpm": random.randint(158, 168),
        "pvc_burst_count": 0,
        "cadence_spm": 182,
        "baro_hpa": round(random.uniform(1012.0, 1018.0), 1),
        "motion_state": "STEADY_TEMPO_RUNNING",
        "accel_variance": 1.88
    }


SENSOR_GENERATORS = {
    "S01": generate_sensor_s01_high_g,
    "S02": generate_sensor_s02_false_impact,
    "S03": generate_sensor_s03_malignant_arrhythmia,
    "S04": generate_sensor_s04_sinus_arrest,
    "S05": generate_sensor_s05_baro_plunge,
    "S06": generate_sensor_s06_normal_running
}


# ==============================================================================
# 维度 4: 声学真实环境拓扑与极端噪声源 (Ambient Acoustic Topology A01~A07)
# ==============================================================================

@dataclass(frozen=True)
class AcousticTopology:
    code: str
    scene_name: str
    noise_db_range: Tuple[float, float]
    background_sounds: List[str]
    junk_peddler_snippets: List[str]


ACOUSTIC_TOPOLOGIES: List[AcousticTopology] = [
    AcousticTopology(
        code="A01",
        scene_name="早晚高峰地铁换乘通道",
        noise_db_range=(82.0, 88.5),
        background_sounds=["车轮轨道啸叫", "换乘广播反复循环", "密集踏步声", "安全门警报蜂鸣"],
        junk_peddler_snippets=[
            "十号线即将进站，请在安全黄线内排队候车！",
            "烤肠淀粉肠三块钱一根五块钱两根！",
            "扫码免费领取矿泉水一瓶！",
            "前面别挤啊，脚都被踩扁了！"
        ]
    ),
    AcousticTopology(
        code="A02",
        scene_name="露天海鲜农贸市场",
        noise_db_range=(75.0, 82.0),
        background_sounds=["剁骨刀重击砧板沉闷撞击", "塑料袋撕扯摩擦", "讨价还价方言对吼", "打氧机水泡破裂"],
        junk_peddler_snippets=[
            "大连活鲍鱼十块钱四个现杀现开！",
            "梭子蟹最后两斤亏本大甩卖了！",
            "老板葱给你塞塑料袋里了，慢走啊！",
            "借过借过，冰块水箱别碰翻了！"
        ]
    ),
    AcousticTopology(
        code="A03",
        scene_name="冲压车间与机加工厂房",
        noise_db_range=(88.0, 95.0),
        background_sounds=["800吨冲床高频泄气冲击", "数控车床切削金属刺耳高音", "行车吊臂行进电铃", "气管漏气呲呲声"],
        junk_peddler_snippets=[
            "二号机床下模具卡料了，拉闸断电！",
            "老张把你安全帽帽带系紧，巡检员过来了！",
            "天车起吊，下方人员立刻避让！",
            "这批螺栓公差超了0.2丝，重新校表！"
        ]
    ),
    AcousticTopology(
        code="A04",
        scene_name="综合三甲医院急诊分诊台",
        noise_db_range=(63.0, 72.0),
        background_sounds=["多参数心电监护仪规律哔哔报警", "急救车警报由远及近穿透", "家属哭号推搡喧闹", "护士叫号广播"],
        junk_peddler_snippets=[
            "请急诊外科0142号到第三诊室就诊！",
            "家属先去窗口把CT费交了才能推机器！",
            "别在分诊台挡着，救护车推车进来了让开！",
            "护士站有热水，一次性纸杯在饮水机旁边。"
        ]
    ),
    AcousticTopology(
        code="A05",
        scene_name="深夜高速长途大巴车厢",
        noise_db_range=(48.0, 56.0),
        background_sounds=["底盘柴油机低频共振嗡鸣", "乘客此起彼伏呼噜鼾声", "短视频外放魔性笑声混响", "减速带沉闷顿挫"],
        junk_peddler_snippets=[
            "【短视频配音】：注意看，眼前这个男人叫大壮...",
            "前排师傅麻烦把空调调大点，后排太闷了。",
            "呼噜——呼噜——（沉重磨牙鼾声）",
            "还有两个小时到服务区，要上厕所的抓紧。"
        ]
    ),
    AcousticTopology(
        code="A06",
        scene_name="婚庆宴席大厅",
        noise_db_range=(78.0, 86.0),
        background_sounds=["司仪无线麦克风啸叫混响", "敬酒猜拳推杯换盏高亢喧哗", "熊孩子推翻碗盘破碎", "开场鼓点震耳欲聋"],
        junk_peddler_snippets=[
            "各位亲朋好友，让我们共同举杯祝新郎新娘百年好合！",
            "哥俩好啊五魁首啊六六六！喝！这杯必须干了！",
            "哎呀谁家孩子把可乐全泼地毯上了！",
            "服务员加一套碗筷，再上一壶热茶！"
        ]
    ),
    AcousticTopology(
        code="A07",
        scene_name="暴风雨夜户外露营地",
        noise_db_range=(68.0, 76.0),
        background_sounds=["暴雨密砸帐篷外帐尼龙撕裂声", "大风拉扯风绳剧烈颤音啸叫", "远近连续闷雷低频翻滚", "暴涨溪水湍流撞击"],
        junk_peddler_snippets=[
            "（呼啦啦风声）风绳要被吹脱钩了，再打两根地钉！",
            "把背包全部用防雨罩套好挪到内帐中间！",
            "（远方闷雷巨响轰隆隆隆）",
            "水快漫过地席了，准备往高处撤！"
        ]
    )
]


# ==============================================================================
# 维度 5: 语言修辞、真实方言与人际伪装 (Linguistic Complexity)
# ==============================================================================

DIALECT_EXPRESSIONS: Dict[str, Dict[str, str]] = {
    "SICHUAN": {
        "disaster": "硬是背时，屋头遭大难了",
        "confront": "你莫在这里跟我装神弄鬼，那笔钱硬是遭卷跑了",
        "pain": "痛得老子心慌气短，脚杆直打摆子",
        "threat": "老子直接去建委堵你们门，一分钱都少不得"
    },
    "NORTHEAST": {
        "disaster": "这回可真是拉了跨了，彻底炸窝了",
        "confront": "别搁这儿跟我扯犊子，下礼拜三前把那笔料钱结了，不然厂子给你扬了",
        "pain": "嘶哈...疼得脑瓜仁子直突突，起都起不来",
        "threat": "痛快点麻溜转账，差一分钱咱们法院见！"
    },
    "CANTONESE": {
        "disaster": "阿叔今次真系大镬，顶唔住喇",
        "confront": "咪同我讲咁多废话，听朝九点律所签纸，一毫子都唔准少",
        "pain": "心口翳住翳住好似俾旧石压住，行两步都喘晒气",
        "threat": "再唔还钱直接报警拉你，咪以为有得走鸡！"
    },
    "SHAANXI": {
        "disaster": "天塌咧，这事教人咋弄哩",
        "confront": "把屋里那份协议拿出来，甭跟额装糊涂！",
        "pain": "额这腰跟断了一样，疼得额汗水直流",
        "threat": "额去劳动监察大队告你，甭想欺负老实人！"
    },
    "SHANGHAI": {
        "disaster": "真是触霉头，摊上这种坍台事情",
        "confront": "侬不要面孔，白纸黑字写清爽额，侬凭啥翻毛腔？",
        "pain": "难过得要死，胸口闷牢像透不过气体一样",
        "threat": "我叫律师直接发律师函告侬，侬等着吃官司好了！"
    }
}

PRAGMATIC_TRAP_TYPES = [
    "NONE",
    "DRUNK_BLUSTER",      # 酒后吹牛: 不构成真实事实
    "SARCASTIC_IRONY",   # 反讽正话反说: 表面夸守信实为违约纠纷
    "BRAVE_DENIAL",      # 重疾嘴硬: 掩盖脑中风/危象，模型必须一票否决
    "COVERT_JARGON",     # 暗语隐匿: 行话密谋
    "SUICIDE_METAPHOR"   # 自绝隐喻: 绝望极端心理危机
]


# ==============================================================================
# 维度 6: 声纹聚类与混杂说话人拓扑 (Voiceprint Dynamics)
# ==============================================================================

def build_speaker_cluster(persona: PersonaDefinition, num_speakers: int = 4) -> Dict[str, Any]:
    """构建包含 3~24 人的声纹聚类图谱与说话人字典。"""
    user_id = persona.user_spk_prefix
    speaker_list = [user_id]
    
    candidate_roles = [
        "spk_creditor_zhang", "spk_boss_liu", "spk_doctor_chen", "spk_lawyer_wang",
        "spk_partner_zhao", "spk_relative_aunt", "spk_police_officer", "spk_nurse_station",
        "spk_neighbor_elder", "spk_customer_vip", "spk_broker_fang", "spk_peddler_01",
        "spk_passerby_a", "spk_passerby_b", "spk_subway_staff", "spk_driver_master"
    ]
    random.shuffle(candidate_roles)
    needed = min(num_speakers - 1, len(candidate_roles))
    speaker_list.extend(candidate_roles[:needed])
    
    return {
        "user_speaker_id": user_id,
        "detected_speakers": speaker_list,
        "total_active_clusters": len(speaker_list),
        "overlapping_ratio": round(random.uniform(0.12, 0.45), 2),
        "snr_db": round(random.uniform(6.5, 18.0), 1)
    }


# ==============================================================================
# 维度 7: 真假对抗与事实反转陷阱 (Adversarial Traps T01~T04)
# ==============================================================================

@dataclass
class AdversarialTrapBlueprint:
    trap_code: str
    trap_name: str
    description: str


TRAP_BLUEPRINTS = {
    "T00": AdversarialTrapBlueprint("T00", "NATURAL_FACT", "自然真实态，无事实反转"),
    "T01": AdversarialTrapBlueprint("T01", "FAKE_TRANSFER_REVERSAL", "微信虚假转账截图 vs 银行APP转账失败冲正"),
    "T02": AdversarialTrapBlueprint("T02", "VERBAL_PROMISE_THEN_RENEGE", "语音电话满口答应 vs 两小时后短信反悔耍赖"),
    "T03": AdversarialTrapBlueprint("T03", "GROUP_CHAT_RETRACTION", "群聊许诺发红包/加钱补贴，2分钟内撤回并私聊发手滑发错"),
    "T04": AdversarialTrapBlueprint("T04", "STAGED_FALL_EXTORTION", "IMU波形极度平缓躺地碰瓷 vs MIC录音撕心裂肺讹诈索赔"),
    "T_HEALTH_DENIAL": AdversarialTrapBlueprint("T_HEALTH_DENIAL", "BRAVE_DENIAL_VS_CARDIO_STROKE", "当事人主观嘴硬否认危象 vs 传感器与客观体征实锤急性心梗脑卒中")
}


# ==============================================================================
# 核心出卷引擎 (SevenDimensionalQuestionEngine)
# ==============================================================================

class SevenDimensionalQuestionEngine:
    """七维随机因子拓扑组合生活流高熵出卷引擎。"""

    def __init__(self, generator_id: str = "agent-01", seed: Optional[int] = None):
        self.generator_id = generator_id
        if seed is not None:
            random.seed(seed)
        self.personas = PERSONAS
        self.events = EVENT_ARCHETYPES
        self.topologies = ACOUSTIC_TOPOLOGIES

    def _pick_counterpart_name(self) -> str:
        names = ["老张", "老周", "刘总", "赵会计", "陈主任", "王经理", "孙老板", "钱大姐", "徐警官", "朱科长"]
        return random.choice(names)

    def generate_single_question(
        self,
        question_idx: int,
        forced_domain: Optional[CognitiveDomain] = None,
        forced_persona_id: Optional[str] = None,
        difficulty_override: Optional[DifficultyLevel] = None
    ) -> CleaningQuestion:
        """从 7 个维度各抽取一个因子，笛卡尔积深度融合，生成单道高熵考卷。"""
        # --- 维 1: 选取佩戴者身份 ---
        if forced_persona_id:
            persona = next((p for p in self.personas if p.tag_id == forced_persona_id), random.choice(self.personas))
        else:
            persona = random.choice(self.personas)

        # --- 维 2: 选取极限事件 (支持五大认知域均衡分配) ---
        if forced_domain:
            candidate_events = [e for e in self.events if e.domain == forced_domain]
        else:
            candidate_events = self.events
        event = random.choice(candidate_events)

        # --- 维 3: 选取外部物理传感器波形 ---
        # 如果是健康急症/跌倒，高概率选取 S01/S03/S04；否则随机
        if event.domain == CognitiveDomain.HEALTH:
            if "心" in event.title:
                s_code = random.choice(["S01", "S03", "S04"])
            elif "晕" in event.title or "休克" in event.title:
                s_code = random.choice(["S01", "S04"])
            else:
                s_code = random.choice(["S01", "S03", "S05", "S02"])
        else:
            s_code = random.choice(["S01", "S02", "S05", "S06"])
        sensor_data = SENSOR_GENERATORS[s_code]()

        # --- 维 4: 选取声学环境拓扑 ---
        acoustic = random.choice(self.topologies)
        ambient_noise_db = round(random.uniform(*acoustic.noise_db_range), 1)

        # --- 维 5: 选取方言俚语与修辞陷阱 ---
        dialect_choice = random.choice(list(DIALECT_EXPRESSIONS.keys()))
        dialect_dict = DIALECT_EXPRESSIONS[dialect_choice]
        pragmatic_trap = random.choice(PRAGMATIC_TRAP_TYPES)

        # --- 维 6: 组装 3~24 说话人声纹聚类 ---
        num_speakers = random.randint(3, 14)
        voiceprint = build_speaker_cluster(persona, num_speakers=num_speakers)

        # --- 维 7: 真假对抗与事实反转陷阱 (深度契合认知域) ---
        # 30% 概率触发域专属真假对抗陷阱，70% 触发自然态真实事件
        roll_trap = random.random()
        if roll_trap < 0.35:
            if event.domain == CognitiveDomain.HEALTH:
                trap_code = "T_HEALTH_DENIAL"
            elif event.domain == CognitiveDomain.FINANCE:
                trap_code = "T01"
            elif event.domain == CognitiveDomain.SOCIAL:
                trap_code = "T02"
            elif event.domain == CognitiveDomain.CAREER:
                trap_code = "T03"
            else:  # CognitiveDomain.CONTRACT
                trap_code = "T04"
        else:
            trap_code = "T00"

        trap_info = TRAP_BLUEPRINTS.get(trap_code, TRAP_BLUEPRINTS["T00"])

        # 难度设定
        diff = difficulty_override or event.difficulty
        if trap_code in ("T01", "T02", "T03", "T04", "T_HEALTH_DENIAL"):
            diff = DifficultyLevel.ADVERSARIAL

        # 构造当事人名字与金额
        counterpart = self._pick_counterpart_name()
        amount = random.choice([5, 10, 20, 35, 50, 80, 150, 200])
        dt_base = datetime(2026, 9, 16, random.randint(7, 22), random.randint(0, 59), random.randint(0, 59), tzinfo=UTC)

        # ----------------- 生成多模态数据流 -----------------
        mic_stream: List[Dict[str, Any]] = []
        app_message_stream: List[Dict[str, Any]] = []
        user_dialogue_stream: List[Dict[str, Any]] = []
        ground_truth_junk_ids: List[str] = []
        ground_truth_facts: List[DirectionalSemanticFact] = []

        # 1. 注入环境噪音切片 (铁律四必须物理删除的 JUNK)
        junk_mic_text = random.choice(acoustic.junk_peddler_snippets)
        mic_stream.append({
            "snippet_id": f"mic_junk_{question_idx:05d}_01",
            "speaker_id": "spk_peddler_or_pa",
            "ambient_noise_db": ambient_noise_db,
            "text": junk_mic_text,
            "scene_topology": acoustic.scene_name,
            "is_junk": True
        })
        ground_truth_junk_ids.append(f"mic_junk_{question_idx:05d}_01")

        # 2. 注入垃圾 APP 消息 (推销、砍一刀、垃圾验证码等 JUNK)
        junk_app_senders = ["拼多多福利群", "特惠贷款中心", "淘金币助手", "垃圾验证码通知", "物业便民通知"]
        junk_app_contents = [
            "【仅差0.01元】老友求助力！帮我点一下即可提现200元大红包！",
            "【信用预授信】您已获得最高300,000元应急周转备用金，今日提现免息...",
            "【验证码】您正在登录某某同城交友，验证码为849102，切勿泄露给他人。",
            "关于本周三地下车库消火栓打压测试的温馨提示，请勿泊车于消防通道。"
        ]
        app_message_stream.append({
            "msg_id": f"msg_junk_{question_idx:05d}_01",
            "app": random.choice(persona.typical_apps),
            "sender": random.choice(junk_app_senders),
            "content": random.choice(junk_app_contents),
            "is_junk": True
        })
        ground_truth_junk_ids.append(f"msg_junk_{question_idx:05d}_01")

        # 选取自然的佩戴者称呼
        call_name = random.choice(persona.call_names)
        persona_anchor = f"{persona.character_name}(佩戴者)"
        persona_display = f"{persona.character_name}（{persona.name}）"

        # 3. 核心对抗逻辑与真实事件生成
        core_desc = event.core_content_template.format(
            persona_name=persona_display,
            counterpart_name=counterpart,
            amount=amount
        )
        anchors = [a.format(persona_name=persona_anchor, counterpart_name=counterpart, amount=amount) for a in event.anchor_entities_templates]

        # 考虑方言修辞融合
        dialogue_dialect_hint = dialect_dict["confront"] if "欠" in event.title or "违约" in event.title else dialect_dict["pain"]

        # --- 维 5: 处理修辞陷阱与语言复杂度 ---
        if pragmatic_trap == "DRUNK_BLUSTER":
            # 酒后狂悖吹牛 -> 放入原话流但标为 JUNK，不产生事实！
            user_dialogue_stream.append({
                "utterance_id": f"ut_bluster_{question_idx:05d}",
                "raw_speech": f"喝！倒满！明天老子去香港把那栋维港大楼全买下来给兄弟们一人分一层！老子账上有的是几百亿！",
                "context_scene": "酒桌深夜醉酒发泄",
                "emotional_tone": "BOASTFUL_DRUNK",
                "is_junk": True
            })
            ground_truth_junk_ids.append(f"ut_bluster_{question_idx:05d}")

        elif pragmatic_trap == "SARCASTIC_IRONY":
            # 反讽正话反说 -> 表面夸守信，实为违约
            mic_stream.append({
                "snippet_id": f"mic_irony_{question_idx:05d}",
                "speaker_id": counterpart,
                "ambient_noise_db": ambient_noise_db - 3.0,
                "text": f"行啊{call_name}，你可真守信用，说好今天结清{amount}万，连人影都见不着，手机还把我拉黑！",
                "is_junk": False
            })

        elif pragmatic_trap == "BRAVE_DENIAL":
            # 重疾嘴硬 -> 必须被大模型识破并一票否决其乐观说辞
            user_dialogue_stream.append({
                "utterance_id": f"ut_brave_{question_idx:05d}",
                "raw_speech": f"我没事别大惊小怪叫什么120...我就是眼前发黑...舌头有点发麻说话不利索...歇两分钟就好...",
                "context_scene": "手环佩戴者突发中风先兆但极度抗拒送医",
                "emotional_tone": "BRAVE_CONCEALMENT",
                "is_junk": False
            })

        elif pragmatic_trap == "COVERT_JARGON":
            # 暗语行话隐匿 -> 隐蔽保密约定
            mic_stream.append({
                "snippet_id": f"mic_jargon_{question_idx:05d}",
                "speaker_id": counterpart,
                "ambient_noise_db": ambient_noise_db - 1.0,
                "text": f"老地方老陈皮拿三份，尾款老规矩走不记名卡，绝不能走公账。",
                "is_junk": False
            })

        elif pragmatic_trap == "SUICIDE_METAPHOR":
            # 自绝隐喻 -> 重度绝望心理危机
            user_dialogue_stream.append({
                "utterance_id": f"ut_crisis_{question_idx:05d}",
                "raw_speech": f"安眠药已经攒够整整一瓶了，今晚终于可以不用醒过来了...",
                "context_scene": "深夜独自卧室绝望自语",
                "emotional_tone": "CRITICAL_DESPAIR",
                "is_junk": False
            })

        # --- 维 7: 执行对抗陷阱与事实生成 (确保每道题均生成具有方向性同义词簇的事实) ---
        if trap_code == "T_HEALTH_DENIAL":
            # 嘴硬否认危象 vs 客观体征实锤
            sensor_data = SENSOR_GENERATORS["S03"]()  # 恶性心律失常
            user_dialogue_stream.append({
                "utterance_id": f"ut_adv_{question_idx:05d}_denial",
                "raw_speech": f"我真没事别打120大惊小怪...就是早晨吃了凉油条胃有点胀...舌头稍微有点麻...歇会儿就好...",
                "context_scene": f"{persona_display}突发严重下壁心梗伴脑缺血但主观坚决否认就医",
                "emotional_tone": "STUBBORN_BRAVE_DENIAL",
                "is_junk": False
            })
            fact_desc = f"{persona_display}突发隐匿性心脑血管急性危象（静止心率狂飙至{sensor_data['heart_rate_bpm']}bpm伴室性早搏与言语不利），佩戴者主观嘴硬否认就医，大模型必须一票否决其乐观说辞紧急报警"
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id="dim:health",
                semantic_intent="ACUTE_CRITICAL_DENIAL_OVERRIDE",
                anchor_entities=[persona_anchor, "急性心脑血管危象", "频发室性早搏", "一票否决乐观说辞", "紧急呼叫120送医"],
                directional_keywords=["急性心梗脑卒中危象", "突发恶性心律失常", "否决病患主观嘴硬", "紧急送医抢救", "生命体征危急", "急救绿色通道", "心血管危象介入"],
                core_content=fact_desc,
                source_ref_id=f"ut_adv_{question_idx:05d}_denial",
                confidence=1.0
            ))

        elif trap_code == "T01":
            # T01: 微信发了转账截图，但银行 APP 随后弹出转账失败
            app_message_stream.append({
                "msg_id": f"msg_adv_{question_idx:05d}_01",
                "app": "WeChat",
                "sender": counterpart,
                "content": f"【图片: 银行转账电子回执单 已向您尾号3341成功汇出人民币 {amount}0,000.00 元】",
                "is_junk": False
            })
            app_message_stream.append({
                "msg_id": f"msg_adv_{question_idx:05d}_02",
                "app": "BankApp",
                "sender": "工商银行",
                "content": f"【转账冲正失败通知】对方账户发起的人民币 {amount}0,000.00 元转账已被退回，原因：对方账户处于涉案司法冻结状态。",
                "is_junk": False
            })
            fact_desc = f"{counterpart}向{persona_anchor}发送转账{amount}万元截图，但实际被银行APP拦截冲正失败，转账未完成并涉及账户涉案异常"
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id=event.domain.value,
                semantic_intent="TRANSFER_FAILED_ADVERSARIAL_TRAP",
                anchor_entities=[persona_anchor, counterpart, f"{amount}万元", "转账失败冲正", "账户异常"],
                directional_keywords=["转账失败", "虚假转账", "汇款退回", "转账未成功", "款项冲正", "账户异常拦截", "欠款未清"],
                core_content=fact_desc,
                source_ref_id=f"msg_adv_{question_idx:05d}_02",
                confidence=1.0
            ))

        elif trap_code == "T02":
            # T02: 先承诺后反悔
            mic_stream.append({
                "snippet_id": f"mic_adv_{question_idx:05d}_01",
                "speaker_id": counterpart,
                "ambient_noise_db": ambient_noise_db - 2.0,
                "text": f"行行行算我怕了你，明天上午九点准时去民政局协议离婚签字，财产按你说的办！",
                "is_junk": False
            })
            app_message_stream.append({
                "msg_id": f"msg_adv_{question_idx:05d}_03",
                "app": "SMS",
                "sender": counterpart,
                "content": f"刚才是敷衍你的，想协议离婚门都没有，房子和抚养权我全要，耗死你！",
                "is_junk": False
            })
            fact_desc = f"{counterpart}口头答应协议签署但两小时后短信明确反悔拒绝履约并威胁耗死佩戴者"
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id=event.domain.value,
                semantic_intent="PROMISE_THEN_RENEGE_DISPUTE",
                anchor_entities=[persona_anchor, counterpart, "协议签字反悔", "短信拒绝履行", "双方彻底破裂"],
                directional_keywords=["反悔毁约", "出尔反尔", "拒绝协议", "谈判破裂", "耍赖违约", "恶性争端升级"],
                core_content=fact_desc,
                source_ref_id=f"msg_adv_{question_idx:05d}_03",
                confidence=1.0
            ))

        elif trap_code == "T03":
            # T03: 群聊许诺撤回并狡辩手滑
            app_message_stream.append({
                "msg_id": f"msg_adv_{question_idx:05d}_04",
                "app": "WeChatGroup",
                "sender": counterpart,
                "content": f"（该消息在发送1分20秒后被发送者撤回）",
                "is_junk": True
            })
            ground_truth_junk_ids.append(f"msg_adv_{question_idx:05d}_04")
            app_message_stream.append({
                "msg_id": f"msg_adv_{question_idx:05d}_05",
                "app": "WeChat",
                "sender": counterpart,
                "content": f"刚才在群里发的消息我撤回了，喝高了手滑发错群，你们班组的赶工补贴还是按原合同扣罚，一分不补！",
                "is_junk": False
            })
            fact_desc = f"{counterpart}在群聊许诺补贴后迅速撤回，私聊明确表示手滑发错并维持原合同扣罚"
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id=event.domain.value,
                semantic_intent="RETRACTED_PROMISE_MAINTAIN_PENALTY",
                anchor_entities=[persona_anchor, counterpart, "消息撤回", "手滑发错狡辩", "拒绝追加补贴"],
                directional_keywords=["撤回承诺", "拒不认可补贴", "维持扣款", "私下否认", "劳务补偿争议"],
                core_content=fact_desc,
                source_ref_id=f"msg_adv_{question_idx:05d}_05",
                confidence=1.0
            ))

        elif trap_code == "T04":
            # T04: 假摔碰瓷 (IMU 平缓顺势躺下 vs 录音大声呼痛索赔五万)
            sensor_data["raw_imu_g_force"] = [1.02, 0.98, 0.95, 0.91, 0.88, 1.00]
            sensor_data["motion_state"] = "GENTLE_SUPINE_TRANSITION_NO_IMPACT"
            sensor_data["impact_peak_g"] = 1.05
            mic_stream.append({
                "snippet_id": f"mic_adv_{question_idx:05d}_06",
                "speaker_id": counterpart,
                "ambient_noise_db": ambient_noise_db,
                "text": f"哎呦！撞死人啦！骨头都撞碎了！不赔我五万块钱医药费，你今天休想走！",
                "is_junk": False
            })
            fact_desc = f"{counterpart}发生疑似假摔碰瓷讹诈，传感器IMU无撞击峰值仅轻微平躺，但现场录音大声索赔五万元"
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id=event.domain.value,
                semantic_intent="STAGED_FALL_FRAUD_ACCUSATION",
                anchor_entities=[persona_anchor, counterpart, "无撞击平躺", "索赔五万元", "疑似碰瓷讹诈"],
                directional_keywords=["假摔碰瓷", "碰瓷讹诈", "虚假摔倒", "无碰撞顺势倒地", "索赔医药费", "欺诈碰瓷争议"],
                core_content=fact_desc,
                source_ref_id=f"mic_adv_{question_idx:05d}_06",
                confidence=0.95
            ))

        else:
            # T00: 自然真实态事件
            # 添加标准对话切片
            mic_stream.append({
                "snippet_id": f"mic_core_{question_idx:05d}_01",
                "speaker_id": counterpart,
                "ambient_noise_db": ambient_noise_db,
                "text": f"{call_name}！{dialogue_dialect_hint}，今天这事必须给个明确说法！",
                "is_junk": False
            })
            user_dialogue_stream.append({
                "utterance_id": f"ut_core_{question_idx:05d}_01",
                "raw_speech": f"你别冲动，听我讲，这{amount}万块钱的账单明细我全保留着，后天咱们找第三方公证！",
                "context_scene": f"{persona_display}面对冲突交涉对质",
                "emotional_tone": "TENSE_RESILIENT",
                "is_junk": False
            })
            ground_truth_facts.append(DirectionalSemanticFact(
                fact_id=f"fact_{question_idx:05d}_01",
                dimension_id=event.domain.value,
                semantic_intent=event.semantic_intent,
                anchor_entities=anchors,
                directional_keywords=event.directional_keywords,
                core_content=core_desc,
                source_ref_id=f"mic_core_{question_idx:05d}_01",
                confidence=1.0
            ))

            # 如果是健康急症，增加生理事实
            if event.domain == CognitiveDomain.HEALTH:
                ground_truth_facts.append(DirectionalSemanticFact(
                    fact_id=f"fact_{question_idx:05d}_02",
                    dimension_id="dim:health",
                    semantic_intent="ACUTE_PHYSIOLOGICAL_SYMPTOM",
                    anchor_entities=[persona_anchor, "突发生理危象", "手环传感器异动", "紧急就医救治"],
                    directional_keywords=["急性发作", "重疾危象", "紧急就诊", "危急生理指标", "呼叫救护车", "抢救救助"],
                    core_content=f"{persona_display}突发生理急症，传感器波形异常且伴随严重躯体症状，亟需医疗干预",
                    source_ref_id="sensor_stream",
                    confidence=1.0
                ))

        # 构建规范 CleaningQuestion
        question_id = f"Q_{self.generator_id}_{question_idx:05d}"
        return CleaningQuestion(
            question_id=question_id,
            generator_agent=self.generator_id,
            timestamp_utc=dt_base.isoformat(),
            difficulty=diff,
            persona_tag=persona.persona_tag,
            sensor_stream=sensor_data,
            mic_stream=mic_stream,
            voiceprint_cluster=voiceprint,
            app_message_stream=app_message_stream,
            user_dialogue_stream=user_dialogue_stream,
            ground_truth_facts=ground_truth_facts,
            ground_truth_junk_ids=ground_truth_junk_ids
        )

    def generate_batch(
        self,
        count: int = 1000,
        balance_domains: bool = True
    ) -> List[CleaningQuestion]:
        """批量生成考题，强制五大认知域均衡分配 (各 >= 15%)。"""
        domains = list(CognitiveDomain)
        questions: List[CleaningQuestion] = []

        for i in range(1, count + 1):
            if balance_domains:
                domain = domains[(i - 1) % len(domains)]
            else:
                domain = None
            q = self.generate_single_question(question_idx=i, forced_domain=domain)
            questions.append(q)

        return questions

    def export_to_files(
        self,
        count: int,
        questions_path: Path,
        gt_path: Path,
        batch_size: int = 500
    ) -> Dict[str, Any]:
        """流式高效落盘到 JSONL，保证内存安全并生成统计报告。"""
        questions_path.parent.mkdir(parents=True, exist_ok=True)
        gt_path.parent.mkdir(parents=True, exist_ok=True)

        domain_counter: Dict[str, int] = {d.value: 0 for d in CognitiveDomain}
        difficulty_counter: Dict[str, int] = {}
        total_facts = 0
        total_junks = 0

        domains = list(CognitiveDomain)

        with open(questions_path, "w", encoding="utf-8") as f_q, \
             open(gt_path, "w", encoding="utf-8") as f_gt:

            for i in range(1, count + 1):
                # 轮换认知域保证五大域严格均衡 (各 20% >= 15%)
                forced_domain = domains[(i - 1) % len(domains)]
                q = self.generate_single_question(question_idx=i, forced_domain=forced_domain)

                # 统计
                diff_str = str(q.difficulty.value)
                difficulty_counter[diff_str] = difficulty_counter.get(diff_str, 0) + 1
                for fact in q.ground_truth_facts:
                    domain_counter[fact.dimension_id] = domain_counter.get(fact.dimension_id, 0) + 1
                    total_facts += 1
                total_junks += len(q.ground_truth_junk_ids)

                # 题目流 (含完整字段)
                f_q.write(q.model_dump_json() + "\n")

                # 标答流
                gt_entry = {
                    "question_id": q.question_id,
                    "generator_agent": q.generator_agent,
                    "persona_tag": q.persona_tag,
                    "ground_truth_junk_ids": q.ground_truth_junk_ids,
                    "ground_truth_facts": [f.model_dump() for f in q.ground_truth_facts]
                }
                f_gt.write(json.dumps(gt_entry, ensure_ascii=False) + "\n")

        stats = {
            "total_questions": count,
            "generator_agent": self.generator_id,
            "domain_distribution": domain_counter,
            "difficulty_distribution": difficulty_counter,
            "total_facts": total_facts,
            "total_junks": total_junks,
            "avg_facts_per_question": round(total_facts / max(count, 1), 2),
            "avg_junks_per_question": round(total_junks / max(count, 1), 2),
            "questions_file": str(questions_path),
            "ground_truth_file": str(gt_path)
        }
        return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="AIOS 3.0 7D Combinatorial Life-Spectrum Question Generator")
    parser.add_argument("--agent-id", type=str, default="agent-01", help="出卷战队编号 (如 agent-01)")
    parser.add_argument("--count", type=int, default=1000, help="生成题目总数")
    parser.add_argument("--out-dir", type=str, default="benchmarks/data_cleaning", help="输出基准目录")
    args = parser.parse_args()

    out_base = Path(args.out_dir)
    questions_file = out_base / "questions" / f"questions_{args.agent_id}.jsonl"
    gt_file = out_base / "ground_truth" / f"gt_{args.agent_id}.jsonl"

    print(f"[*] 启动 7 维拓扑高熵出卷引擎: 战队={args.agent_id}, 题数={args.count}")
    engine = SevenDimensionalQuestionEngine(generator_id=args.agent_id)
    stats = engine.export_to_files(count=args.count, questions_path=questions_file, gt_path=gt_file)
    print("[+] 生成完成！统计摘要:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
