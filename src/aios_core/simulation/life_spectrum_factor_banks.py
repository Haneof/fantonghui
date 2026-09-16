"""全人生谱系高熵因子库（AIOS 3.0 数据清洗大考 · 出题侧）。

定位
----
本模块是**纯数据因子库**，不产生任何断言、不做任何评分判断，只负责把"千人千面"
的真实人生谱系拆成可组合的七大维度因子：

1. ``PERSONAS``           维度一：佩戴者身份与人生阶段（16 岁 → 90 岁、全职业光谱）
2. ``EVENT_FAMILIES``     维度二：五大认知域的极限事件谱系（dim:health/finance/social/career/life）
3. ``SENSOR_PROFILES``    维度三：外部物理传感器高熵波形库（S00~S06）
4. ``ACOUSTIC_TOPOLOGIES`` 维度四：声学真实环境拓扑与极端噪声源（A01~A12）
5. ``DIALECT_PACKS``      维度五：语言修辞、方言黑话与人际伪装
6. ``SPEAKER_ROLES``      维度六：声纹聚类与混杂说话人拓扑（3~24 人）
7. ``TRAP_SPECS``         维度七：真假对抗与事实反转陷阱（T01~T08）

设计纪律（对应出题质量红线）
----------------------------
* **零模板化**：每个因子都带多套语料模具与随机槽位（人名/金额/日期/地点/症状/物品），
  组合空间远超 10^12，禁止"张三李四王五"式刷题；
* **真实医学与生活逻辑**：事件族携带 ``sensor_hints``，把传感器波形与身体/生活逻辑
  硬绑定（疑似心梗不允许配 S06 跑步基线，假摔碰瓷不允许出现 15G 冲击波峰）；
* **方向性同义词簇**：每个事实自带 ≥6 个方向近义词，供裁判端方向容差判分使用；
* **方言与修辞可追溯**：方言因子按"语用功能"取值（讨钱/威胁/疼痛/哀求/反讽/吹牛…），
  修辞因子区分"真事实"与"无效发泄"，供大模型做真伪意图辨析。

本文件不 import 任何 AIOS 内部模块，唯一外部依赖是标准库，保证可被任何战队
独立复用与扩展。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

__all__ = [
    "Relation",
    "Persona",
    "EventFamily",
    "AcousticTopology",
    "TrapSpec",
    "PERSONAS",
    "EVENT_FAMILIES",
    "ACOUSTIC_TOPOLOGIES",
    "SENSOR_PROFILES",
    "DIALECT_PACKS",
    "SPEAKER_ROLES",
    "TRAP_SPECS",
    "RHETORIC_SPECS",
    "RHETORIC_FACTS",
    "JUNK_SELF_TALK",
    "NAME_BANK",
    "SURNAMES",
    "AMOUNT_BANK",
    "DATE_BANK",
    "PLACE_BANK",
    "ITEM_BANK",
    "SYMPTOM_BANK",
    "MED_BANK",
    "DOMAIN_IDS",
    "FOCUS_STREAM_WEIGHTS",
]


# --------------------------------------------------------------------------------------
# 基础结构
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Relation:
    """佩戴者的固定人际关系（声纹与实体锚点复用的根基）。"""

    role: str          # spouse / parent / child / boss / creditor / doctor / ...
    name: str          # 称谓（老张 / 王医生 / 我妈 / 二房东刘姐）
    speaker_id: str    # 声纹标识 spk_xxx
    dialect: str = ""  # 该交互人的方言；留空则跟随佩戴者


@dataclass(frozen=True)
class Persona:
    """维度一：千人千面的佩戴者身份。"""

    pid: str
    tag: str
    label: str
    age: int
    gender: str                      # "m" / "f"
    dialect: str                     # DIALECT_PACKS 键
    region: str                      # PLACE_BANK 键
    occupation: str
    life_stage: str
    threads: Tuple[str, ...]         # 该人生阶段长期缠绕的矛盾线
    conditions: Tuple[str, ...]      # 基础疾病/慢性状态
    home_scene: str
    work_scene: str
    apps: Tuple[str, ...]
    companions: Tuple[Relation, ...]


@dataclass(frozen=True)
class EventFamily:
    """维度二：五大认知域的极限事件族（一个族 = 一类真实冲突 + 方向同义词簇）。"""

    fid: str
    domain: str                      # dim:health / dim:finance / dim:social / dim:career / dim:life
    intent: str
    keywords: Tuple[str, ...]        # 方向性同义词簇（≥6）
    severity: str                    # routine / serious / critical
    sensor_hints: Tuple[str, ...]    # 与事件逻辑自洽的传感器波形
    roles: Tuple[str, ...]           # 需要出场的交互角色（self 表示佩戴者自述）
    fact_lines: Tuple[str, ...]      # 标准事实 core_content 模具
    user_lines: Tuple[str, ...]      # 佩戴者原话模具
    other_lines: Tuple[str, ...]     # 交互人原话模具（可用 {role:xxx} 指定角色）
    app_keys: Tuple[Tuple[str, str, str], ...]  # 关键 APP 消息 (app, 发送方, 内容模具)
    dialect_fn: str = "money"        # 本族最贴合的方言语用功能
    entity_slots: Tuple[str, ...] = ("amount",)


@dataclass(frozen=True)
class AcousticTopology:
    """维度四：声学环境拓扑。"""

    aid: str
    label: str
    db_range: Tuple[float, float]
    junk_lines: Tuple[str, ...]      # 环境垃圾片段（必须被物理剪枝）
    overlap_rate: float = 0.35       # 抢话/重叠说话概率


@dataclass(frozen=True)
class TrapSpec:
    """维度七：真假对抗陷阱。"""

    tid: str
    label: str
    intent: str
    keywords: Tuple[str, ...]
    claim_line: str                  # 陷阱方的"假象"陈述（可能是截图/口供/语音）
    claim_app: str                   # 假象所在的 APP（空串表示只用语音）
    counter_line: str                # 反证据（银行/医院/法院/时间戳）
    counter_app: str
    fact_line: str                   # 最终标答事实（真相）
    junk_claim: bool = False         # 假象是否属于必须删除的垃圾（吹牛类为 True）


def _rel(role: str, name: str, speaker_id: str, dialect: str = "") -> Relation:
    return Relation(role=role, name=name, speaker_id=speaker_id, dialect=dialect)


DOMAIN_IDS: Tuple[str, ...] = ("dim:health", "dim:finance", "dim:social", "dim:career", "dim:life")

# 数据流聚焦配比（Master Dispatch #11：传感器 30% / MIC 30% / 声纹 20% / APP 15% / 对话 5%）
FOCUS_STREAM_WEIGHTS: Dict[str, int] = {
    "sensor": 30,
    "mic": 30,
    "voiceprint": 20,
    "app": 15,
    "dialogue": 5,
}


# --------------------------------------------------------------------------------------
# 维度一：50 位佩戴者（16 岁 → 90 岁，全职业光谱）
# --------------------------------------------------------------------------------------
PERSONAS: Tuple[Persona, ...] = (
    Persona(
        pid="D01",
        tag="D01_高三复读生_17岁_焦虑躯体化与陪读高压",
        label="17岁高三复读生（住校）",
        age=17,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="复读学校高三学生",
        life_stage="二次高考冲刺，父母轮流在县城租房陪读，睡眠被彻底榨干",
        threads=("重度失眠", "焦虑躯体化", "父母高压陪读", "同学间文具借还"),
        conditions=("慢性失眠", "考试焦虑伴躯体化", "功能性胃痛"),
        home_scene="学校六人间宿舍与校外陪读出租屋",
        work_scene="晚自习教室与走廊背书",
        apps=("WeChat", "班级小管家", "网易有道词典", "支付宝"),
        companions=(
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("parent", "我爸", "spk_parent_father"),
            _rel("teacher", "班主任老吴", "spk_teacher_wu"),
            _rel("classmate", "同桌小赵", "spk_classmate_zhao"),
        ),
    ),
    Persona(
        pid="D02",
        tag="D02_大厂互联网外包_24岁_通宵排障与隔断间漏水",
        label="24岁大厂互联网外包运维",
        age=24,
        gender="m",
        dialect="shanghai",
        region="shanghai",
        occupation="互联网大厂外包运维工程师",
        life_stage="连续通宵排查线上故障，被主管甩锅，租住隔断间发霉漏水",
        threads=("连续通宵排障", "被主管甩锅背锅", "隔断间漏水", "合租室友纠纷"),
        conditions=("睡眠剥夺", "窦性心动过速", "慢性胃炎"),
        home_scene="外环外隔断间，墙角常年渗水",
        work_scene="机房与开放式工位",
        apps=("DingTalk", "WeChat", "飞书", "招商银行", "美团"),
        companions=(
            _rel("boss", "主管老陈", "spk_boss_chen"),
            _rel("roommate", "室友小马", "spk_roommate_ma"),
            _rel("landlord", "二房东王哥", "spk_landlord_wang", "henan"),
            _rel("coworker", "同组小刘", "spk_coworker_liu"),
        ),
    ),
    Persona(
        pid="D03",
        tag="D03_孕晚期准妈妈_28岁_妊娠高血糖与月嫂之争",
        label="28岁孕晚期准妈妈",
        age=28,
        gender="f",
        dialect="cantonese",
        region="guangzhou",
        occupation="外贸公司跟单员（孕期保胎）",
        life_stage="孕 34 周，妊娠期高血糖需要每日胎动与血糖记录，婆媳为月嫂人选僵持",
        threads=("妊娠期高血糖", "胎动记录异常", "婆媳月嫂争执", "产检指标危机"),
        conditions=("妊娠期糖尿病", "贫血", "耻骨联合分离痛"),
        home_scene="天河区两居室，婆婆住次卧",
        work_scene="居家远程跟单",
        apps=("WeChat", "美柚", "微信读书", "招商银行", "饿了么"),
        companions=(
            _rel("spouse", "老公阿强", "spk_spouse_qiang"),
            _rel("parent", "婆婆", "spk_mother_in_law"),
            _rel("doctor", "产检李医生", "spk_doctor_li"),
            _rel("coworker", "同事阿珊", "spk_coworker_shan"),
        ),
    ),
    Persona(
        pid="D04",
        tag="D04_长途重卡司机_32岁_高原反应与油卡盗刷",
        label="32岁长途重卡货运司机",
        age=32,
        gender="m",
        dialect="shaanxi",
        region="shaanxi",
        occupation="个体长途重卡司机（挂靠车队）",
        life_stage="川藏线连轴转，疲劳驾驶与高反叠加，油卡被车队内部人员盗刷",
        threads=("连续疲劳驾驶", "高原反应", "路怒别车", "油卡盗刷与高速堵车"),
        conditions=("高血压", "腰椎间盘突出", "高尿酸"),
        home_scene="车上卧铺与西安城中村出租房",
        work_scene="G318 折多山段与高速服务区",
        apps=("高德地图", "WeChat", "货车帮", "建设银行", "支付宝"),
        companions=(
            _rel("spouse", "媳妇", "spk_spouse_wife"),
            _rel("boss", "车队老板老康", "spk_boss_kang"),
            _rel("coworker", "搭档小杜", "spk_coworker_du"),
            _rel("stranger", "别车司机", "spk_driver_rival"),
        ),
    ),
    Persona(
        pid="D05",
        tag="D05_失业离异二房东_36岁_被诉与胃出血",
        label="36岁失业离异二房东",
        age=36,
        gender="f",
        dialect="dongbei",
        region="dongbei",
        occupation="失业后靠转租差价维生",
        life_stage="被原房东起诉解除合同，租客拖欠租金，前夫拒付抚养费，胃溃疡急性出血",
        threads=("被原房东起诉", "租客拖欠房租", "抚养费催缴", "胃溃疡急性出血"),
        conditions=("胃溃疡", "焦虑状态", "缺铁性贫血"),
        home_scene="老小区两室一厅，客厅改隔断",
        work_scene="房产中介门店与法院诉服中心",
        apps=("WeChat", "贝壳找房", "人民法院在线服务", "支付宝", "招商银行"),
        companions=(
            _rel("ex_spouse", "前夫老周", "spk_ex_spouse_zhou"),
            _rel("tenant", "租客小徐", "spk_tenant_xu"),
            _rel("landlord", "原房东赵姐", "spk_landlord_zhao"),
            _rel("child", "女儿甜甜", "spk_child_tiantian"),
        ),
    ),
    Persona(
        pid="D06",
        tag="D06_急诊科住院总医师_42岁_连轴24小时与医疗纠纷",
        label="42岁三甲医院急诊科住院总医师",
        age=42,
        gender="m",
        dialect="wuhan",
        region="wuhan",
        occupation="急诊科住院总医师",
        life_stage="连续 24 小时值守，处置医疗纠纷推搡，暴露于高传染风险",
        threads=("连轴转24小时", "医疗纠纷推搡", "高暴露感染风险", "家属下跪托付"),
        conditions=("高血压", "睡眠剥夺", "慢性腰痛"),
        home_scene="医院值班室折叠床",
        work_scene="急诊分诊台与抢救室",
        apps=("企业微信", "WeChat", "医院OA", "丁香园", "银行卡"),
        companions=(
            _rel("coworker", "护士长李姐", "spk_nurse_li"),
            _rel("patient_family", "患者家属", "spk_family_member"),
            _rel("boss", "科主任老胡", "spk_boss_hu"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D07",
        tag="D07_钢筋班包工头_48岁_痛风并发讨薪",
        label="48岁建筑工地钢筋班包工头",
        age=48,
        gender="m",
        dialect="sichuan",
        region="chengdu",
        occupation="建筑工地钢筋班包工头",
        life_stage="总包结算款被压，班组三十号人堵门讨薪，痛风急性发作下不了地",
        threads=("农民工讨薪围堵", "发包方阴阳合同", "痛风急性发作", "工人高空坠落险情"),
        conditions=("痛风", "高血压", "脂肪肝"),
        home_scene="城中村出租屋与工地彩钢房",
        work_scene="主体结构钢筋作业面与项目部板房",
        apps=("WeChat", "工地实名制考勤", "支付宝", "建设银行", "货车帮"),
        companions=(
            _rel("creditor", "班组长老张", "spk_creditor_zhang"),
            _rel("boss", "项目总包王经理", "spk_boss_wang"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
            _rel("coworker", "工人小刘", "spk_worker_liu"),
        ),
    ),
    Persona(
        pid="D08",
        tag="D08_民营财务总监_53岁_假发票稽查与失眠盗汗",
        label="53岁民营企业财务总监",
        age=53,
        gender="f",
        dialect="shandong",
        region="shandong",
        occupation="民营企业财务总监",
        life_stage="更年期失眠盗汗叠加税务稽查突击上门，大额发票对账责任压顶",
        threads=("大额假发票对账", "税务稽查突击", "更年期失眠盗汗", "女儿出嫁礼金纠纷"),
        conditions=("更年期综合征", "高血压", "甲状腺结节"),
        home_scene="市区三居室",
        work_scene="财务办公室与税务稽查接待室",
        apps=("WeChat", "电子税务局", "金蝶云", "工商银行", "企业微信"),
        companions=(
            _rel("boss", "董事长老孙", "spk_boss_sun"),
            _rel("coworker", "出纳小丁", "spk_coworker_ding"),
            _rel("tax_officer", "稽查科赵科长", "spk_tax_officer_zhao"),
            _rel("child", "女儿", "spk_child_daughter"),
        ),
    ),
    Persona(
        pid="D09",
        tag="D09_初老退休教师_65岁_脑萎缩前兆与养老房套牢",
        label="65岁初老退休教师",
        age=65,
        gender="m",
        dialect="tianjin",
        region="tianjin",
        occupation="退休中学语文教师",
        life_stage="轻度脑萎缩前兆健忘，候鸟式养老房被套牢，老伴白内障手术在即",
        threads=("轻度脑萎缩前兆", "养老房套牢", "保健品传销洗脑", "老伴白内障手术"),
        conditions=("轻度认知障碍", "高血压", "老花眼"),
        home_scene="老式学区房与海南候鸟公寓",
        work_scene="社区活动室与老年大学",
        apps=("WeChat", "拼多多", "支付宝", "国家医保服务平台", "抖音"),
        companions=(
            _rel("spouse", "老伴", "spk_spouse_wife"),
            _rel("child", "儿子", "spk_child_son"),
            _rel("stranger", "保健品推销员", "spk_salesman"),
            _rel("neighbor", "邻居老刘", "spk_neighbor_liu"),
        ),
    ),
    Persona(
        pid="D10",
        tag="D10_独居空巢老人_78岁_骨质疏松与遗忘煤气",
        label="78岁独居空巢老人",
        age=78,
        gender="f",
        dialect="shanghai",
        region="shanghai",
        occupation="独居退休纺织女工",
        life_stage="骨质疏松随时可能髋部骨折，轻度阿尔茨海默走失风险，煤气常忘关",
        threads=("骨质疏松髋部风险", "轻度阿尔茨海默走失", "煤气遗忘未关", "邻里漏水争执"),
        conditions=("骨质疏松", "轻度阿尔茨海默病", "冠心病"),
        home_scene="老公房六楼无电梯",
        work_scene="菜场与小区花园",
        apps=("WeChat", "拼多多", "社区养老服务", "支付宝", "水滴筹"),
        companions=(
            _rel("child", "女儿", "spk_child_daughter"),
            _rel("neighbor", "楼下邻居", "spk_neighbor_downstairs"),
            _rel("community", "社区网格员小周", "spk_community_zhou"),
            _rel("doctor", "家庭医生", "spk_doctor_family"),
        ),
    ),
    Persona(
        pid="D11",
        tag="D11_极限攀岩越野者_30岁_崖壁滑坠与失温",
        label="30岁户外越野与极限攀岩者",
        age=30,
        gender="m",
        dialect="sichuan",
        region="chengdu",
        occupation="户外俱乐部领队兼极限攀岩者",
        life_stage="独攀失足滑坠悬挂崖壁，卫星电话盲区，失温脱水叠加骨折自救",
        threads=("失足滑坠悬挂崖壁", "失温脱水", "卫星电话盲区", "骨折自救"),
        conditions=("陈旧性踝关节损伤", "低体温史", "运动性哮喘"),
        home_scene="城郊青旅与改装面包车",
        work_scene="四姑娘山与贡嘎西坡",
        apps=("两步路", "WeChat", "Windy", "支付宝", "救援队电话"),
        companions=(
            _rel("coworker", "搭档老冯", "spk_partner_feng"),
            _rel("rescuer", "救援队老蒋", "spk_rescuer_jiang"),
            _rel("spouse", "女友", "spk_spouse_girlfriend"),
            _rel("stranger", "山下牧民", "spk_herdsman"),
        ),
    ),
    Persona(
        pid="D12",
        tag="D12_乡村外卖骑手_22岁_暴雨超时与电瓶车被盗",
        label="22岁乡村外卖骑手",
        age=22,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="县域外卖平台骑手",
        life_stage="暴雨天送单被罚超时，电瓶车被盗，与商户出餐口角，膝盖滑囊炎",
        threads=("暴雨超时罚款", "电瓶车被盗", "商户出餐口角", "膝盖滑囊炎"),
        conditions=("髌前滑囊炎", "过敏性鼻炎", "胃痛"),
        home_scene="县城合租平房",
        work_scene="县城商业街与暴雨中的非机动车道",
        apps=("美团骑手", "WeChat", "支付宝", "快手", "boss直聘"),
        companions=(
            _rel("boss", "站点站长", "spk_boss_station"),
            _rel("merchant", "麻辣烫店老板", "spk_merchant"),
            _rel("coworker", "骑手兄弟阿凯", "spk_rider_kai"),
            _rel("parent", "我妈", "spk_parent_mother"),
        ),
    ),
    Persona(
        pid="D13",
        tag="D13_餐饮连锁店主_45岁_抽检危机与厨师罢工",
        label="45岁中式餐饮连锁店主",
        age=45,
        gender="m",
        dialect="hunan",
        region="hunan",
        occupation="中式快餐连锁店主（3 家门店）",
        life_stage="市场监管局抽检不合格危机，后厨集体罢工，供应商上门催款",
        threads=("食品安全抽检危机", "厨师集体罢工", "供应商催款", "油烟烫伤"),
        conditions=("高血脂", "油烟性咽炎", "右臂烫伤瘢痕"),
        home_scene="店铺楼上自建房",
        work_scene="后厨与前厅",
        apps=("WeChat", "美团商家版", "支付宝", "云闪付", "抖音"),
        companions=(
            _rel("coworker", "厨师长阿彪", "spk_chef_biao"),
            _rel("supplier", "食材供应商老陶", "spk_supplier_tao"),
            _rel("officer", "市场监管所杨队", "spk_officer_yang"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D14",
        tag="D14_远洋轮机长_38岁_断网耳鸣与幽闭恐惧",
        label="38岁远洋货轮轮机长",
        age=38,
        gender="m",
        dialect="minnan",
        region="minnan",
        occupation="远洋货轮轮机长",
        life_stage="连续航行 40 天，卫星断网后补收家书，机舱高分贝噪音致耳鸣与幽闭恐惧",
        threads=("连续航行40天", "卫星断网收家信", "机舱噪音耳鸣", "幽闭恐惧"),
        conditions=("噪声性听力损失", "幽闭恐惧倾向", "胃食管反流"),
        home_scene="船上生活舱",
        work_scene="主机舱与集控室",
        apps=("WeChat", "海事卫星邮件", "支付宝", "招商银行", "船讯网"),
        companions=(
            _rel("coworker", "大管轮老蔡", "spk_engineer_cai"),
            _rel("spouse", "妻子阿梅", "spk_spouse_mei"),
            _rel("boss", "船长老吴", "spk_captain_wu"),
            _rel("child", "儿子", "spk_child_son"),
        ),
    ),
    Persona(
        pid="D15",
        tag="D15_自由插画师_26岁_颈椎压迫与甲方毁约",
        label="26岁独立自由插画师",
        age=26,
        gender="f",
        dialect="shanghai",
        region="shanghai",
        occupation="独立自由插画师（接商稿）",
        life_stage="颈椎神经压迫致手部麻木，甲方无底线改图并毁约，猫咪重度腹膜炎",
        threads=("颈椎神经压迫手麻", "甲方无底线改图毁约", "版权侵权维权", "猫咪重度腹膜炎"),
        conditions=("颈椎病（神经根型）", "干眼症", "慢性胃炎"),
        home_scene="一居室工作室",
        work_scene="数位板前的书桌",
        apps=("WeChat", "小红书", "站酷", "支付宝", "precreate 版权登记"),
        companions=(
            _rel("client", "甲方品牌方小郑", "spk_client_zheng"),
            _rel("vet", "宠物医院张医生", "spk_vet_zhang"),
            _rel("friend", "同行好友", "spk_friend_painter"),
            _rel("parent", "我妈", "spk_parent_mother"),
        ),
    ),
    Persona(
        pid="D16",
        tag="D16_初三田径特长生_16岁_体育加试扭伤与宿舍手机被收",
        label="16岁初三体育特长生",
        age=16,
        gender="m",
        dialect="shandong",
        region="shandong",
        occupation="县城初中初三田径特长生",
        life_stage="中考体育加试前踝关节扭伤，宿舍手机被收，与同学发生冷暴力摩擦",
        threads=("体育加试前扭伤", "宿舍手机被收", "同学冷暴力", "教练加练"),
        conditions=("踝关节韧带损伤", "生长痛", "运动性低血糖"),
        home_scene="学校男生宿舍",
        work_scene="操场与训练房",
        apps=("WeChat", "班级群", "抖音", "支付宝"),
        companions=(
            _rel("teacher", "教练老赵", "spk_coach_zhao"),
            _rel("classmate", "队友小周", "spk_classmate_zhou"),
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("dorm", "宿管老师", "spk_dorm_teacher"),
        ),
    ),
    Persona(
        pid="D17",
        tag="D17_汽修实习生_19岁_师傅打骂与腰椎扭伤",
        label="19岁大专汽修实习生",
        age=19,
        gender="m",
        dialect="dongbei",
        region="dongbei",
        occupation="4S 店汽修实习生",
        life_stage="师徒矛盾激化被克扣实习补贴，抬变速箱时闪了腰",
        threads=("师徒矛盾", "克扣实习补贴", "腰椎扭伤", "夜校专升本"),
        conditions=("急性腰扭伤", "腱鞘炎", "近视"),
        home_scene="4S 店集体宿舍",
        work_scene="维修车间举升机旁",
        apps=("WeChat", "QQ", "boss直聘", "支付宝"),
        companions=(
            _rel("boss", "带班师傅老邢", "spk_master_xing"),
            _rel("coworker", "同批实习生小唐", "spk_intern_tang"),
            _rel("parent", "我爸", "spk_parent_father"),
            _rel("doctor", "骨科门诊医生", "spk_doctor_bone"),
        ),
    ),
    Persona(
        pid="D18",
        tag="D18_快递分拣夜班员_21岁_爆仓与腕管综合征",
        label="21岁快递分拨中心夜班分拣员",
        age=21,
        gender="f",
        dialect="henan",
        region="henan",
        occupation="快递分拨中心夜间分拣员",
        life_stage="双十一爆仓连上 14 天夜班，手腕麻木，宿舍消防通道被堵",
        threads=("爆仓连班", "腕管综合征", "宿舍消防隐患", "组长的绩效考核刁难"),
        conditions=("腕管综合征", "月经失调", "干眼症"),
        home_scene="园区集体宿舍（上下铺）",
        work_scene="分拨中心传送带",
        apps=("WeChat", "钉钉", "拼多多", "支付宝", "快手"),
        companions=(
            _rel("boss", "组长马姐", "spk_shift_leader_ma"),
            _rel("coworker", "工友小杨", "spk_worker_yang"),
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("doctor", "社区医院医生", "spk_doctor_community"),
        ),
    ),
    Persona(
        pid="D19",
        tag="D19_规培护士_23岁_夜班晕倒与针刺伤",
        label="23岁三甲医院规培护士",
        age=23,
        gender="f",
        dialect="hubei",
        region="wuhan",
        occupation="三甲医院 ICU 规培护士",
        life_stage="夜班晕倒被疑低血糖，给乙肝患者拔针时发生针刺伤暴露",
        threads=("夜班晕倒", "针刺伤职业暴露", "排班不公", "带教老师严苛"),
        conditions=("低血糖倾向", "缺铁性贫血", "焦虑状态"),
        home_scene="医院附近合租单间",
        work_scene="ICU 病房与配药间",
        apps=("企业微信", "WeChat", "医院OA", "支付宝", "美团"),
        companions=(
            _rel("coworker", "带教老师王姐", "spk_mentor_wang"),
            _rel("doctor", "感控科医生", "spk_doctor_infection"),
            _rel("roommate", "室友小谢", "spk_roommate_xie"),
            _rel("parent", "我妈", "spk_parent_mother"),
        ),
    ),
    Persona(
        pid="D20",
        tag="D20_乡镇公务员_25岁_防汛值守与催婚",
        label="25岁乡镇公务员",
        age=25,
        gender="m",
        dialect="hunan",
        region="hunan",
        occupation="乡镇政府综合办科员",
        life_stage="汛期连续值守河道，材料压稿到凌晨，家里天天电话催婚",
        threads=("汛期值守", "材料压稿", "催婚压力", "基层垫资报销难"),
        conditions=("慢性咽炎", "颈椎不适", "睡眠不足"),
        home_scene="乡镇政府周转房",
        work_scene="防汛值班室与村委会",
        apps=("WeChat", "学习强国", "政务钉钉", "支付宝", "12345 热线"),
        companions=(
            _rel("boss", "分管副镇长", "spk_deputy_head"),
            _rel("coworker", "同事小夏", "spk_coworker_xia"),
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("village_head", "村支书老廖", "spk_village_head_liao"),
        ),
    ),
    Persona(
        pid="D21",
        tag="D21_跨境电商卖家_27岁_封店与货代跑路",
        label="27岁跨境电商创业卖家",
        age=27,
        gender="f",
        dialect="minnan",
        region="minnan",
        occupation="跨境电商公司创始人（8 人团队）",
        life_stage="平台店铺被判违规封停，货代卷货跑路，信用证面临拒付",
        threads=("平台封店申诉", "货代跑路货款两空", "信用证拒付", "团队工资压力"),
        conditions=("焦虑发作", "颈椎病", "失眠"),
        home_scene="loft 公寓兼办公室",
        work_scene="仓库与线上会议室",
        apps=("WeChat", "亚马逊卖家", "钉钉", "中国银行", "货代查询"),
        companions=(
            _rel("partner", "合伙人阿杰", "spk_partner_jie"),
            _rel("supplier", "工厂老板老潘", "spk_supplier_pan"),
            _rel("lawyer", "律师老许", "spk_lawyer_xu"),
            _rel("coworker", "运营小黄", "spk_coworker_huang"),
        ),
    ),
    Persona(
        pid="D22",
        tag="D22_互联网产品经理_29岁_裁员名单与惊恐发作",
        label="29岁互联网产品经理",
        age=29,
        gender="m",
        dialect="dongbei",
        region="dongbei",
        occupation="互联网公司产品经理",
        life_stage="裁员优化名单流言压顶，惊恐发作在会议室，期权回购纠纷缠身",
        threads=("裁员优化名单", "惊恐发作", "期权回购纠纷", "房贷压力"),
        conditions=("惊恐障碍", "窦性心动过速", "胃食管反流"),
        home_scene="贷款买的两居室",
        work_scene="开放工位与会议室",
        apps=("飞书", "WeChat", "脉脉", "招商银行", "支付宝"),
        companions=(
            _rel("boss", "总监老康", "spk_boss_kang"),
            _rel("coworker", "同事小冯", "spk_coworker_feng"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
            _rel("lawyer", "劳动法律师", "spk_lawyer_labor"),
        ),
    ),
    Persona(
        pid="D23",
        tag="D23_双胞胎妈妈_31岁_产后抑郁与乳腺炎",
        label="31岁双胞胎新手妈妈",
        age=31,
        gender="f",
        dialect="sichuan",
        region="chengdu",
        occupation="产假中的财务专员",
        life_stage="双胞胎夜奶三小时一轮，乳腺炎高热 39.5℃，育儿嫂突然辞职",
        threads=("产后抑郁", "急性乳腺炎高热", "育儿嫂辞职", "婆媳育儿观冲突"),
        conditions=("产后抑郁倾向", "急性乳腺炎", "睡眠剥夺"),
        home_scene="三居室，婴儿床占满客厅",
        work_scene="家中的吸奶角与阳台",
        apps=("WeChat", "亲宝宝", "美团", "支付宝", "医院挂号"),
        companions=(
            _rel("spouse", "老公", "spk_spouse_husband"),
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("doctor", "产科医生", "spk_doctor_obstetrics"),
            _rel("nanny", "育儿嫂刘姨", "spk_nanny_liu"),
        ),
    ),
    Persona(
        pid="D24",
        tag="D24_城中村小超市夫妻店主_33岁_赊账与拆迁通知",
        label="33岁城中村小超市夫妻店主",
        age=33,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="城中村小超市店主",
        life_stage="街坊赊账烂账堆积，供货商断供，门口贴上拆迁丈量通知",
        threads=("赊账烂账", "供货商断供", "拆迁丈量通知", "同行恶性竞争"),
        conditions=("慢性腰肌劳损", "慢性胃炎", "视力疲劳"),
        home_scene="超市后间搭的床",
        work_scene="三十平米超市与门口冰柜",
        apps=("WeChat", "收钱吧", "支付宝", "拼多多", "美团优选"),
        companions=(
            _rel("spouse", "老婆", "spk_spouse_wife"),
            _rel("supplier", "供货商老贺", "spk_supplier_he"),
            _rel("neighbor", "常赊账的老赖陈", "spk_debtor_chen"),
            _rel("officer", "拆迁办工作人员", "spk_demolition_staff"),
        ),
    ),
    Persona(
        pid="D25",
        tag="D25_视障按摩师_35岁_透析与涨租",
        label="35岁视障按摩师（慢性肾病透析）",
        age=35,
        gender="m",
        dialect="hubei",
        region="wuhan",
        occupation="盲人按摩店技师",
        life_stage="每周三次血液透析，导盲犬被投诉，店铺租约到期租金翻倍",
        threads=("血液透析排班", "导盲犬被投诉", "店铺涨租", "医保报销比例"),
        conditions=("慢性肾衰竭（透析期）", "肾性贫血", "高血压"),
        home_scene="老小区一楼，便于出入",
        work_scene="按摩店与血液净化中心",
        apps=("WeChat", "国家医保服务平台", "支付宝", "无障碍读屏", "拼多多"),
        companions=(
            _rel("coworker", "店主老韩", "spk_shop_owner_han"),
            _rel("doctor", "透析中心护士长", "spk_nurse_dialysis"),
            _rel("neighbor", "投诉的邻居", "spk_neighbor_complaint"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D26",
        tag="D26_乡村小学教师_37岁_留守儿童家访与肺结节",
        label="37岁乡村小学教师",
        age=37,
        gender="f",
        dialect="hunan",
        region="hunan",
        occupation="乡村中心小学教师",
        life_stage="暴雨冲毁教室围墙自筹修缮，留守儿童家访路上摔伤，体检查出肺结节",
        threads=("留守儿童家访", "自费修缮校舍", "体检查出肺结节", "职称评审材料"),
        conditions=("甲状腺结节", "肺微小结节待复查", "腰椎不适"),
        home_scene="学校教师周转房",
        work_scene="教室与泥泞山路",
        apps=("WeChat", "钉钉家校", "支付宝", "银行", "学习强国"),
        companions=(
            _rel("boss", "校长老朱", "spk_principal_zhu"),
            _rel("parent", "留守儿童奶奶", "spk_grandma"),
            _rel("coworker", "同办公室老师", "spk_coworker_teacher"),
            _rel("doctor", "呼吸科医生", "spk_doctor_respiratory"),
        ),
    ),
    Persona(
        pid="D27",
        tag="D27_上市公司销售总监_39岁_对赌与回扣举报",
        label="39岁上市公司销售总监",
        age=39,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="上市公司区域销售总监",
        life_stage="年度对赌缺口巨大，客户回扣被匿名举报，酒精性肝损伤检查异常",
        threads=("业绩对赌缺口", "回扣举报", "酒精性肝损伤", "团队核心离职"),
        conditions=("酒精性肝损伤", "高脂血症", "失眠"),
        home_scene="省会高档小区",
        work_scene="客户酒局与会议室",
        apps=("企业微信", "WeChat", "企业OA", "招商银行", "飞书"),
        companions=(
            _rel("boss", "集团副总老康", "spk_boss_group_kang"),
            _rel("coworker", "下属小夏", "spk_subordinate_xia"),
            _rel("client", "大客户罗总", "spk_client_luo"),
            _rel("lawyer", "合规部律师", "spk_compliance_lawyer"),
        ),
    ),
    Persona(
        pid="D28",
        tag="D28_消防特勤班长_41岁_灼伤与应激反应",
        label="41岁消防特勤班长",
        age=41,
        gender="m",
        dialect="shandong",
        region="shandong",
        occupation="消防救援站特勤班长",
        life_stage="化工厂爆燃救援中前臂灼伤，队友牺牲后应激反应反复，家人不理解",
        threads=("化工厂爆燃灼伤", "队友牺牲应激", "家人不理解", "训练伤复发"),
        conditions=("前臂二度灼伤", "创伤后应激", "右膝半月板损伤"),
        home_scene="消防站备勤室与家属院",
        work_scene="爆燃储罐区与训练塔",
        apps=("WeChat", "消防救援平台", "支付宝", "抖音", "银行"),
        companions=(
            _rel("boss", "队长", "spk_captain"),
            _rel("coworker", "队友小郑", "spk_firefighter_zheng"),
            _rel("doctor", "烧伤科医生", "spk_doctor_burn"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D29",
        tag="D29_菜市场猪肉摊主_44岁_注水肉举报与打架",
        label="44岁菜市场猪肉摊主",
        age=44,
        gender="f",
        dialect="sichuan",
        region="chengdu",
        occupation="农贸市场猪肉摊主",
        life_stage="被同行举报注水肉，摊位边界争执升级为推搡打架，手腕腱鞘炎发作",
        threads=("注水肉举报", "同行打架", "腱鞘炎", "摊位费涨价"),
        conditions=("腕部腱鞘炎", "静脉曲张", "高血脂"),
        home_scene="市场附近老旧小区",
        work_scene="农贸市场三号肉摊",
        apps=("WeChat", "支付宝", "微信收款", "抖音", "拼多多"),
        companions=(
            _rel("competitor", "隔壁摊主老赖", "spk_competitor_lai"),
            _rel("officer", "市场监管所人员", "spk_market_officer"),
            _rel("supplier", "屠宰场送肉司机", "spk_meat_driver"),
            _rel("spouse", "老公", "spk_spouse_husband"),
        ),
    ),
    Persona(
        pid="D30",
        tag="D30_夜班出租车司机_46岁_碰瓷与腰椎间盘突出",
        label="46岁夜班出租车司机",
        age=46,
        gender="m",
        dialect="tianjin",
        region="tianjin",
        occupation="夜班出租车司机",
        life_stage="凌晨被碰瓷索赔，久坐致腰椎间盘突出压迫坐骨神经，交班纠纷不断",
        threads=("碰瓷索赔", "腰椎间盘突出", "交班纠纷", "份子钱压力"),
        conditions=("腰椎间盘突出", "前列腺增生", "睡眠节律紊乱"),
        home_scene="老小区顶楼",
        work_scene="夜班出租车与加气站",
        apps=("WeChat", "滴滴车主", "支付宝", "交管12123", "快手"),
        companions=(
            _rel("stranger", "碰瓷男子", "spk_faker"),
            _rel("officer", "交警", "spk_traffic_police"),
            _rel("coworker", "对班司机老赵", "spk_driver_zhao"),
            _rel("spouse", "老婆", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D31",
        tag="D31_住家保姆_47岁_噎食急救与工资纠纷",
        label="47岁住家保姆",
        age=47,
        gender="f",
        dialect="henan",
        region="henan",
        occupation="城市住家保姆（照护失能老人）",
        life_stage="老人呛咳噎食惊险抢救，雇主拖延工资，春节返乡票难求",
        threads=("老人噎食急救", "工资纠纷", "返乡车票", "自家孩子学费"),
        conditions=("高血压", "静脉曲张", "肩周炎"),
        home_scene="雇主家保姆间",
        work_scene="雇主家客厅与医院急诊",
        apps=("WeChat", "支付宝", "12306", "抖音", "银行"),
        companions=(
            _rel("employer", "雇主李女士", "spk_employer_li"),
            _rel("elder", "失能老人", "spk_elder"),
            _rel("doctor", "急诊医生", "spk_doctor_er"),
            _rel("child", "儿子", "spk_child_son"),
        ),
    ),
    Persona(
        pid="D32",
        tag="D32_国企中层_49岁_配合调查与血压飙升",
        label="49岁国企中层干部",
        age=49,
        gender="m",
        dialect="dongbei",
        region="dongbei",
        occupation="国有能源企业中层干部",
        life_stage="被要求配合专项调查，家庭信任出现裂痕，血压飙升至 180/110",
        threads=("配合专项调查", "家庭信任裂痕", "高血压危象", "账户流水核查"),
        conditions=("高血压二级", "脂肪肝", "焦虑状态"),
        home_scene="单位家属院",
        work_scene="纪委谈话室与办公楼",
        apps=("WeChat", "企业OA", "工商银行", "支付宝", "政务平台"),
        companions=(
            _rel("boss", "集团纪委老王", "spk_discipline_wang"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
            _rel("lawyer", "律师", "spk_lawyer_criminal"),
            _rel("coworker", "同事老赵", "spk_coworker_zhao"),
        ),
    ),
    Persona(
        pid="D33",
        tag="D33_环卫工人_52岁_高温中暑与剐蹭索赔",
        label="52岁环卫工人",
        age=52,
        gender="f",
        dialect="henan",
        region="henan",
        occupation="市政环卫保洁员",
        life_stage="高温橙色预警下连续作业中暑，被电动车剐蹭索赔无果，儿子彩礼催钱",
        threads=("高温中暑", "剐蹭索赔", "儿子彩礼", "社保补缴"),
        conditions=("热衰竭史", "膝关节骨性关节炎", "高血压"),
        home_scene="城中村出租屋",
        work_scene="主干道清扫段与环卫驿站",
        apps=("WeChat", "支付宝", "拼多多", "抖音", "银行"),
        companions=(
            _rel("boss", "环卫班长", "spk_sanitation_foreman"),
            _rel("stranger", "肇事电动车骑手", "spk_scooter_rider"),
            _rel("child", "儿子", "spk_child_son"),
            _rel("doctor", "急诊医生", "spk_doctor_er"),
        ),
    ),
    Persona(
        pid="D34",
        tag="D34_民营医院院长_54岁_医保飞检与术后复查",
        label="54岁民营医院院长",
        age=54,
        gender="m",
        dialect="wuhan",
        region="wuhan",
        occupation="民营专科医院院长",
        life_stage="医保飞行检查进驻，一起手术并发症索赔升级，自身胃癌术后复查异常",
        threads=("医保飞检", "医疗事故索赔", "胃癌术后复查", "股东撤资"),
        conditions=("胃癌术后", "反流性食管炎", "焦虑状态"),
        home_scene="医院旁自购房",
        work_scene="院长办公室与检查接待室",
        apps=("WeChat", "医院HIS", "企业微信", "工商银行", "12345"),
        companions=(
            _rel("officer", "医保飞检组组长", "spk_insurance_inspector"),
            _rel("lawyer", "医院法律顾问", "spk_hospital_lawyer"),
            _rel("doctor", "肿瘤科主任", "spk_doctor_oncology"),
            _rel("partner", "股东老周", "spk_shareholder_zhou"),
        ),
    ),
    Persona(
        pid="D35",
        tag="D35_乡镇养殖户_56岁_猪瘟扑杀与饲料欠款",
        label="56岁乡镇生猪养殖户",
        age=56,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="生猪养殖户（年出栏 800 头）",
        life_stage="周边疫情导致扑杀补贴争议，饲料商堵门要账，修猪舍时摔伤腰椎",
        threads=("扑杀补贴争议", "饲料欠款", "腰椎压缩性骨折", "环保整改"),
        conditions=("腰椎压缩性骨折恢复期", "慢性支气管炎", "高血压"),
        home_scene="猪场旁的自家院子",
        work_scene="猪舍与镇上兽药店",
        apps=("WeChat", "支付宝", "牧原e家", "银行", "快手"),
        companions=(
            _rel("officer", "镇畜牧站站长", "spk_animal_station"),
            _rel("supplier", "饲料商老尹", "spk_feed_supplier_yin"),
            _rel("spouse", "老伴", "spk_spouse_wife"),
            _rel("doctor", "县医院骨科医生", "spk_doctor_county_bone"),
        ),
    ),
    Persona(
        pid="D36",
        tag="D36_返聘高校教授_58岁_经费审计与老伴透析",
        label="58岁返聘高校教授",
        age=58,
        gender="m",
        dialect="shaanxi",
        region="shaanxi",
        occupation="高校返聘教授（在研国家课题）",
        life_stage="科研经费专项审计，学生论文造假被举报，老伴每周三次透析需陪护",
        threads=("科研经费审计", "学生论文造假举报", "老伴透析陪护", "课题结题压力"),
        conditions=("高血压", "颈椎病", "白内障早期"),
        home_scene="高校家属区",
        work_scene="实验室与审计接待室",
        apps=("WeChat", "科研管理平台", "支付宝", "银行", "学术会议"),
        companions=(
            _rel("officer", "审计处老方", "spk_auditor_fang"),
            _rel("student", "博士生小邹", "spk_student_zou"),
            _rel("spouse", "老伴", "spk_spouse_wife"),
            _rel("doctor", "肾内科医生", "spk_doctor_nephrology"),
        ),
    ),
    Persona(
        pid="D37",
        tag="D37_上市公司董事长_61岁_心梗支架与股权质押爆仓",
        label="61岁上市公司董事长",
        age=61,
        gender="m",
        dialect="cantonese",
        region="guangzhou",
        occupation="上市公司董事长（家族企业）",
        life_stage="路演途中突发胸痛植入支架，二代接班内斗，股权质押触及平仓线",
        threads=("路演途中急性心梗", "二代接班内斗", "股权质押爆仓", "供应链断供"),
        conditions=("冠心病（支架术后）", "2 型糖尿病", "高血脂"),
        home_scene="珠江新城大平层",
        work_scene="董事会会议室与医院CCU",
        apps=("WeChat", "企业微信", "券商APP", "私人银行", "邮件"),
        companions=(
            _rel("child", "大儿子", "spk_child_son_elder"),
            _rel("boss", "总裁老麦", "spk_president_mai"),
            _rel("doctor", "心内科主任", "spk_doctor_cardiology"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D38",
        tag="D38_广场舞队长_63岁_跟腱断裂与保健品投资",
        label="63岁广场舞队长（退休护士）",
        age=63,
        gender="f",
        dialect="shanghai",
        region="shanghai",
        occupation="退休护士，社区广场舞队长",
        life_stage="排练劈叉致跟腱断裂，邻里噪音诉讼缠身，养老钱被保健品投资项目套住",
        threads=("跟腱断裂", "噪音诉讼", "保健品投资骗局", "老姐妹内部矛盾"),
        conditions=("跟腱断裂恢复期", "骨关节炎", "高血压"),
        home_scene="内环老小区六楼",
        work_scene="社区广场与康复科",
        apps=("WeChat", "美篇", "支付宝", "小红书", "银行"),
        companions=(
            _rel("neighbor", "投诉邻居", "spk_neighbor_complaint"),
            _rel("doctor", "骨科医生", "spk_doctor_bone"),
            _rel("friend", "舞队姐妹王姨", "spk_friend_wang"),
            _rel("stranger", "理财推销员", "spk_financial_salesman"),
        ),
    ),
    Persona(
        pid="D39",
        tag="D39_糖尿病足患者_66岁_足溃疡与房产争夺",
        label="66岁糖尿病并发症患者",
        age=66,
        gender="m",
        dialect="dongbei",
        region="dongbei",
        occupation="退休机械厂工人",
        life_stage="糖尿病足溃疡面临截趾风险，胰岛素冷链断供，两个子女为老房子产权争执",
        threads=("糖尿病足溃疡", "胰岛素断供", "子女房产争夺", "血糖失控"),
        conditions=("2 型糖尿病伴足溃疡", "周围神经病变", "视网膜病变"),
        home_scene="厂区家属楼三楼",
        work_scene="内分泌科门诊与家中换药角",
        apps=("WeChat", "国家医保服务平台", "支付宝", "拼多多", "银行"),
        companions=(
            _rel("child", "大女儿", "spk_child_daughter_elder"),
            _rel("child", "小儿子", "spk_child_son_younger"),
            _rel("doctor", "内分泌科医生", "spk_doctor_endocrine"),
            _rel("spouse", "老伴", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D40",
        tag="D40_小区门卫_68岁_夜巡摔伤与社保补缴",
        label="68岁小区夜班门卫（环卫退休再就业）",
        age=68,
        gender="m",
        dialect="henan",
        region="henan",
        occupation="小区物业夜班门卫",
        life_stage="凌晨巡逻抓盗窃嫌疑人时摔伤，社保补缴缺档，业主投诉停车纠纷",
        threads=("夜巡摔伤", "社保补缴缺档", "停车纠纷投诉", "老伴药费"),
        conditions=("高血压", "前列腺增生", "右肩陈旧性损伤"),
        home_scene="小区门卫室与老家属楼",
        work_scene="小区地库与岗亭",
        apps=("WeChat", "支付宝", "拼多多", "社保APP", "银行"),
        companions=(
            _rel("boss", "物业经理", "spk_property_manager"),
            _rel("coworker", "同班保安", "spk_guard_colleague"),
            _rel("spouse", "老伴", "spk_spouse_wife"),
            _rel("officer", "社区民警", "spk_community_police"),
        ),
    ),
    Persona(
        pid="D41",
        tag="D41_胃癌术后老人_71岁_化疗副作用与陪护推诿",
        label="71岁胃癌术后老人",
        age=71,
        gender="m",
        dialect="shandong",
        region="shandong",
        occupation="退休供销社会计",
        life_stage="术后第三个化疗周期副作用剧烈，三个子女为陪护排班互相推诿，遗嘱需要修改",
        threads=("化疗副作用", "子女陪护推诿", "遗嘱修改", "营养摄入不足"),
        conditions=("胃癌术后化疗期", "骨髓抑制", "轻度贫血"),
        home_scene="县城自建房",
        work_scene="肿瘤科日间病房与家中餐桌",
        apps=("WeChat", "国家医保服务平台", "支付宝", "银行", "挂号平台"),
        companions=(
            _rel("child", "大儿子", "spk_child_son_elder"),
            _rel("child", "二女儿", "spk_child_daughter_middle"),
            _rel("doctor", "肿瘤科医生", "spk_doctor_oncology"),
            _rel("lawyer", "公证员", "spk_notary"),
        ),
    ),
    Persona(
        pid="D42",
        tag="D42_老渔民_74岁_出海遇险与渔业补贴",
        label="74岁老渔民（休渔期修补渔船）",
        age=74,
        gender="m",
        dialect="minnan",
        region="minnan",
        occupation="近海渔船船主",
        life_stage="出海遇大风浪被困锚地，渔业油补发放争议，长期机舱噪声致听力受损",
        threads=("出海遇险", "渔业油补争议", "听力受损", "腿部旧伤复发"),
        conditions=("老年性耳聋", "下肢静脉血栓史", "高血压"),
        home_scene="渔村石厝老宅",
        work_scene="渔港码头与近海锚地",
        apps=("WeChat", "渔港通", "支付宝", "船讯网", "银行"),
        companions=(
            _rel("coworker", "船上老伙计阿水", "spk_fisherman_shui"),
            _rel("officer", "渔政站工作人员", "spk_fishery_officer"),
            _rel("child", "儿子", "spk_child_son"),
            _rel("doctor", "耳鼻喉科医生", "spk_doctor_ent"),
        ),
    ),
    Persona(
        pid="D43",
        tag="D43_退役老兵_76岁_荣誉认购骗局与白内障手术",
        label="76岁退役老兵",
        age=76,
        gender="m",
        dialect="shaanxi",
        region="shaanxi",
        occupation="退休老兵（日常在干休所活动）",
        life_stage="被『荣誉勋章认购』骗局卷走积蓄，白内障手术排期，养老院护理员态度恶劣",
        threads=("荣誉诈骗", "白内障手术", "养老院虐老投诉", "子女远在外地"),
        conditions=("老年性白内障", "高血压", "听力下降"),
        home_scene="干休所与养老院房间",
        work_scene="干休所活动室与眼科门诊",
        apps=("WeChat", "退役军人服务平台", "支付宝", "银行", "抖音"),
        companions=(
            _rel("stranger", "诈骗团伙推销员", "spk_scammer"),
            _rel("doctor", "眼科医生", "spk_doctor_ophthalmology"),
            _rel("child", "女儿", "spk_child_daughter"),
            _rel("coworker", "老战友李老", "spk_veteran_li"),
        ),
    ),
    Persona(
        pid="D44",
        tag="D44_退休会计_79岁_高息理财爆雷与记账异常",
        label="79岁退休会计（轻度认知减退）",
        age=79,
        gender="f",
        dialect="shanghai",
        region="shanghai",
        occupation="退休会计",
        life_stage="高息理财平台爆雷损失养老钱，记账出现重复与遗漏，家中暖气管道漏水",
        threads=("高息理财爆雷", "记账异常", "暖气管道漏水", "保姆频繁更换"),
        conditions=("轻度认知减退", "骨关节炎", "高血压"),
        home_scene="老式两居室",
        work_scene="社区理财讲座与家中账本",
        apps=("WeChat", "支付宝", "银行", "拼多多", "理财平台"),
        companions=(
            _rel("child", "儿子", "spk_child_son"),
            _rel("nanny", "钟点工阿姨", "spk_cleaner"),
            _rel("neighbor", "邻居老张", "spk_neighbor_zhang"),
            _rel("stranger", "理财客户经理", "spk_wealth_manager"),
        ),
    ),
    Persona(
        pid="D45",
        tag="D45_双耳失聪老人_82岁_助听器纠纷与分家",
        label="82岁双耳极重度听障老人",
        age=82,
        gender="m",
        dialect="sichuan",
        region="chengdu",
        occupation="退休铁路工人",
        life_stage="助听器验配纠纷维权，长子幼子为分家协议争执，夜间如厕跌倒髋部疼痛",
        threads=("助听器验配纠纷", "分家协议争执", "跌倒髋部疼痛", "听力沟通障碍"),
        conditions=("双耳极重度听障", "骨质疏松", "冠心病"),
        home_scene="铁路家属区一楼",
        work_scene="助听器门店与家中客厅",
        apps=("WeChat（文字）", "支付宝", "银行", "拼多多", "残联服务"),
        companions=(
            _rel("child", "长子", "spk_child_son_elder"),
            _rel("child", "幼子", "spk_child_son_younger"),
            _rel("stranger", "助听器销售", "spk_hearing_aid_sales"),
            _rel("doctor", "骨科医生", "spk_doctor_bone"),
        ),
    ),
    Persona(
        pid="D46",
        tag="D46_子女海外独居老人_85岁_肠梗阻急诊",
        label="85岁子女定居海外的独居老人",
        age=85,
        gender="f",
        dialect="cantonese",
        region="guangzhou",
        occupation="退休中学英语教师",
        life_stage="深夜腹痛呕吐疑肠梗阻，越洋电话时差联系不上子女，遗产公证尚未完成",
        threads=("肠梗阻急诊", "越洋时差联系", "遗产公证", "独居照护缺口"),
        conditions=("高血压", "慢性便秘", "轻度心衰"),
        home_scene="越秀区老房",
        work_scene="急诊留观室与家中卧室",
        apps=("WeChat", "FaceTime", "支付宝", "银行", "海外挂号协助"),
        companions=(
            _rel("child", "女儿（在加拿大）", "spk_child_daughter_overseas"),
            _rel("neighbor", "楼下陈姨", "spk_neighbor_chen"),
            _rel("doctor", "急诊外科医生", "spk_doctor_er_surgery"),
            _rel("lawyer", "公证处人员", "spk_notary"),
        ),
    ),
    Persona(
        pid="D47",
        tag="D47_临终关怀患者_88岁_止痛剂量与后事交代",
        label="88岁安宁疗护患者",
        age=88,
        gender="m",
        dialect="tianjin",
        region="tianjin",
        occupation="退休大学图书管理员",
        life_stage="安宁疗护病房，止痛药剂量争议，趁清醒交代后事与账户密码",
        threads=("止痛药剂量争议", "后事交代", "家属情绪失控", "呼吸困难"),
        conditions=("晚期肺癌伴骨转移", "慢性疼痛", "营养不良"),
        home_scene="安宁疗护病房与家中老书桌",
        work_scene="病房窗边",
        apps=("WeChat", "银行", "支付宝", "电子遗嘱", "医院HIS"),
        companions=(
            _rel("spouse", "老伴", "spk_spouse_wife"),
            _rel("child", "儿子", "spk_child_son"),
            _rel("doctor", "安宁疗护医生", "spk_doctor_hospice"),
            _rel("nurse", "责任护士", "spk_nurse_primary"),
        ),
    ),
    Persona(
        pid="D48",
        tag="D48_四世同堂老人_90岁_压疮护理与拆迁签字",
        label="90岁四世同堂老人",
        age=90,
        gender="f",
        dialect="henan",
        region="henan",
        occupation="农村高龄老人（四世同堂）",
        life_stage="长期卧床骶尾部压疮，儿孙为老宅拆迁补偿签字争执不下，护理人手不足",
        threads=("压疮护理", "拆迁补偿签字争执", "卧床肺部感染风险", "家族赡养分摊"),
        conditions=("骶尾部 2 期压疮", "坠积性肺炎风险", "高血压"),
        home_scene="农村老宅正屋",
        work_scene="堂屋与县医院换药室",
        apps=("微信（家人代操作）", "支付宝", "银行", "村委会通知", "医保平台"),
        companions=(
            _rel("child", "大儿子", "spk_child_son_elder"),
            _rel("child", "二儿媳", "spk_daughter_in_law"),
            _rel("officer", "村委会主任", "spk_village_head"),
            _rel("doctor", "换药室护士", "spk_nurse_dressing"),
        ),
    ),
    Persona(
        pid="D49",
        tag="D49_海外华人工程师_34岁_跨洋时差与身份续签",
        label="34岁海外华人芯片验证工程师",
        age=34,
        gender="m",
        dialect="overseas",
        region="overseas",
        occupation="海外芯片验证工程师",
        life_stage="项目冻结面临裁员与工作签证续签死线，母亲在国内突发脑梗需要远程决策",
        threads=("裁员与签证死线", "母亲脑梗远程决策", "跨洋时差疲劳", "跨境汇款延迟"),
        conditions=("慢性失眠", "颈椎病", "焦虑状态"),
        home_scene="一居室公寓",
        work_scene="实验室与跨洋视频会议",
        apps=("WeChat", "Teams", "PayPal", "招商银行", "领英"),
        companions=(
            _rel("boss", "直属经理 David", "spk_manager_david"),
            _rel("parent", "我妈", "spk_parent_mother"),
            _rel("doctor", "主治医生", "spk_doctor_attending"),
            _rel("spouse", "妻子", "spk_spouse_wife"),
        ),
    ),
    Persona(
        pid="D50",
        tag="D50_高原牧区阿妈_52岁_雪灾失联与畜群损失",
        label="52岁高原牧区阿妈（普通话说得吃力）",
        age=52,
        gender="f",
        dialect="overseas",
        region="tibet_plateau",
        occupation="高原牧区牧民",
        life_stage="暴雪封路断网三天，帐篷被压塌，羊群大面积冻损，需向乡政府报灾",
        threads=("雪灾封路失联", "羊群冻损", "帐篷压塌", "降压药断了"),
        conditions=("高原性高血压", "风湿性关节痛", "白内障早期"),
        home_scene="牧区帐篷与冬窝子",
        work_scene="草场与乡政府救灾点",
        apps=("微信语音", "支付宝", "乡村广播", "银行", "抖音"),
        companions=(
            _rel("child", "女儿卓玛", "spk_child_drolma"),
            _rel("officer", "驻村工作队", "spk_township_worker"),
            _rel("neighbor", "邻居牧户", "spk_herder_neighbor"),
            _rel("doctor", "巡回医疗队医生", "spk_doctor_mobile"),
        ),
    ),
)


# --------------------------------------------------------------------------------------
# 维度五之一：真实方言与口语俚语库（按"语用功能"取值，供事件族拼装关键原话）
# --------------------------------------------------------------------------------------
DIALECT_PACKS: Dict[str, Dict[str, object]] = {
    "henan": {
        "name": "河南话",
        "particles": ("呗", "哩", "咧", "嗳", "中不中"),
        "vocatives": ("娃儿", "老师儿", "哥", "婶儿", "老表"),
        "money": (
            "这钱你再拖下去可就不中咧，俺家里也等着用哩",
            "上回说好咧月底给俺结，咋又变卦了嗳",
            "甭跟俺绕圈子，把钱给俺算清咧就中",
        ),
        "threat": (
            "你要是再耍赖，俺就去劳动监察大队告你去，中不中",
            "咱把丑话说前头，下礼拜三之前见不着钱，俺就带人堵你门口咧",
            "别怪俺不给你留脸面，这事儿俺们到明面上说理去",
        ),
        "pain": (
            "哎哟喂，这脚疼得俺直冒汗，走路都成问题咧",
            "俺这心口窝憋得慌，喘气都费劲，你别不当回事儿",
            "头晕得厉害，眼前一黑差一点就栽那儿咧",
        ),
        "plead": (
            "俺求你了，先给俺垫上这几百块钱药费中不中",
            "叔，恁可千万替俺把那单子留着，俺明天一早就过去",
            "帮俺盯着点老人，俺这边真是脱不开身咧",
        ),
        "rebut": (
            "你说得轻巧，俺又不欠你的，凭啥让俺认这事儿",
            "这话俺可不认，账目得一笔一笔跟俺对清楚",
            "甭拿那些虚头巴脑的话糊弄俺，俺要的是个实在说法",
        ),
        "irony": (
            "行啊你可真守信用，说好今天还钱连人影都见不着，电话还拉黑",
            "恁可真是个大忙人，俺找恁八趟了都见不着个人",
            "怪好哩，出了事全成俺一个人的责任了呗",
        ),
        "boast": (
            "明儿个老子就把那栋楼买下来给弟兄们分了",
            "这点钱算个啥，哥一出面啥事都能摆平",
            "等俺这单成了，请恁们全村人去县城吃席",
        ),
        "warm": (
            "天冷了多穿点，别硬撑着，有啥事儿给家里打电话",
            "你先吃口热的，事儿咱慢慢说，别急出毛病来",
            "中，俺记下了，你放心去忙你的吧",
        ),
    },
    "sichuan": {
        "name": "四川话",
        "particles": ("嘛", "哈", "哦", "噻", "晓得不"),
        "vocatives": ("娃儿", "老汉", "幺儿", "妹儿", "哥子"),
        "money": (
            "那笔钱好久结给我嘛，硬是拖不得了哦",
            "哥子，工钱的事你给个准信噻，屋头等着这笔钱过年",
            "硬是背时，屋头借的一万块钱硬是遭拐子卷跑了",
        ),
        "threat": (
            "你莫跟我装糊涂哈，再不拿钱我就去住建局告你",
            "三十号兄弟的血汗钱，下周五要是打不进卡里，咱们住建局见",
            "话我给你摆到这儿，再拖我就带人堵项目部大门了哦",
        ),
        "pain": (
            "嘶……疼死我了，这脚趾头肿得像馒头，火烧一样",
            "心口翳住翳住好似有块石头压到，走两步就喘",
            "脑壳昏得很，眼睛看东西都在打转转",
        ),
        "plead": (
            "医生，麻烦你给看仔细点嘛，我实在扛不住了",
            "帮我把这批货先垫到嘛，我下个月一定补齐",
            "老哥，帮我盯一下工地，我腿杆实在下不了地",
        ),
        "rebut": (
            "你莫乱说哦，账本是白纸黑字写起的",
            "这个责我不认，明明是你们总包方先撕的合同",
            "少来这套哈，我不得吃这个哑巴亏",
        ),
        "irony": (
            "可以哦，说好的三天结款，硬是拖了三个月，你说话算话得很噻",
            "好嘛，出事就都是我一个人的责任，你们一个个都干干净净的",
            "要得噻，你们领导忙得很，我们这些下力气的算个啥子嘛",
        ),
        "boast": (
            "等老子这个工程款下来，直接把那层楼买到",
            "这点小事算个啥子，哥子出马分分钟给你摆平",
            "明天老子去香港把那栋楼全买下来给弟兄们分了",
        ),
        "warm": (
            "你各人注意身体哈，有啥子事给我打电话",
            "先喝口热水，慢慢说，莫着急上火",
            "要得，我记到了，你各人路上小心点",
        ),
    },
    "dongbei": {
        "name": "东北话",
        "particles": ("呗", "哈", "呐", "嘞", "咋的"),
        "vocatives": ("老铁", "哥们儿", "姐", "大哥", "老弟"),
        "money": (
            "那八万块料钱啥时候给结啊，我这都垫了两月了",
            "别搁这儿跟我扯犊子，钱啥时候到账给个准话",
            "哥们儿，我这边真揭不开锅了，你先给我匀点呗",
        ),
        "threat": (
            "别搁这儿跟我扯犊子，下礼拜三前把那八万块料钱结了，不然厂子给你扬了",
            "你再赖账咱就上劳动仲裁，我不跟你玩虚的",
            "丑话说前头，钱不到账，明天我就带人上你单位门口蹲着",
        ),
        "pain": (
            "哎呀妈呀，这腰疼得跟断了似的，起都起不来",
            "胸口这儿闷得慌，喘不上来气儿，你赶紧的",
            "脑袋嗡嗡的，眼前直冒金星",
        ),
        "plead": (
            "老铁，你先帮我垫上这回，回头我肯定还你",
            "哥，帮我看两眼老人呗，我实在腾不出人",
            "求你了，先给我开点药，我兜里钱不太够",
        ),
        "rebut": (
            "这话我可就不爱听了，我哪点儿对不起你们了",
            "别整那些虚的，账咱们一笔一笔掰扯清楚",
            "你说啥呢，合同上白纸黑字写着，你咋就装看不见呢",
        ),
        "irony": (
            "行啊你可太讲究了，说好今天还钱连人影都找不着",
            "哥们儿你真够意思，出事儿了就我一个人扛着呗",
            "得嘞，你们都是大忙人，就我是闲人对吧",
        ),
        "boast": (
            "这点钱算啥呀，哥随便一出手就给你摆平了",
            "等我这单拿下，请你们全屯子人上城里吃大席",
            "明儿个老子就把那栋楼给包圆了，分给弟兄们",
        ),
        "warm": (
            "注意身体啊，天冷加件衣裳，别冻着",
            "先吃口热乎的，事儿慢慢捋，别上火了",
            "行，我记下了，你放心忙你的去吧",
        ),
    },
    "shaanxi": {
        "name": "陕西话",
        "particles": ("额", "咧", "嘛", "么", "咋"),
        "vocatives": ("娃", "老哥", "婶", "咱", "乡党"),
        "money": (
            "把屋里那两亩果园协议拿出来，甭跟额装糊涂",
            "那笔赔偿款啥时候到咧，额家里等着急用哩",
            "乡党，先给额把料钱结了么，额实在垫不下咧",
        ),
        "threat": (
            "你再拖，额就上法院告你去咧，咱把话摆到桌面上",
            "甭逼额叫人来堵门，到时候脸上都不好看",
            "这事没完，额非得讨个说法不成",
        ),
        "pain": (
            "额这胸口闷得慌，跟压了块石头似的",
            "腰疼得直不起来咧，动一下就钻心",
            "头咋这么晕呢，眼前黑一下黑一下的",
        ),
        "plead": (
            "老哥，帮额把这一关过了，额记你一辈子好",
            "先给额把药开上么，钱额明天送来",
            "你帮额盯住老人，额赶紧往回赶",
        ),
        "rebut": (
            "你甭跟额胡扯，账目额这儿记得清清楚楚",
            "这话额不认，明明是你违约在先",
            "少来这套，额不吃你这哑巴亏",
        ),
        "irony": (
            "好得很么，说好一个月结账，现在都仨月了",
            "你可真是讲信用，电话都不接咧",
            "行咧，出事全怪额一个人，你们都是清白的",
        ),
        "boast": (
            "这点事算啥么，额一个电话就摆平咧",
            "等额这工程款下来，直接把这栋楼买到",
            "明天额去城里把那片儿全包咧，给咱乡党分",
        ),
        "warm": (
            "你注意身子骨么，有啥事就给额打电话",
            "先喝口热水，慢慢说，甭急",
            "好咧，额记住咧，你忙你的去",
        ),
    },
    "shanghai": {
        "name": "上海话",
        "particles": ("呀", "啦", "哦", "伐", "嘞"),
        "vocatives": ("阿叔", "阿姐", "小囡", "阿姨", "先生"),
        "money": (
            "侬讲好的铜钿啥辰光还啦，阿拉等仔急煞了",
            "阿姐，数目要核对清爽哦，一分也不能差",
            "借的钞票到期了呀，侬总要给阿拉一个说法",
        ),
        "threat": (
            "侬不要面孔，阿拉小囡结婚的房子产权侬凭啥加名字",
            "再拖下去我就去法院起诉，大家面上都不好看",
            "侬当心点，这桩事体阿拉是要追究到底的",
        ),
        "pain": (
            "心口翳住翳住好似俾旧石压住，行两步都喘晒气",
            "阿叔今次真系大镬，头晕得厉害，眼睛都花了",
            "这只脚肿得像馒头，碰一碰就疼得跳起来",
        ),
        "plead": (
            "医生，侬帮阿拉仔细看看呀，实在熬不牢了",
            "先帮阿拉垫一垫好伐，下个月一定还侬",
            "侬帮阿拉看牢老太太，阿拉马上赶过来",
        ),
        "rebut": (
            "侬讲这话就没道理嘞，账本记得清清爽爽",
            "这个责任阿拉不认的，是侬先违约的呀",
            "少来这一套，阿拉不吃这个亏的",
        ),
        "irony": (
            "侬倒蛮讲信用的，讲好今朝还钞票，人影也看勿到",
            "好嘞，出了事体就阿拉一个人负责，侬倒清清爽爽",
            "侬真是大忙人，阿拉寻侬十趟也寻勿着",
        ),
        "boast": (
            "这点钞票算啥，阿拉随便动动手指头就搞定",
            "等这单生意落地，请大家一道去吃饭",
            "明朝阿拉就去把那栋楼买下来，分把弟兄们",
        ),
        "warm": (
            "侬自家当心身体，有事体就打阿拉电话",
            "先吃口热的，事体慢慢讲，勿要急",
            "好嘞，阿拉记牢了，侬忙侬的",
        ),
    },
    "cantonese": {
        "name": "粤语",
        "particles": ("啦", "嘅", "㗎", "咩", "囉"),
        "vocatives": ("阿叔", "阿伯", "细佬", "靓女", "老板"),
        "money": (
            "笔钱几时找数呀，我哋都等咗成个月啦",
            "老细，尾款唔好再拖喇，伙记都要出粮㗎",
            "讲好嘅数就照数畀，唔好又话资金紧",
        ),
        "threat": (
            "你再唔畀钱，我就去劳动局告你，唔怕同你拉硬弓",
            "讲清楚啲，下礼拜三之前唔到账，我哋就上你门口",
            "唔好逼我真系同你揾律师，大家面阻阻都唔好",
        ),
        "pain": (
            "阿叔今次真系大镬，心口翳住翳住好似俾旧石压住，行两步都喘晒气",
            "个头好晕呀，眼前一黑，差啲企唔稳",
            "只脚肿到似个包咁，掂一掂都痛到飙泪",
        ),
        "plead": (
            "医生唔该你帮我睇真啲，我真系顶唔顺啦",
            "细佬帮我顶住呢几日，钱我月尾一定还你",
            "帮我睇住阿妈呀，我即刻返嚟",
        ),
        "rebut": (
            "你咁讲就唔啱喇，啲数我簿记到清清楚楚",
            "呢个镬我唔认㗎，系你哋先撕合约嘅",
            "唔好同我讲呢啲，我唔食呢个哑巴亏",
        ),
        "irony": (
            "你几时都咁守信嘅，讲好今日还钱，人影都唔见",
            "好嘢，出咗事就我一个人孭飞，你哋个个都干净",
            "你真系大忙人，我揾你十次都揾唔到",
        ),
        "boast": (
            "呢啲钱算咩呀，我随手一搞就搞掂",
            "等我单嘢落地，请晒弟兄食大餐",
            "听日我去香港将嗰栋楼买晒，分畀啲兄弟",
        ),
        "warm": (
            "你自己小心身体，有事就打畀我",
            "饮啖热水先啦，慢慢讲，唔好心急",
            "好，我记住咗，你忙你嘅啦",
        ),
    },
    "shandong": {
        "name": "山东话",
        "particles": ("呗", "咧", "嘞", "哈", "杠"),
        "vocatives": ("老师儿", "伙计", "嫂子", "大哥", "小嫚"),
        "money": (
            "那笔账啥时候结咧，俺这边等着急用",
            "老哥，先把料钱给俺清了呗，拖得实在不像话",
            "咱把账目对对，差多少补多少，别含糊",
        ),
        "threat": (
            "你再拖俺就去法院起诉，咱明明白白说理去",
            "别逼俺叫人来堵门，到时候脸上都挂不住",
            "话说到前头，下周三之前钱不到账，俺就去投诉",
        ),
        "pain": (
            "哎哟，这腰疼得俺直不起腰来，动一下就钻心",
            "胸口这儿杠闷得慌，气都喘不匀溜",
            "头晕得厉害，眼前一黑一黑的",
        ),
        "plead": (
            "老哥，先借俺点钱垫上，俺下月发工资就还",
            "帮俺照看照看老人呗，俺这边实在走不开",
            "求你了，先给俺开点药，钱明天送来",
        ),
        "rebut": (
            "这话俺可不认，账上写得清清楚楚",
            "别整那些虚的，白纸黑字的合同你能看不见",
            "俺不吃这个哑巴亏，该谁的责任就是谁的",
        ),
        "irony": (
            "行啊你真守信用，说好今天还钱连人影都见不着，电话还拉黑",
            "你可真够意思，出了事先把俺推出来顶着",
            "好，你们都是大忙人，就俺闲得慌",
        ),
        "boast": (
            "这点钱算啥，俺一个电话就解决咧",
            "等俺这单干成，请大家上城里吃大席",
            "明天老子就把那栋楼买下来给弟兄们分了",
        ),
        "warm": (
            "天冷了多穿点，别硬扛着，有事打电话",
            "先吃口热乎的，事儿慢慢说，别上火",
            "行，俺记下了，你放心忙你的",
        ),
    },
    "hubei": {
        "name": "湖北/武汉话",
        "particles": ("撒", "嘞", "哦", "咧", "蛮"),
        "vocatives": ("伢", "师傅", "太（奶奶）", "拐子（哥哥）", "嫂子"),
        "money": (
            "那笔钱么时候结撒，我这边等得蛮着急",
            "老板，尾款拖不得咧，工人都要发工资",
            "账要算清白，一分一厘都莫想含糊过去",
        ),
        "threat": (
            "再拖我就找劳动监察咧，莫以为我是吓你",
            "话说到这儿，再不给钱我就堵你办公室门口",
            "莫跟我扯野棉花，钱不到账我们法庭上见",
        ),
        "pain": (
            "哎哟，这腿疼得像针扎一样，站都站不稳",
            "胸口蛮闷，喘气都不匀勺，快帮我打120",
            "脑壳昏得很，眼睛发花，站不住咧",
        ),
        "plead": (
            "师傅，麻烦你先帮我垫一下，我明天就还",
            "帮我照看一下屋里老人撒，我实在脱不开身",
            "医生，你帮我仔细看看，我确实扛不住了咧",
        ),
        "rebut": (
            "你莫瞎说，账本上记得一清二楚",
            "这个责我不认咧，是你们先违约的",
            "莫来这一套，我不吃这个哑巴亏",
        ),
        "irony": (
            "可以咧，说好三天结账，硬是拖了三个月",
            "你蛮守信用咧，说好今天还钱连人都冇得",
            "行撒，出了事都是我一个人的错，你们都清白",
        ),
        "boast": (
            "这点钱算么事撒，我一个电话就摆平",
            "等我工程款下来，那栋楼我直接买",
            "明天老子去香港把那栋楼全买下来给弟兄们分了",
        ),
        "warm": (
            "你自己注意身体咧，有事就打电话我",
            "先喝口热水，慢慢说，莫急",
            "好咧，我记下了，你忙你的",
        ),
    },
    "hunan": {
        "name": "湖南话",
        "particles": ("咯", "嘞", "哒", "嗦", "咧"),
        "vocatives": ("伢子", "老板", "娭毑", "老倌子", "妹陀"),
        "money": (
            "那笔钱几时结咯，我这里真的等不起哒",
            "老板，尾款莫拖了嘞，工人都要靠它过年",
            "账要一是一二是二，莫跟我打马虎眼",
        ),
        "threat": (
            "再拖我就去投诉你，莫怪我不讲情面",
            "钱不到账，明天我就带人堵你店门口咯",
            "讲清楚哒，再赖账我们就法院见",
        ),
        "pain": (
            "哎哟，这脚痛得要命，走路都走不得咯",
            "胸口闷得慌，出气都出不匀嘞",
            "脑壳晕得厉害，眼前发黑哒",
        ),
        "plead": (
            "老板，先帮我垫一下咯，我明天就还你",
            "帮我照看一下老人嘞，我实在走不开",
            "医生，帮我仔细看看哒，我扛不住了",
        ),
        "rebut": (
            "你莫乱讲，账上是记得清清楚楚嘞",
            "这个责任我不认咯，是你们先违约",
            "少来这一套，我不吃这个哑巴亏哒",
        ),
        "irony": (
            "可以咯，讲好三天结账，硬是拖了三个月",
            "你蛮讲信用嘞，讲好今天还钱人影都冇得",
            "行咯，出事就都怪我，你们都清白",
        ),
        "boast": (
            "这点钱算什么咯，我一个电话就摆平",
            "等我工程款下来，那栋楼我直接买咯",
            "明天老子就把那栋楼全买下来分给弟兄们",
        ),
        "warm": (
            "你自己当心身体咯，有事就打电话",
            "先喝口热水，慢慢讲，莫急",
            "好嘞，我记住哒，你忙你的咯",
        ),
    },
    "minnan": {
        "name": "闽南话区普通话（带闽南腔）",
        "particles": ("啦", "喔", "捏", "啦", "咧"),
        "vocatives": ("阿伯", "少年家", "阿姐", "头家（老板）", "厝边（邻居）"),
        "money": (
            "这笔钱什么时候结啦，我这边等很久了喔",
            "头家，尾款不要再拖了捏，大家都要吃饭",
            "账要算清楚啦，一毛钱都不能含糊",
        ),
        "threat": (
            "再拖我就去投诉啦，不要怪我不给面子",
            "钱不到位，明天我就要去你公司门口等",
            "讲清楚喔，再赖账我们就法院见",
        ),
        "pain": (
            "哎哟，这只脚疼死了啦，站都站不住",
            "胸口闷闷的，喘气都喘不过来喔",
            "头很晕捏，眼前都黑了",
        ),
        "plead": (
            "头家，先帮我垫一下啦，我明天就还",
            "帮我照看一下厝里老人喔，我实在走不开",
            "医生，帮我仔细看看啦，我撑不住了",
        ),
        "rebut": (
            "你不要乱讲啦，账上记得清清楚楚",
            "这个责任我不认喔，是你们先违约的",
            "不要来这一套啦，我不吃这个亏",
        ),
        "irony": (
            "可以啦，说好三天结账，拖了三个月",
            "你很守信用喔，说好今天还钱连人都不见",
            "好啦，出事都怪我，你们都清白",
        ),
        "boast": (
            "这点钱算什么啦，我一个电话就解决",
            "等我这笔款下来，那栋楼我直接买",
            "明天我去香港把那栋楼全买下来分给兄弟们",
        ),
        "warm": (
            "你自己注意身体喔，有事就打电话",
            "先喝口热水，慢慢讲，不要急",
            "好，我记住了啦，你忙你的喔",
        ),
    },
    "tianjin": {
        "name": "天津话",
        "particles": ("嘛", "哏儿", "呗", "嘞", "您了"),
        "vocatives": ("大哥", "姐姐", "老几位", "师傅", "小伙子"),
        "money": (
            "那笔钱多前儿结啊，我这儿都快断了顿儿了",
            "师傅，尾款您了别拖了呗，工人都等着呢",
            "账咱得掰扯清楚，一笔是一笔",
        ),
        "threat": (
            "您了别逼我，再拖我可就上法院告去了",
            "钱不到账，明儿我就上您单位门口等着去",
            "丑话说头里，这事儿我不能这么算了",
        ),
        "pain": (
            "哎哟，这腰疼得跟折了似的，起不来床了",
            "这胸口嘛玩意儿堵得慌，喘气儿都费劲",
            "脑袋瓜子嗡嗡的，眼前直冒金光",
        ),
        "plead": (
            "大哥，您了先给我垫上，回头我准还您",
            "帮我照看照看老人呗，我实在抽不开身",
            "大夫，您了给我仔细瞧瞧，我扛不住了",
        ),
        "rebut": (
            "您了这话我可就不爱听了，账上写得明白",
            "这责任我不认，是你们先违约的",
            "少来这套，我不吃这哑巴亏",
        ),
        "irony": (
            "行啊您了真守信用，说好今天还钱，人影儿都没见着",
            "您了真够意思，出了事全我一个人担着",
            "好嘛，合着就我一个闲人，你们都忙",
        ),
        "boast": (
            "这点儿钱算嘛呀，我一个电话就摆平",
            "等我这单成了，请老几位上城里吃席去",
            "明儿个老子就把那栋楼买下来分给弟兄们",
        ),
        "warm": (
            "您了注意身体啊，有事儿给我打电话",
            "先吃口热乎的，事儿慢慢说，别上火",
            "行，我记下了，您了忙您的",
        ),
    },
    "overseas": {
        "name": "海外华语（中英夹杂）",
        "particles": ("啦", "哦", "嗯", "这样子", "然后"),
        "vocatives": ("David", "阿姨", "老板", "医生", "妈"),
        "money": (
            "这笔钱大概什么时候能转过来啦，我这边要付房租咯",
            "老板，尾款麻烦尽快安排一下哦，我现金流真的紧张",
            "账目要对清楚嗯，跨境汇款手续费也要算进去",
        ),
        "threat": (
            "如果再不解决，我就要走法律程序了",
            "合同写得很清楚，拖下去对谁都不好",
            "我这边已经联系律师了，希望不要走到那一步",
        ),
        "pain": (
            "胸口很闷，喘不太上来，走两步就要停下来",
            "脚肿得很厉害，一碰就疼得受不了",
            "头晕得厉害，眼前发黑，我得坐下",
        ),
        "plead": (
            "麻烦您先帮我垫一下，我明天就还您",
            "帮我照看一下我妈，我在这边实在赶不回去",
            "医生，麻烦您仔细看看，我真的撑不住了",
        ),
        "rebut": (
            "这个说法不对，账目我这边都有记录",
            "责任不在我，是你们先违约的",
            "不好意思，这个亏我不会吃",
        ),
        "irony": (
            "您真的很守信用，说好今天还钱，人都联系不上",
            "行啦，出了事都是我一个人的问题，你们都干净",
            "嗯，你们都忙，就我不忙",
        ),
        "boast": (
            "这点钱不算什么，我一个电话就能解决",
            "等我这个项目落地，请兄弟们吃大餐",
            "明天我就把那栋楼买下来分给大家",
        ),
        "warm": (
            "你注意身体哦，有事随时给我打电话",
            "先喝点热水，慢慢说，别急",
            "好，我记下来了，你先忙",
        ),
    },
    "plateau": {
        "name": "高原牧区汉语（说得吃力、语序朴素）",
        "particles": ("啦", "啊", "哦", "嘛", "嗯"),
        "vocatives": ("阿妈", "兄弟", "医生", "干部", "邻居"),
        "money": (
            "这个钱什么时候给，我们家里要用",
            "老板，尾款一个月了，大家要吃饭",
            "账要写清楚，我不会看汉字，要念给我听",
        ),
        "threat": (
            "再不给，我就去乡政府说这个事",
            "钱到不了，我去县里找人，不能一直等",
            "这个事我不干，我要一个说法",
        ),
        "pain": (
            "头疼得厉害，喘气很困难，胸口很闷",
            "脚肿了，走路很疼，一步也走不动",
            "头晕，看不见东西，我要坐下休息",
        ),
        "plead": (
            "帮我先垫一下药钱，过几天还给你",
            "帮我看一下阿妈，我去山上找羊",
            "医生，麻烦看清楚一点，我很难受",
        ),
        "rebut": (
            "不是这样，这个事情我没做",
            "这个钱不是我欠的，账上有名字",
            "不能这样算，我不认这个数",
        ),
        "irony": (
            "你说话很好，钱一直没有到",
            "好得很，出事就找我一个人",
            "你们都很忙，我不忙",
        ),
        "boast": (
            "这点钱不多，我卖羊就给",
            "等雪化了，我请你到家里喝茶",
            "明天我去县里，把这个事情办好",
        ),
        "warm": (
            "你身体小心，冷了穿衣服",
            "先喝热茶，慢慢说，不要急",
            "好，我记住了，你忙吧",
        ),
    },
}
DIALECT_PACKS["wuhan"] = DIALECT_PACKS["hubei"]
DIALECT_PACKS["generic"] = {
    "name": "标准普通话",
    "particles": ("啊", "吧", "呢", "的", "嘛"),
    "vocatives": ("师傅", "老板", "医生", "同志", "您"),
    "money": (
        "那笔钱什么时候结，我这边真的等不起了",
        "尾款麻烦尽快安排，大家都等着这笔钱",
        "账目要对清楚，一分一厘都不能含糊",
    ),
    "threat": (
        "再拖下去我就要走法律程序了，希望不要到那一步",
        "钱不到账，我只能带上材料去投诉了",
        "说清楚，再赖账我们就法庭上见",
    ),
    "pain": (
        "这里疼得厉害，动一下都受不了，麻烦帮我叫个车",
        "胸口闷得慌，喘不上气，赶紧送我去急诊",
        "头晕得厉害，眼前发黑，我扶一下墙",
    ),
    "plead": (
        "麻烦您先帮我垫一下，我明天就还您",
        "帮我盯一下老人，我马上赶过来",
        "医生，麻烦您看仔细一点，我实在扛不住了",
    ),
    "rebut": (
        "这话不对，账上写得清清楚楚",
        "这个责任我不认，是你们先违约的",
        "不好意思，这个亏我不会吃",
    ),
    "irony": (
        "您真守信用，说好今天还钱，人却联系不上了",
        "行，出了事都是我一个人的责任，你们都清白",
        "好，你们都忙，就我不忙",
    ),
    "boast": (
        "这点钱不算什么，我一个电话就解决",
        "等我这个项目落地，请大家吃大餐",
        "明天我就把那栋楼买下来分给大家",
    ),
    "warm": (
        "你注意身体，有事随时给我打电话",
        "先喝点热水，慢慢说，别急",
        "好，我记下来了，你先忙",
    ),
}


# --------------------------------------------------------------------------------------
# 槽位词库（人名/金额/日期/地点/物品/症状/药品）
# --------------------------------------------------------------------------------------
SURNAMES: Tuple[str, ...] = (
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周", "徐", "孙", "马", "朱", "胡",
    "郭", "林", "何", "高", "罗", "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
    "彭", "曾", "肖", "田", "董", "袁", "潘", "蒋", "蔡", "余", "杜", "叶", "程", "苏", "魏",
)

NAME_BANK: Dict[str, Tuple[str, ...]] = {
    "male": (
        "建国", "志强", "海涛", "小军", "文斌", "立新", "铁柱", "东升", "永强", "庆华",
        "长春", "大勇", "守信", "宝国", "振华", "国栋", "德胜", "金山", "秀峰", "宏斌",
        "守业", "有才", "满仓", "二奎", "老蔫", "栓柱", "来福", "狗剩", "三娃", "大成",
    ),
    "female": (
        "秀兰", "桂芳", "玉梅", "小丽", "亚楠", "春燕", "红霞", "凤英", "晓燕", "美玲",
        "秀英", "招娣", "盼娣", "金花", "春梅", "桂香", "秀珍", "慧敏", "淑华", "小娥",
        "翠萍", "志红", "月琴", "巧云", "银花", "翠兰", "文静", "雪梅", "雅琴", "小婉",
    ),
    "nick_prefix": ("老", "小", "大", "二"),
    "nick_suffix": ("哥", "姐", "叔", "姨", "师傅", "老板", "老师儿", "主任", "总", "工"),
}

AMOUNT_BANK: Tuple[Tuple[str, int], ...] = (
    ("三百八", 380), ("八百块", 800), ("一千二", 1200), ("两千五", 2500), ("三千六", 3600),
    ("五千块", 5000), ("六千八", 6800), ("八千八", 8800), ("一万二", 12000), ("一万八", 18000),
    ("两万三", 23000), ("三万五", 35000), ("四万八", 48000), ("六万六", 66000), ("八万整", 80000),
    ("十万块", 100000), ("十二万八", 128000), ("十五万", 150000), ("十八万六", 186000),
    ("二十万", 200000), ("二十六万", 260000), ("三十五万", 350000), ("四十八万", 480000),
    ("六十万", 600000), ("八十万", 800000), ("一百万", 1000000), ("两百万", 2000000),
)

DATE_BANK: Tuple[str, ...] = (
    "下周三", "下周一早上九点", "本月15号", "月底之前", "这个礼拜五", "明天上午", "后天中午前",
    "国庆节前", "过年前", "正月十六", "3月28号", "4月10号", "5月6号", "6月18号", "7月2号",
    "8月15号", "9月28号", "10月12号", "11月3号", "12月20号", "三天之内", "一周之内", "十天之内",
)

PLACE_BANK: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "henan": {
        "city": ("郑州", "洛阳", "新乡", "周口", "驻马店", "许昌"),
        "hospital": ("市人民医院急诊", "县医院骨科门诊", "省肿瘤医院", "乡镇卫生院"),
        "legal": ("区劳动监察大队", "县人民法院第三法庭", "街道司法所", "社区调解室"),
    },
    "sichuan": {
        "city": ("成都", "绵阳", "德阳", "宜宾", "南充"),
        "hospital": ("华西医院急诊", "省人民医院", "市三医院", "县中医院"),
        "legal": ("住建局清欠办", "区法院执行局", "工地项目部", "劳动监察大队"),
    },
    "dongbei": {
        "city": ("沈阳", "长春", "哈尔滨", "鞍山", "大连"),
        "hospital": ("医大一院急诊", "市二院骨科", "区医院", "社区医院"),
        "legal": ("区人民法院", "劳动仲裁委", "房产交易中心", "派出所"),
    },
    "shaanxi": {
        "city": ("西安", "咸阳", "渭南", "宝鸡", "榆林"),
        "hospital": ("交大一附院", "市中心医院", "县医院急诊", "镇卫生院"),
        "legal": ("中级人民法院", "不动产登记中心", "劳动监察支队", "交警大队"),
    },
    "shanghai": {
        "city": ("上海", "浦东", "闵行", "杨浦", "静安"),
        "hospital": ("三甲医院急诊科", "社区卫生服务中心", "市眼科医院", "康复科门诊"),
        "legal": ("区人民法院", "街道调解室", "房管局窗口", "公证处"),
    },
    "cantonese": {
        "city": ("广州", "佛山", "东莞", "顺德", "中山"),
        "hospital": ("省中医院", "市胸痛中心", "妇幼保健院", "镇医院急诊"),
        "legal": ("海事法院", "劳动人事争议仲裁院", "不动产登记中心", "派出所"),
    },
    "shandong": {
        "city": ("济南", "青岛", "潍坊", "临沂", "烟台"),
        "hospital": ("省立医院急诊", "肿瘤医院日间病房", "县医院", "市立医院"),
        "legal": ("市劳动人事争议仲裁院", "区人民法院", "公证处", "镇调解中心"),
    },
    "hubei": {
        "city": ("武汉", "襄阳", "宜昌", "黄石", "荆州"),
        "hospital": ("同济医院急诊", "协和医院", "血液净化中心", "民营专科医院"),
        "legal": ("医保飞行检查组", "区法院", "医患纠纷调解中心", "卫健委"),
    },
    "hunan": {
        "city": ("长沙", "株洲", "岳阳", "常德", "郴州"),
        "hospital": ("湘雅医院", "市中心医院", "乡镇卫生院", "呼吸科门诊"),
        "legal": ("市场监管所", "区人民法院", "乡镇司法所", "教育局"),
    },
    "minnan": {
        "city": ("厦门", "泉州", "漳州", "晋江", "石狮"),
        "hospital": ("市第一医院", "海上急救站", "耳鼻喉科", "县医院"),
        "legal": ("渔政管理站", "海事局", "跨境电商产业园", "区法院"),
    },
    "tianjin": {
        "city": ("天津", "滨海新区", "河西区", "南开区", "武清区"),
        "hospital": ("总医院急诊", "安宁疗护病房", "社区卫生中心", "眼科医院"),
        "legal": ("交通事故处理中心", "区人民法院", "公证处", "房管局"),
    },
    "overseas": {
        "city": ("多伦多", "洛杉矶", "墨尔本", "吉隆坡", "新加坡"),
        "hospital": ("当地急诊", "远程会诊中心", "家庭医生诊所", "专科门诊"),
        "legal": ("当地法院", "移民局窗口", "劳动仲裁机构", "领事馆"),
    },
    "tibet_plateau": {
        "city": ("那曲", "玉树", "阿坝", "甘南", "果洛"),
        "hospital": ("州人民医院", "巡回医疗队", "乡卫生院", "县医院急诊"),
        "legal": ("乡政府救灾办", "县农业农村局", "村委会", "民政救助站"),
    },
}

ITEM_BANK: Tuple[str, ...] = (
    "两箱牛奶", "一袋大米", "三桶防水涂料", "五吨钢筋", "一台二手冰柜", "四箱抗生素",
    "一整套验配助听器", "两台透析机耗材", "一辆电动车电池", "八件羊绒衫", "十几只冻羊",
    "一批锂电池电芯", "三台数控刀头", "两扇防盗门", "一车越冬饲料", "六箱胰岛素",
    "两台增氧机", "一批秋装样衣", "数位板与色卡", "五套脚手架扣件",
)

SYMPTOM_BANK: Tuple[str, ...] = (
    "胸口闷痛伴冷汗", "右脚大拇趾红肿灼痛", "持续性头晕伴眼球震颤", "腹部绞痛伴呕吐",
    "单侧肢体发麻说话含糊", "膝关节肿胀无法负重", "伤口渗出脓液有异味", "夜间阵发性呼吸困难",
    "皮肤大片风团伴气促", "尿液呈浓茶色", "咳血丝伴低热", "后腰钝痛并向腿部放射",
    "手掌麻木握不住笔", "突发耳鸣伴旋转性眩晕", "血糖飙到 20 以上", "骶尾部皮肤破溃发黑",
    "反复呕吐无法进食", "心跳得快要从嗓子眼里蹦出来", "体温 39.5 度打寒战", "眼压升高眼睛胀痛",
)

MED_BANK: Tuple[str, ...] = (
    "双氯芬酸钠缓释胶囊", "硝酸甘油片", "速效救心丸", "二甲双胍缓释片", "胰岛素笔芯",
    "硫酸氢氯吡格雷", "布洛芬缓释胶囊", "硝苯地平控释片", "左氧氟沙星", "奥美拉唑肠溶胶囊",
    "沙丁胺醇气雾剂", "云南白药气雾剂", "别嘌醇片", "甲钴胺片", "创可贴与碘伏",
)


# --------------------------------------------------------------------------------------
# 维度四：声学真实环境拓扑与极端噪声源（A01~A12）
# --------------------------------------------------------------------------------------
ACOUSTIC_TOPOLOGIES: Tuple[AcousticTopology, ...] = (
    AcousticTopology(
        aid="A01",
        label="85dB 早晚高峰地铁换乘通道",
        db_range=(80.0, 88.0),
        junk_lines=(
            "列车进站，请乘客先下后上，注意脚下安全",
            "大刀肉大刀肉！两块钱一串！现烤现卖！",
            "扫码送气球嘞，扫一个送一个——",
            "让一让让一让，赶不上车了",
            "地铁口贴膜，二十块钱一张，免费送数据线——",
        ),
        overlap_rate=0.45,
    ),
    AcousticTopology(
        aid="A02",
        label="78dB 露天海鲜农贸市场",
        db_range=(72.0, 84.0),
        junk_lines=(
            "新鲜带鱼！早上刚到的！二十五一斤——",
            "老板称两斤排骨，多搭点葱啊",
            "剁骨刀砰砰砸在砧板上，塑料袋嘶啦作响",
            "三块钱三块钱！最后一批青菜三块钱一堆！",
            "称不准我可要砸你摊子了啊",
        ),
        overlap_rate=0.40,
    ),
    AcousticTopology(
        aid="A03",
        label="90dB 冲压车间与机加工厂房",
        db_range=(84.0, 94.0),
        junk_lines=(
            "气阀排气砰的一声撞击，金属切削发出刺耳尖啸",
            "老李！把那批料搬到三号机床去！",
            "行车鸣笛三声，吊钩缓缓移动",
            "砂轮机擦出火花，钢屑落地沙沙作响",
            "换班了换班了，先去吃饭",
        ),
        overlap_rate=0.30,
    ),
    AcousticTopology(
        aid="A04",
        label="65dB 三甲医院急诊分诊台",
        db_range=(58.0, 72.0),
        junk_lines=(
            "急诊分诊广播：请28号患者到3号诊室就诊",
            "监护仪规律地嘟嘟响，走廊里脚步杂乱",
            "救护车警报由远及近，担架车轱辘碾过地面",
            "护士拿着号牌喊：家属不要在门口聚集——",
            "孩子哭闹着不肯打针，家长在哄",
        ),
        overlap_rate=0.50,
    ),
    AcousticTopology(
        aid="A05",
        label="50dB 深夜高速长途大巴车厢",
        db_range=(42.0, 56.0),
        junk_lines=(
            "发动机低频嗡鸣混着乘客此起彼伏的鼾声",
            "手机外放的短视频声音：家人们点点关注——",
            "司机广播：前方服务区休息二十分钟",
            "过道里有人拖着箱子慢慢走过",
        ),
        overlap_rate=0.25,
    ),
    AcousticTopology(
        aid="A06",
        label="80dB 婚庆宴席大厅",
        db_range=(74.0, 86.0),
        junk_lines=(
            "司仪话筒啸叫：来来来，新郎新娘敬酒啦——",
            "猜拳声四起：哥俩好啊，五魁首啊！",
            "熊孩子追逐撞翻碗盘，长辈在后面喊别跑",
            "后厨传菜口：六号桌的鱼再来一条！",
        ),
        overlap_rate=0.55,
    ),
    AcousticTopology(
        aid="A07",
        label="70dB 暴风雨夜户外露营地",
        db_range=(64.0, 78.0),
        junk_lines=(
            "雨点密集砸在帐篷帆布上，狂风拉扯风绳呼啸",
            "远处闷雷滚滚，闪电把帐篷照得发白",
            "隔壁帐篷的人喊：绳子再打紧一点！",
            "溪水暴涨，石头被冲得哗哗滚落",
        ),
        overlap_rate=0.20,
    ),
    AcousticTopology(
        aid="A08",
        label="76dB 县城网吧与电竞馆",
        db_range=(70.0, 82.0),
        junk_lines=(
            "机箱风扇嗡嗡响，键盘敲击连成一片",
            "有人摔鼠标大喊：这辅助也太坑了吧！",
            "前台喊：8号机三小时，微信还是支付宝？",
            "外放的游戏解说声压过所有交谈",
        ),
        overlap_rate=0.45,
    ),
    AcousticTopology(
        aid="A09",
        label="62dB 乡镇卫生院输液室",
        db_range=(55.0, 70.0),
        junk_lines=(
            "输液架挂钩叮当，液体滴答落进滴壶",
            "老人在咳嗽，家属小声劝他喝口水",
            "护士叮嘱：这瓶挂完记得按铃——",
            "电视里放着戏曲频道，声音开得很大",
        ),
        overlap_rate=0.35,
    ),
    AcousticTopology(
        aid="A10",
        label="74dB 幼儿园接送区与游乐广场",
        db_range=(68.0, 80.0),
        junk_lines=(
            "孩子们追逐尖叫，滑梯上排起队",
            "家长喊：宝宝慢一点！把书包背好！",
            "广场舞音响鼓点咚咚，领队在数节拍",
            "小贩推车经过：棉花糖五块钱一个——",
        ),
        overlap_rate=0.50,
    ),
    AcousticTopology(
        aid="A11",
        label="58dB 老旧小区电梯间与楼道",
        db_range=(50.0, 66.0),
        junk_lines=(
            "电梯运行的低频嗡嗡声突然停顿又启动",
            "楼道里邻居隔着门喊：谁家的水又漏下来了",
            "收废品的扩音器循环播放：高价回收旧家电——",
            "楼梯间的小孩在拍皮球",
        ),
        overlap_rate=0.30,
    ),
    AcousticTopology(
        aid="A12",
        label="55dB 深夜便利店与加油站",
        db_range=(48.0, 62.0),
        junk_lines=(
            "冰柜压缩机嗡嗡响，门口风铃叮的一声",
            "收银台扫码枪嘀嘀响，店员打了个哈欠",
            "加油机流速声突停顿，旁边司机在打电话",
            "便利店广播：关东煮第二份半价——",
        ),
        overlap_rate=0.20,
    ),
)


# --------------------------------------------------------------------------------------
# 维度三：传感器高熵波形库（S00~S06）
# --------------------------------------------------------------------------------------
SENSOR_PROFILES: Dict[str, Dict[str, object]] = {
    "S00": {
        "label": "平稳静息基线",
        "motion_state": "SIT_RESTING",
        "g_range": (0.96, 1.06),
        "hr_range": (58, 88),
        "pvc_range": (0, 1),
        "baro_range": (1002.0, 1018.0),
        "tags": ("steady",),
        "note": "安静坐着或躺着，波形平缓，属于正常基线偏移",
    },
    "S01": {
        "label": "高 G 值剧烈冲击后长时间静止",
        "motion_state": "IMPACT_THEN_STILL",
        "g_range": (15.0, 35.0),
        "hr_range": (96, 148),
        "pvc_range": (0, 6),
        "baro_range": (1000.0, 1016.0),
        "tags": ("impact", "stillness", "fall"),
        "note": "15G~35G 撞击后长时间静止，配合呼救或无人应答",
    },
    "S02": {
        "label": "虚假冲击对冲（单峰高 G + 连续运动）",
        "motion_state": "CONTINUOUS_ACTIVITY",
        "g_range": (4.0, 9.5),
        "hr_range": (110, 168),
        "pvc_range": (0, 3),
        "baro_range": (998.0, 1014.0),
        "tags": ("false_impact", "activity"),
        "note": "磕碰门框/鼓掌/扣杀造成的单峰高 G，但后续运动连续，不构成坠落静止",
    },
    "S03": {
        "label": "夜间静止下恶性心律失常",
        "motion_state": "SUPINE_STILL",
        "g_range": (0.94, 1.12),
        "hr_range": (150, 212),
        "pvc_range": (12, 48),
        "baro_range": (1004.0, 1016.0),
        "tags": ("arrhythmia", "critical"),
        "note": "夜间静息心率从 60 狂飙至 200+，伴高频室性早搏阵发",
    },
    "S04": {
        "label": "缓慢性心脏停搏",
        "motion_state": "SLUMP_AND_SINK",
        "g_range": (0.90, 1.25),
        "hr_range": (26, 42),
        "pvc_range": (0, 5),
        "baro_range": (1006.0, 1016.0),
        "tags": ("pause", "critical"),
        "note": "窦性停搏 3.8 秒，心率骤降至 30 出头，身体失衡失速下沉",
    },
    "S05": {
        "label": "气压与海拔骤变",
        "motion_state": "OUTDOOR_WALKING",
        "g_range": (1.00, 1.45),
        "hr_range": (76, 118),
        "pvc_range": (0, 2),
        "baro_range": (980.0, 1002.0),
        "tags": ("storm", "pressure_drop"),
        "note": "暴雨来临前 20hPa 气压骤降，温湿度突变，体感冰冷",
    },
    "S06": {
        "label": "跑步运动基线正常偏移",
        "motion_state": "RUNNING_CADENCE",
        "g_range": (1.8, 3.6),
        "hr_range": (142, 172),
        "pvc_range": (0, 1),
        "baro_range": (1004.0, 1016.0),
        "tags": ("normal_exertion", "run"),
        "note": "配速 4分30秒 剧烈摆臂，心率规律正弦波动，绝不属于心梗或抽搐",
    },
}


# --------------------------------------------------------------------------------------
# 维度六：声纹说话人拓扑（3~24 人；用户 + 关键交互人 + 大量一次性路人）
# --------------------------------------------------------------------------------------
SPEAKER_ROLES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("spk_stranger_noise", "背景路人", ("这个多少钱？", "哎，让一让", "老板在不在？", "排好队排好队")),
    ("spk_stall_owner", "摊主/小贩", ("便宜卖了啊，最后三斤！", "扫码还是现金？", "新鲜的，早上刚到的！")),
    ("spk_broadcast", "广播/扩音器", ("请乘客注意脚下安全", "本店今日全场八折", "园区禁止吸烟，谢谢配合")),
    ("spk_commuter_01", "通勤路人", ("借过借过，我要下车了", "这趟车怎么还不来", "手机信号又没了")),
    ("spk_worker_01", "工友甲", ("料子放哪边？", "吃饭了没？", "下午还得浇一遍混凝土")),
    ("spk_worker_02", "工友乙", ("钢筋型号又领错了", "这活儿赶得也太紧了", "安全帽扣好再上去")),
    ("spk_customer", "顾客", ("能不能再便宜点？", "发票能开吗？", "我就要那一份")),
    ("spk_delivery_guy", "同行骑手", ("这单又超时了，扣钱扣得狠", "电池别被偷了，昨天丢了两组", "前面路口堵死了")),
    ("spk_child_play", "玩耍的孩子", ("你追不到我！", "妈妈我要吃冰淇淋", "这是我的玩具！")),
    ("spk_salesman", "推销员", ("姐，这个项目保本保息，年化二十个点", "免费领鸡蛋，登记一下就行", "这是最后三个名额了")),
    ("spk_telemarketer", "电话营销", ("您好，我们这边有个低息贷款", "您的号码中奖了", "宽带免费升级了解一下")),
    ("spk_security", "保安/门卫", ("车辆往这边停", "这里不能摆摊", "出来记得登记")),
    ("spk_nurse_call", "护士呼叫", ("请家属到护士站签字", "下一个准备进诊室", "输液快没了记得按铃")),
    ("spk_teacher_call", "老师", ("家长会下周三下午两点", "孩子这次成绩有波动", "校服费明天交")),
    ("spk_neighbor_chat", "邻居闲聊", ("听说这栋楼下个月要停电检修", "你家漏水把我家泡了", "昨晚吵得睡不着")),
    ("spk_gamer", "网吧玩家", ("打野怎么又不在", "这波团输了我认", "网管，机器卡了")),
    ("spk_passenger_snore", "打鼾乘客", ("呼——呼——", "别开窗，冷", "到站了叫我一声")),
    ("spk_wedding_host", "司仪", ("掌声有请新人入场", "大家一起举杯", "新郎官说两句")),
    ("spk_vendor_bike", "流动商贩", ("磨剪子嘞戗菜刀——", "高价回收旧手机", "豆腐脑热乎的，两块钱一碗")),
    ("spk_herder", "牧民", ("羊群往东边去了", "雪太厚，路封了", "帐篷压塌了要重新搭")),
    ("spk_farmer", "农户", ("这天怕是要下大雨", "地里水排不出去", "农药又涨价了")),
    ("spk_rider_tenant", "租客", ("这个月房租能不能缓两天", "水管又漏水了", "押金什么时候退")),
    ("spk_coworker_bg", "公司同事", ("周报记得下午发", "客户又改需求了", "食堂今天有红烧肉")),
    ("spk_tourist", "外地游客", ("请问地铁怎么走", "这边有什么好吃的", "帮我拍张照呗")),
)


# --------------------------------------------------------------------------------------
# 维度七：真假对抗与事实反转陷阱（T01~T08）
# --------------------------------------------------------------------------------------
TRAP_SPECS: Tuple[TrapSpec, ...] = (
    TrapSpec(
        tid="T01",
        label="假借条/假转账截图对冲",
        intent="FAKE_TRANSFER_CLAIM_COUNTERED",
        keywords=("转账失败", "截图造假", "账户异常", "未到账", "赖账", "资金凭证反证"),
        claim_line="钱我已经转过去了哈，{amount}的转账截图发你了，你查收一下",
        claim_app="WeChat",
        counter_line="转账失败：{amount}因对方账户状态异常已原路退回，资金未支出",
        counter_app="BankApp",
        fact_line="{counter_name}收到的转账截图声称已支付{amount}，但银行APP显示该笔转账因对方账户异常失败并原路退回，实际并未到账",
    ),
    TrapSpec(
        tid="T02",
        label="先承认后反悔（口头承诺 vs 短信反悔）",
        intent="PROMISE_BROKEN_AFTER_BACKTRACK",
        keywords=("口头承诺", "反悔推翻", "协议离婚", "出尔反尔", "短信否认", "消耗拖延"),
        claim_line="行，明早九点我准时到民政局，咱们把手续办了，我不拖你",
        claim_app="",
        counter_line="想离门都没有，房子的事没说清之前，我耗死你",
        counter_app="SMS",
        fact_line="电话录音中双方约定次日九点到民政局办理手续，两小时后{role_name}发短信反悔『想离门都没有，耗死你』，口头承诺被推翻",
    ),
    TrapSpec(
        tid="T03",
        label="群聊承诺后撤回并辟谣",
        intent="RETRACTED_COMMITMENT_EVIDENCE",
        keywords=("撤回消息", "证据销毁", "手滑发错", "群内承诺", "自相矛盾", "口头否认"),
        claim_line="这笔货款我先垫，明天上午十点前打到公司账户，大家都看着",
        claim_app="WeChat",
        counter_line="该消息已被撤回；私聊：刚才手滑发错了，别当真",
        counter_app="WeChat",
        fact_line="群聊中{role_name}承诺次日上午十点前垫付货款后于两分钟内撤回，并私聊称『手滑发错』，承诺存在但被销毁证据",
    ),
    TrapSpec(
        tid="T04",
        label="假摔诈伤碰瓷",
        intent="FAKED_FALL_CLAIM_SCAM",
        keywords=("碰瓷诈伤", "无碰撞波峰", "索赔五万", "顺势躺倒", "监控反证", "要价过高"),
        claim_line="你骑车撞到我了！我这腰动不了了，先赔五万，不然我躺这儿不走！",
        claim_app="",
        counter_line="IMU 波形显示全程无冲击波峰，加速度仅 0.98~1.24G，身体为缓慢顺势躺倒后立刻转为自主活动",
        counter_app="SensorStream",
        fact_line="{role_name}在无碰撞的情况下缓慢顺势躺倒并大声呼痛索赔五万元，传感器波形不存在撞击波峰，涉嫌碰瓷敲诈",
        junk_claim=True,
    ),
    TrapSpec(
        tid="T05",
        label="语音克隆冒充亲属诈骗",
        intent="VOICE_CLONE_IMPERSONATION_FRAUD",
        keywords=("语音克隆", "冒充亲属", "紧急汇款", "无法回拨", "反诈提醒", "账号异常"),
        claim_line="妈，我手机摔坏了，这是我同事的号，你赶紧把这个钱转过来，急用！",
        claim_app="WeChat",
        counter_line="反诈中心提醒：该账号被多人举报，涉嫌冒充亲属实施诈骗，请勿转账；回拨原号码无人接听",
        counter_app="SMS",
        fact_line="疑似语音克隆冒充{role_name}要求紧急汇款，反诈平台提示该账号被多次举报且原号码无法回拨，实为诈骗",
        junk_claim=True,
    ),
    TrapSpec(
        tid="T06",
        label="伪造病历/化验单",
        intent="FORGED_MEDICAL_RECORD",
        keywords=("伪造病历", "化验单造假", "日期错位", "医院核验不符", "骗取理赔", "盖章存疑"),
        claim_line="我这儿有诊断证明，医生说了必须休养三个月，赔偿一分不能少",
        claim_app="WeChat",
        counter_line="医院病案室核验回执：该编号病历不存在；系统内同日门诊记录为『上呼吸道感染，无需休假』",
        counter_app="HospitalApp",
        fact_line="对方提交的诊断证明经医院核验不存在，同日门诊记录仅为上呼吸道感染，索赔依据疑似伪造",
    ),
    TrapSpec(
        tid="T07",
        label="双合同阴阳条款",
        intent="DUAL_CONTRACT_SIDE_AGREEMENT",
        keywords=("阴阳合同", "口头承诺", "备案价款不符", "阴阳两份", "偷逃税", "付款条件冲突"),
        claim_line="这份是备案用的，真按那个价结算你们要补税，咱按另外一份来就行",
        claim_app="WeChat",
        counter_line="备案合同扫描件显示价款为{amount}，与手中另一份手写补充协议金额相差一倍以上",
        counter_app="Email",
        fact_line="{role_name}提出签订价款不同的两份合同，备案价与实际结算价相差一倍以上，涉嫌阴阳合同偷逃税费",
    ),
    TrapSpec(
        tid="T08",
        label="伪造传感器数据冒领保险",
        intent="FORGED_SENSOR_CLAIM_INSURANCE",
        keywords=("伪造数据", "冒领保险", "波形拼接", "时间戳矛盾", "理赔调查", "拒赔通知"),
        claim_line="我那天确实摔下脚手架了，手环数据都记着呢，你们保险公司必须赔",
        claim_app="InsuranceApp",
        counter_line="理赔调查回执：上报的冲击波形与同秒 GPS 轨迹矛盾（该时段位于家中静止），且原始采样存在拼接痕迹，予以拒赔",
        counter_app="InsuranceApp",
        fact_line="上报的坠落冲击波形与 GPS 轨迹存在时间冲突并检出数据拼接痕迹，保险理赔被拒，涉嫌伪造传感器数据",
    ),
)


# --------------------------------------------------------------------------------------
# 维度五之二：修辞陷阱与真伪意图（供大模型做"反讽/口嗨/病危硬撑"辨析）
# --------------------------------------------------------------------------------------
RHETORIC_SPECS: Dict[str, Dict[str, object]] = {
    "none": {
        "label": "平实直述",
        "severity": "routine",
        "is_junk": False,
        "utterances": ("就是把这事儿记一下，别到时候说不清", "我先把单子拍下来存着", "这事儿得按规矩来"),
        "fact_note": "无额外修辞，按字面理解",
    },
    "boast_drunk": {
        "label": "酒后狂悖吹牛（无效酒精发泄，必须识别为垃圾）",
        "severity": "routine",
        "is_junk": True,
        "utterances": (
            "明天老子去香港把那栋楼全买下来给弟兄们分了！",
            "等哥发了财，这整条街都给你盘下来！",
            "这点小钱算个屁，老子一个电话就把公司收购了！",
        ),
        "fact_note": "酒精作用下的夸张吹牛，不构成任何真实事实，属于必须剪枝的垃圾",
    },
    "irony_true": {
        "label": "反讽与正话反说（字面夸奖实为严重违约讨债）",
        "severity": "serious",
        "is_junk": False,
        "utterances": (
            "行啊你可真守信用，说好今天还钱连人影都见不着，电话还拉黑",
            "好得很，你们公司办事效率真高，材料交了八个月还没动静",
            "真是谢谢你啊，把我坑得连房租都交不上了",
        ),
        "fact_note": "反讽表层为夸奖，真实语义是严重违约与讨债控诉，必须按反向语义提纯",
    },
    "stoic_critical": {
        "label": "病危假装坚强（乐观说辞必须被一票否决）",
        "severity": "critical",
        "is_junk": False,
        "utterances": (
            "我没事别大惊小怪……就是眼前发黑，舌头有点发麻说话不利索",
            "不用去医院，歇一会儿就好了……就是这半边身子使不上劲儿",
            "别叫救护车，花那钱干啥……胸口就是有点闷，出点汗而已",
        ),
        "fact_note": "当事人刻意淡化病情，但其描述已属急性脑卒中/心梗先兆，必须判定为危重急救事实",
    },
    "argot_hidden": {
        "label": "暗语行话隐匿（非法交易或高保密约定）",
        "severity": "serious",
        "is_junk": False,
        "utterances": (
            "老地方老陈皮拿三份，尾款老规矩走卡",
            "货按上次的走法出，账走三号壳，别用真名",
            "那批料子还压着，先散散味儿，月底再出手",
        ),
        "fact_note": "暗语指代实际交易与转账路径，属于高风险约定，需按字面之外的行业语义提纯",
    },
    "suicidal_metaphor": {
        "label": "自杀自残隐喻（极危重心理危机）",
        "severity": "critical",
        "is_junk": False,
        "utterances": (
            "药已经攒够整整一瓶了，今晚终于可以不用醒过来了",
            "反正我走了也没人发现，空调外机我看了好几天了",
            "把遗书都写好了，就等他们都出门",
        ),
        "fact_note": "隐喻式表达自绝念头，属于最高级别心理危机，绝不可当作玩笑或口嗨",
    },
}


# --------------------------------------------------------------------------------------
# 维度二：五大认知域极限事件谱系（EVENT_FAMILIES）
#   模具约定（由生成引擎解释）：
#     other_lines 形如 "role_key>台词"，user_lines 为佩戴者本人口径；
#     可用槽位：{self_name} {role_key...} {amount} {date} {place} {city} {hospital}
#               {legal_place} {item} {symptom} {med} {vital} {project} {company}
#               {dialect_line} {rhet_line}
# --------------------------------------------------------------------------------------
_HEALTH: Tuple[EventFamily, ...] = (
    EventFamily(
        fid="H01_SILENT_MI",
        domain="dim:health",
        intent="SILENT_MYOCARDIAL_INFARCTION_SIGNS",
        keywords=("心梗先兆", "胸闷胸痛", "冒冷汗", "误当胃痛", "含服硝酸甘油", "急诊心电图", "濒死感"),
        severity="critical",
        sensor_hints=("S03", "S01"),
        roles=("spouse", "doctor"),
        fact_lines=(
            "{self_name}把上腹胀痛当成消化不良硬撑了半天，实际是伴冷汗、恶心、左肩放射痛的下壁心梗先兆，被医生要求立刻进导管室",
            "{self_name}反复说只是胃不舒服，但监护显示心肌酶升高、心电图 ST 段抬高，确诊急性下壁心肌梗死并立即行急诊介入",
        ),
        user_lines=(
            "就是胃有点胀，吃两片{med}顶一下就过去了，别大惊小怪的",
            "我没事，歇会儿就好……就是这后背闷得慌，出了一身冷汗",
        ),
        other_lines=(
            "spouse>你这汗出得衣服都湿透了，脸都白了，不行，咱马上去{hospital}",
            "doctor>肌钙蛋白明显升高，心电图下壁 ST 抬高，马上启动导管室，不能等！",
            "doctor>他说胃痛你就信？下壁心梗的典型表现就是上腹不适加冷汗恶心！",
        ),
        app_keys=(
            ("WeChat", "家属群", "{doctor}刚通知：{self_name}心电图异常，已进导管室做急诊造影，签字马上过来"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "hospital", "med"),
    ),
    EventFamily(
        fid="H02_GOUT_TOPHUS",
        domain="dim:health",
        intent="GOUT_ACUTE_ATTACK_TOPUS_INFECTION",
        keywords=("痛风急性发作", "关节红肿剧痛", "痛风石破溃", "伤口感染", "尿酸超标", "无法着地", "服药止痛"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("spouse", "doctor"),
        fact_lines=(
            "{self_name}右脚第一跖趾关节红肿灼痛无法着地，痛风石破溃处有脓性渗出，血尿酸严重超标，医生要求立即抗感染并降尿酸治疗",
            "{self_name}的痛风急性发作合并痛风石破溃感染，脚趾肿得像馒头一样，连拖鞋都穿不上，只能单脚跳着走",
        ),
        user_lines=(
            "嘶……疼死我了，这脚趾头肿得像馒头火烧一样，先买盒{med}撑着",
            "走不动了走不动了，这脚一沾地就跟针扎似的，谁扶我一把",
        ),
        other_lines=(
            "doctor>尿酸 680，破溃处已经有脓了，再拖下去就是败血症，今天必须住院！",
            "spouse>你少吃点海鲜少喝点酒行不行？上个月刚犯过，这个月又来！",
            "coworker>{self_name}，工地那边你先别去了，我替你顶两天，把脚先养好",
        ),
        app_keys=(
            ("HospitalApp", "检验报告", "血尿酸 682 μmol/L ↑，C反应蛋白 68 mg/L ↑，白细胞 13.9×10⁹/L ↑，建议尽快就诊"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "med", "vital"),
    ),
    EventFamily(
        fid="H03_DKA",
        domain="dim:health",
        intent="DIABETIC_KETOACIDOSIS_BREATH",
        keywords=("酮症酸中毒", "烂苹果味呼吸", "极度口渴", "血糖爆表", "意识模糊", "补液降糖", "急诊抢救"),
        severity="critical",
        sensor_hints=("S03", "S04"),
        roles=("spouse", "doctor"),
        fact_lines=(
            "{self_name}呼吸带烂苹果味、口渴到连喝三瓶水仍不解渴并出现意识模糊，指尖血糖高到血糖仪显示 HI，确诊糖尿病酮症酸中毒正在抢救",
            "{self_name}擅自停用胰岛素后呕吐嗜睡，血气提示代谢性酸中毒、尿酮体强阳性，属于危及生命的糖尿病酮症酸中毒",
        ),
        user_lines=(
            "就是有点渴，最近水喝得多……血糖仪怎么显示 HI 了，是不是坏了",
            "针我不打了，太贵了，省着点吧，反正也没觉得哪儿不舒服",
        ),
        other_lines=(
            "doctor>烂苹果味呼吸、深大呼吸、脱水明显，血气 pH 7.12，立刻双通道补液加胰岛素静脉泵入！",
            "spouse>他这两天一直说渴，我不想打扰你们……现在叫他都迷迷糊糊的",
            "coworker>今天他说话都颠三倒四的，我们以为他熬夜熬的",
        ),
        app_keys=(
            ("HospitalApp", "急诊检验", "血气 pH 7.12 ↓，血糖 32.6 mmol/L ↑↑，尿酮体 +++，符合糖尿病酮症酸中毒"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "vital", "med"),
    ),
    EventFamily(
        fid="H04_CERVICAL_VERTIGO_FALL",
        domain="dim:health",
        intent="CERVICAL_VERTIGO_COLLAPSE",
        keywords=("颈椎压迫眩晕", "眼球震颤", "非绊倒跌坐", "天旋地转", "颈椎病急性期", "前庭性眩晕", "无法站立"),
        severity="serious",
        sensor_hints=("S02", "S00"),
        roles=("doctor", "coworker"),
        fact_lines=(
            "{self_name}转头时突发天旋地转并跌坐在地，眼球有水平震颤，影像提示颈椎间盘突出压迫椎动脉，属颈椎源性眩晕而非绊倒",
            "{self_name}因颈椎压迫前庭血供突发眩晕跌坐，被同事扶住才没有摔伤头部，医生要求卧床并佩戴颈托",
        ),
        user_lines=(
            "我没绊倒，就是一转脖子天旋地转，腿一软就坐地上了",
            "眼睛看东西都在转，扶着墙才能站起来，脖子一动就晕",
        ),
        other_lines=(
            "coworker>你怎么了？刚才人还好好的，突然就往地上瘫！",
            "doctor>眼球有水平震颤，不是单纯低血糖；颈椎片子显示 C5-C6 突出压迫明显，必须卧床牵引",
            "doctor>最近别再低头看手机连续几小时了，再犯可能直接摔倒骨折",
        ),
        app_keys=(
            ("HospitalApp", "影像报告", "颈椎 MRI：C5-C6 椎间盘突出，椎动脉受压，建议颈托保护与康复治疗"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "doctor"),
    ),
    EventFamily(
        fid="H05_ANAPHYLAXIS",
        domain="dim:health",
        intent="DRUG_ANAPHYLACTIC_SHOCK",
        keywords=("药物过敏", "皮疹风团", "喉头水肿", "呼吸困难", "肾上腺素抢救", "输液反应", "立刻停药"),
        severity="critical",
        sensor_hints=("S03",),
        roles=("nurse", "doctor"),
        fact_lines=(
            "{self_name}输注中药注射液五分钟后全身风团、喉咙发紧、说话费力，判断为药物过敏性休克，现场给予肾上腺素并送抢救室",
            "{self_name}用药后出现全身瘙痒红疹伴气促、血压下降，属于急性过敏反应，药物已立即停用并抗休克处理",
        ),
        user_lines=(
            "怎么身上突然这么痒……嗓子好像被什么东西堵住了",
            "我喘不上气，手也麻了，赶紧的……",
        ),
        other_lines=(
            "nurse>停！马上停药！身上全是风团，血压 78/46，快推抢救车！",
            "doctor>典型过敏性休克，肾上腺素 0.5mg 肌注，地塞米松静推，开放两路静脉！",
            "doctor>以前用过这个药不过敏？过敏可以迟发，这次记下来永久禁忌",
        ),
        app_keys=(
            ("HospitalApp", "抢救记录", "过敏性休克抢救：肾上腺素 0.5mg 肌注，生命体征 10 分钟一次监测"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "med", "vital"),
    ),
    EventFamily(
        fid="H06_RHABDOMYOLYSIS",
        domain="dim:health",
        intent="RHABDOMYOLYSIS_DARK_URINE",
        keywords=("横纹肌溶解", "浓茶色尿", "剧烈运动后", "肌酸激酶爆表", "肌肉酸痛", "急性肾损伤", "大量补液"),
        severity="serious",
        sensor_hints=("S06", "S01"),
        roles=("doctor", "coworker"),
        fact_lines=(
            "{self_name}剧烈运动后肌肉剧痛、尿液呈浓茶色，肌酸激酶高达数万，诊断为横纹肌溶解并存在急性肾损伤风险，需大量补液碱化尿液",
            "{self_name}在体测/加练后出现酱油色尿与肌无力，化验提示横纹肌溶解，医生警告再晚半天可能肾衰",
        ),
        user_lines=(
            "尿怎么是浓茶色的？可能是上火了，多喝点水就行了",
            "腿酸得下不了楼，走路跟踩在棉花上似的",
        ),
        other_lines=(
            "coworker>你昨天不就跑了十公里嘛，今天怎么连楼梯都下不来？",
            "doctor>CK 三万八，肌红蛋白阳性，这是横纹肌溶解！马上大量补液，否则急性肾衰要透析的！",
            "doctor>以后运动量要循序渐进，别一次性把自己练进 ICU",
        ),
        app_keys=(
            ("HospitalApp", "检验报告", "肌酸激酶 38,600 U/L ↑↑，肌红蛋白 1,120 μg/L ↑，尿隐血 +，警惕急性肾损伤"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "vital"),
    ),
    EventFamily(
        fid="H07_STROKE_STOIC",
        domain="dim:health",
        intent="ACUTE_STROKE_SIGNS_UNDERSTATED",
        keywords=("脑卒中先兆", "口角歪斜", "单侧肢体无力", "言语含糊", "假装坚强", "溶栓时间窗", "立即送医"),
        severity="critical",
        sensor_hints=("S04", "S03"),
        roles=("spouse", "doctor"),
        fact_lines=(
            "{self_name}口角歪斜、右侧肢体抬不起来且言语含糊，却反复说没事，被家属识破送医后确诊急性脑梗死，正评估静脉溶栓",
            "{self_name}刻意淡化症状称只是手麻，实际已出现单侧肢体无力与言语不清，属于急性脑卒中，溶栓时间窗分秒必争",
        ),
        user_lines=(
            "我没事别大惊小怪……就是眼前发黑，舌头有点发麻说话不利索",
            "不用去医院，躺一会儿就好……就是我这边手怎么使不上劲儿了",
        ),
        other_lines=(
            "spouse>你嘴都歪了！笑一个——笑不出来，快打 120，这是中风！",
            "doctor>发病 2 小时 40 分，还在时间窗内，马上做 CT 排除出血，准备溶栓！",
            "doctor>患者自己说不严重不代表不严重，家属判断得非常及时",
        ),
        app_keys=(
            ("HospitalApp", "急诊绿色通道", "卒中绿色通道启动：NIHSS 12 分，CT 未见出血，拟静脉溶栓"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "hospital"),
    ),
    EventFamily(
        fid="H08_WOUND_INFECTION",
        domain="dim:health",
        intent="SURGICAL_WOUND_INFECTION_SEPSIS",
        keywords=("伤口感染", "脓性渗出", "发热寒战", "红肿热痛", "压疮恶化", "清创引流", "全身感染风险"),
        severity="serious",
        sensor_hints=("S03",),
        roles=("nurse", "doctor"),
        fact_lines=(
            "{self_name}伤口周围红肿发热、渗出脓液并伴 38.9℃ 寒战，判断为伤口感染加重，需立即清创引流并使用抗生素",
            "{self_name}术后切口裂开流脓、有异味且体温升高，医生提示已出现全身感染征象，必须住院抗感染治疗",
        ),
        user_lines=(
            "就是伤口有点痒……渗点水，换块纱布就好了吧",
            "身上怎么一阵冷一阵热的，可能是昨晚着凉了",
        ),
        other_lines=(
            "nurse>这味儿不对，渗出是黄绿色的，还发热，必须马上叫医生看",
            "doctor>白细胞 16.4，C反应蛋白 92，伤口感染已经跑进血里了，今天清创，抗生素上调",
            "spouse>我早就说让你去医院换药，你非得自己在家拿碘伏糊弄",
        ),
        app_keys=(
            ("HospitalApp", "检验报告", "白细胞 16.4×10⁹/L ↑，C反应蛋白 92 mg/L ↑，降钙素原升高，提示细菌感染"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "vital", "med"),
    ),
    EventFamily(
        fid="H09_PSYCH_CRISIS",
        domain="dim:health",
        intent="ACUTE_SUICIDAL_CRISIS",
        keywords=("自杀风险", "心理危机干预", "攒药", "遗书", "情绪崩塌", "陪伴监护", "危机热线"),
        severity="critical",
        sensor_hints=("S00", "S04"),
        roles=("spouse", "doctor"),
        fact_lines=(
            "{self_name}连续失眠并整理遗物、攒下整瓶安眠药，表达'不用再醒来'的念头，被判定为高度自杀风险需立即监护干预",
            "{self_name}在电话里交代后事并写下遗书，心理危机干预团队已上门，家属被要求 24 小时不离人看护",
        ),
        user_lines=(
            "药已经攒够整整一瓶了，今晚终于可以不用醒过来了",
            "都别管我了，我走了对大家都好，东西我都收拾好了",
        ),
        other_lines=(
            "spouse>你刚刚说什么？你把遗书放哪儿了？电话别挂，我求你，别挂！",
            "doctor>这是重度抑郁伴自杀计划，必须立即住院，家属不能让他一个人待着，家里的药全部收起来",
            "coworker>他最近一个月几乎不说话，工作也总是出错，我们还以为他只是累",
        ),
        app_keys=(
            ("WeChat", "{spouse}", "你在哪？把定位发我，我现在就来，什么都可以慢慢说，别做傻事"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "med"),
    ),
    EventFamily(
        fid="H10_PREGNANCY_EMERGENCY",
        domain="dim:health",
        intent="LATE_PREGNANCY_ACUTE_EMERGENCY",
        keywords=("孕晚期急症", "胎动减少", "阴道出血", "妊娠期高血压", "紧急剖宫产", "胎心监护异常", "立即住院"),
        severity="critical",
        sensor_hints=("S03", "S04"),
        roles=("doctor", "spouse"),
        fact_lines=(
            "{self_name}陪孕 34 周的爱人{spouse}产检时发现胎动明显减少伴下腹坠痛与血压升高，胎心监护提示晚期减速，医生决定紧急剖宫产",
            "{self_name}陪爱人{spouse}就诊时发现其孕晚期阴道流血与持续宫缩，被判定为妊娠晚期急症，正在送往手术室行急诊剖宫产",
        ),
        user_lines=(
            "她今天说宝宝动得少……我劝她再观察观察，可能是我太累了没在意",
            "爱人肚子一阵一阵发紧，腰也酸得厉害，我这就带她去医院",
        ),
        other_lines=(
            "doctor>胎心基线 180，反复晚期减速，不能再等了，通知手术室，备血，马上剖！",
            "nurse>血压 158/102，尿蛋白阳性，考虑子痫前期，先把硫酸镁挂上",
            "spouse>医生让签什么我就签什么，人最重要，麻烦你们了",
        ),
        app_keys=(
            ("HospitalApp", "胎心监护", "胎心基线 178 bp/min，频发晚期减速，NST 无反应型，建议急诊手术"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "hospital", "vital"),
    ),
    EventFamily(
        fid="H11_ALTITUDE_SICKNESS",
        domain="dim:health",
        intent="HIGH_ALTITUDE_PULMONARY_EDEMA",
        keywords=("高原反应", "高原肺水肿", "剧烈头痛", "咳粉红色泡沫痰", "血氧骤降", "紧急下撤吸氧", "意识淡漠"),
        severity="critical",
        sensor_hints=("S05", "S03"),
        roles=("coworker", "doctor"),
        fact_lines=(
            "{self_name}在海拔 4300 米出现剧烈头痛、咳粉红色泡沫痰、血氧跌至 68%，诊断为高原肺水肿，必须立即吸氧并下撤海拔",
            "{self_name}高原作业时出现意识淡漠与呼吸困难，队医判断为高原肺水肿早期，正在紧急转运至低海拔医院",
        ),
        user_lines=(
            "就是有点头疼，吸口氧就好了，队伍不能为我耽误",
            "咳得厉害……喘不上气，胸口像压了块石头",
        ),
        other_lines=(
            "coworker>他嘴唇都紫了，血氧只有 68，别逞强了，马上往低海拔撤！",
            "doctor>粉红色泡沫痰加双肺湿啰音，这是高原肺水肿，下撤是唯一有效的救命措施，一秒钟都不能拖",
            "coworker>车队听好了，掉头，往 2800 米的救护点开！",
        ),
        app_keys=(
            ("SensorApp", "血氧报警", "SpO₂ 68%（海拔 4310m），心率 128，建议立即下撤并高流量吸氧"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "vital"),
    ),
    EventFamily(
        fid="H12_HYPERTENSIVE_CRISIS",
        domain="dim:health",
        intent="HYPERTENSIVE_CRISIS_TARGET_ORGAN",
        keywords=("高血压危象", "血压 180/110", "头痛呕吐", "视物模糊", "眼底出血", "静滴降压", "心脑肾损害"),
        severity="critical",
        sensor_hints=("S03", "S00"),
        roles=("doctor", "spouse"),
        fact_lines=(
            "{self_name}血压飙至 190/116 伴剧烈头痛与视物模糊，眼底见出血点，诊断为高血压危象需静脉降压并排查靶器官损伤",
            "{self_name}突发血压危象，头痛到呕吐、看不清东西，医生要求立即静脉泵入降压药并在监护室观察",
        ),
        user_lines=(
            "就是头有点疼，量了血压 180 多……缓一缓应该就下去了",
            "药我这两天忙忘了吃，不碍事的，我平时身体挺好",
        ),
        other_lines=(
            "doctor>血压 190/116，眼底有出血，这是高血压危象，马上静脉泵入降压药，谨防脑出血",
            "spouse>他昨天就喊头疼，还硬撑着去开会，我劝他他不听",
            "doctor>降压不能太猛，先降到 160 左右，做头颅 CT 排除出血",
        ),
        app_keys=(
            ("HospitalApp", "急诊记录", "血压 190/116 mmHg，眼底见片状出血，拟静脉降压并头颅 CT 检查"),
        ),
        dialect_fn="pain",
        entity_slots=("self_name", "vital", "hospital"),
    ),
)

_FINANCE: Tuple[EventFamily, ...] = (
    EventFamily(
        fid="F01_WAGE_ARREARS",
        domain="dim:finance",
        intent="LABOR_WAGE_DISPUTE_PROMISE",
        keywords=("讨薪", "劳务纠纷", "拖欠工资", "结清工钱", "住建局投诉", "对质争执", "还钱承诺"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("creditor", "boss", "coworker"),
        fact_lines=(
            "{creditor}就班组工人被拖欠的{amount}堵门向{self_name}讨薪并扬言去{legal_place}投诉，{self_name}承诺{date}前分文不少打卡结清",
            "{self_name}被{creditor}堵在项目部对质工人的{amount}血汗钱，双方约定{date}前必须结清否则集体上访住建部门",
        ),
        user_lines=(
            "{creditor}，我脚趾头肿得像馒头下不了地……总包方那{amount}结算款{date}我亲自去堵门要，分文不少给兄弟们",
            "我知道欠着大家，这钱我一定想办法，哪怕把车卖了先给兄弟们垫上",
        ),
        other_lines=(
            "creditor>{self_name}！别装瘸！工地上几十号兄弟的血汗钱，{date}要是打不进卡里，咱们{legal_place}见！",
            "boss>结算款按流程走，你们别闹，闹大了对谁都没好处",
            "coworker>{self_name}，弟兄们都在等你一句话，是给还是不给",
        ),
        app_keys=(
            ("BankApp", "工资代发", "代发工资指令提交失败：账户余额不足，需补足{amount}后重试"),
            ("WeChat", "{creditor}", "兄弟们都盯着呢，{date}之前务必见钱，不然我们只能去{legal_place}了"),
        ),
        dialect_fn="money",
        entity_slots=("creditor", "amount", "date", "legal_place"),
    ),
    EventFamily(
        fid="F02_IOU_DISPUTE",
        domain="dim:finance",
        intent="DEBT_ACKNOWLEDGEMENT_DISPUTE",
        keywords=("欠条纠纷", "借条真伪", "口头借款", "拒不认账", "转账记录", "对账争执", "限期还款"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("creditor", "lawyer"),
        fact_lines=(
            "{self_name}与{creditor}就{amount}借款的欠条真伪当面对账，对方拒不承认签字，{self_name}已准备申请笔迹鉴定",
            "{creditor}否认{amount}借款并撕毁欠条复印件，{self_name}出示转账流水与聊天记录固定证据，拟向法院起诉",
        ),
        user_lines=(
            "钱是我一笔一笔转过去的，流水就在这儿，{creditor}你别翻脸不认人",
            "欠条你要是不认，那咱就走笔迹鉴定，我不怕麻烦",
        ),
        other_lines=(
            "creditor>这字不是我签的，你别拿张破纸来讹我{amount}",
            "lawyer>转账记录、聊天记录、证人证言可以形成证据链，笔迹鉴定申请我们明天就递",
            "creditor>你要起诉就起诉，反正我没钱，你告赢了也拿不到",
        ),
        app_keys=(
            ("BankApp", "流水查询", "近三年转账流水已生成：向{creditor}累计转出{amount}，含备注『借款』3 笔"),
            ("WeChat", "{creditor}", "钱我可以慢慢还，但你得把利息抹了，不然一分没有"),
        ),
        dialect_fn="money",
        entity_slots=("creditor", "amount", "lawyer"),
    ),
    EventFamily(
        fid="F03_FAKE_INVOICE_AUDIT",
        domain="dim:finance",
        intent="FALSE_INVOICE_TAX_AUDIT",
        keywords=("假发票", "税务稽查", "虚开发票", "进项异常", "对账差异", "补税罚款", "责任人签字"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("boss", "officer", "coworker"),
        fact_lines=(
            "{legal_place}突击进厂核查{amount}的大额进项发票，{self_name}发现其中三份供应商发票为虚开，公司面临补税及罚款",
            "{self_name}在税务稽查现场被要求说明{amount}发票来源，经比对开票方已注销，涉嫌取得虚开发票",
        ),
        user_lines=(
            "这几张票的合同、验收单我都要求提供过，是业务部门硬塞过来的",
            "账我可以一笔笔对，但责任不能全压在我一个人头上",
        ),
        other_lines=(
            "officer>这三份发票的开票方已在半年前注销，属于异常凭证，请提供完整业务链证据",
            "boss>{self_name}，这事儿你先把材料圆过去，别把公司扯进去",
            "coworker>当时那批票是老板让入账的，我留了邮件记录",
        ),
        app_keys=(
            ("Email", "业务部", "那{amount}的票你先入账，后续合同我补给你，别卡着流程"),
            ("TaxApp", "风险提示", "您单位存在 3 份异常凭证，涉及金额{amount}，请于{date}前说明情况"),
        ),
        dialect_fn="rebut",
        entity_slots=("amount", "legal_place", "date"),
    ),
    EventFamily(
        fid="F04_PONZI_COLLAPSE",
        domain="dim:finance",
        intent="VIRTUAL_CURRENCY_PONZI_COLLAPSE",
        keywords=("虚拟币崩盘", "传销盘跑路", "拉人头返利", "提现失败", "群主失联", "资金盘", "报案登记"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("friend", "officer"),
        fact_lines=(
            "{self_name}投入{amount}的虚拟币理财盘无法提现、群主失联，平台典型拉人头返利结构被认定为传销资金盘，正在组织报案登记",
            "{self_name}参与的虚拟币项目一夜崩盘，所谓静态收益全部冻结，警方已按组织传销立案并通知投资人登记",
        ),
        user_lines=(
            "当初说日息百分之一，我投了{amount}……现在客服也没了",
            "我不该贪这个高息的，这可是给孩子攒的学费啊",
        ),
        other_lines=(
            "friend>别加仓了！这种拉人头返利的盘子就是传销，早晚要崩",
            "officer>请带好转账记录来登记，涉案金额大的话追赃周期会比较长",
            "friend>群主昨天还在发收益截图，今天群就解散了",
        ),
        app_keys=(
            ("WeChat", "虚拟币交流群", "【系统维护】平台暂停提现 72 小时，请耐心等待，切勿相互传播不实信息"),
            ("BankApp", "转账记录", "向『星链数科』商户转出{amount}，状态成功"),
        ),
        dialect_fn="rebut",
        entity_slots=("amount", "friend", "legal_place"),
    ),
    EventFamily(
        fid="F05_LENDING_DEFAULT",
        domain="dim:finance",
        intent="PRIVATE_LENDING_DEFAULT_RECOVERY",
        keywords=("高利贷追偿", "利滚利", "上门催收", "软暴力威胁", "报警备案", "本金认定", "超法定利率"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("creditor", "officer"),
        fact_lines=(
            "{creditor}以{amount}本金按月息三分计息，上门催收并对{self_name}施加软暴力威胁，警方提示超出法定利率部分不受保护",
            "{self_name}被高利贷催收人员堵在门口威胁，实际到账本金远低于借条金额，已报警并留存录音证据",
        ),
        user_lines=(
            "我借的时候到手就{amount}，利滚利滚成这样我实在还不上",
            "你们要是再堵门我就报警了，我不是不还，是还不起这个数",
        ),
        other_lines=(
            "creditor>今天要么拿钱，要么把房子抵押给我，别怪兄弟们不客气",
            "officer>超过法定利率部分法院不支持，任何人不得以催收名义威胁恐吓，请把录音交给警方",
            "creditor>我不管什么法定不法定，白纸黑字写着呢",
        ),
        app_keys=(
            ("SMS", "催收通知", "您的借款已逾期，今日需还{amount}，否则将联系您的亲属及单位"),
            ("WeChat", "{creditor}", "别躲了，我在你家属院门口，出来聊聊"),
        ),
        dialect_fn="threat",
        entity_slots=("creditor", "amount", "officer"),
    ),
    EventFamily(
        fid="F06_BET_JOINT_LIABILITY",
        domain="dim:finance",
        intent="FINANCING_BET_JOINT_LIABILITY",
        keywords=("对赌失败", "无限连带责任", "连带清偿通知", "股权回购", "个人资产冻结", "法务函", "还款方案"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("lawyer", "partner"),
        fact_lines=(
            "{self_name}签署的融资对赌协议因业绩未达标触发回购条款，收到{amount}连带清偿通知，个人房产面临被查封风险",
            "投资方依据对赌协议要求{self_name}承担{amount}无限连带责任，律师建议立即梳理可执行财产并争取分期和解",
        ),
        user_lines=(
            "当初签字的时候谁知道会到这个地步，现在让我一个人扛{amount}",
            "房本都在家里，你们要执行我也拦不住，我只求别牵连老人孩子",
        ),
        other_lines=(
            "lawyer>连带责任已经生效，对方申请财产保全的话，你的房和车都会先被查封",
            "partner>这事儿是你签的字，我只能帮你协调，钱我是真拿不出来了",
            "lawyer>建议主动联系对方谈分期，别等到强制执行，那样信用彻底完了",
        ),
        app_keys=(
            ("Email", "投资方法务", "关于{amount}股权回购及连带清偿的通知：请于{date}前书面回复还款安排"),
            ("BankApp", "账户提醒", "您名下账户已收到法院协助冻结通知，请注意资金安排"),
        ),
        dialect_fn="rebut",
        entity_slots=("amount", "lawyer", "date"),
    ),
    EventFamily(
        fid="F07_HOUSE_CHAIN_BREACH",
        domain="dim:finance",
        intent="SECOND_HAND_HOUSE_CHAIN_BREACH",
        keywords=("二手房违约", "连环单", "定金不退", "中介吃差价", "网签失败", "诉讼保全", "双倍返还"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("client", "lawyer"),
        fact_lines=(
            "{self_name}的二手房连环单因下家贷款审批失败断链，卖方拒绝返还{amount}定金，中介又被指吃差价，双方拟诉讼解决",
            "二手房交易中{self_name}的下家临时毁约，{amount}定金与中介费争议升级，买卖双方在{legal_place}门口激烈争执",
        ),
        user_lines=(
            "我这边定金都交了，房子卖了才有钱付这边，现在两头都卡死了",
            "中介当初说的价跟他现在报的差着好几万，这差价是不是进你们兜里了",
        ),
        other_lines=(
            "client>合同写的是{date}前网签，你们违约在先，定金按法律是双倍返还",
            "lawyer>房屋买卖合同纠纷我们可以先申请诉前保全，但时间成本不低，建议调解",
            "client>钱不退我们就去{legal_place}说理，今天谁也别想走",
        ),
        app_keys=(
            ("BankApp", "转账凭证", "您已向{client}支付定金{amount}，备注：二手房定金"),
            ("HousingApp", "网签通知", "您预约的网签时间为{date}，因买方贷款审批未通过，本次预约已失效"),
        ),
        dialect_fn="money",
        entity_slots=("client", "amount", "date", "legal_place"),
    ),
    EventFamily(
        fid="F08_RENOVATION_FLED",
        domain="dim:finance",
        intent="RENOVATION_CONTRACTOR_ABSCONDED",
        keywords=("装修队跑路", "卷款消失", "烂尾工地", "工人围堵", "材料商追款", "合同诈骗", "报案受理"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("coworker", "officer", "supplier"),
        fact_lines=(
            "装修队收取{amount}工程款后卷款跑路，工地烂尾、工人与材料商堵在{self_name}家门口要账，警方已受理合同诈骗报案",
            "承接装修的包工头拿钱失联，{self_name}不但房子没装完，还被材料商追讨欠款，正在{legal_place}做笔录",
        ),
        user_lines=(
            "钱我一分不少打给他了，房子还是毛坯，你们堵我家有什么用",
            "我也想知道人去哪儿了，我比你们还想找到他",
        ),
        other_lines=(
            "supplier>他欠我{amount}材料款，人跑了我不找你找谁，你家门牌号是他给我的",
            "officer>请提供合同、转账记录和现场照片，我们按合同诈骗受理，追赃需要时间",
            "coworker>工钱还欠我们两个月呢，老板电话关机了",
        ),
        app_keys=(
            ("BankApp", "转账凭证", "向『宏图装饰工程』转出{amount}，状态成功"),
            ("WeChat", "装修队", "你们先别急，我在外地谈材料，下周一定回来开工"),
        ),
        dialect_fn="threat",
        entity_slots=("amount", "supplier", "legal_place"),
    ),
    EventFamily(
        fid="F09_ACCOUNT_FROZEN",
        domain="dim:finance",
        intent="BANK_ACCOUNT_FROZEN_SUSPECTED_FRAUD",
        keywords=("账户冻结", "涉诈资金", "反诈中心", "交易异常", "解冻材料", "误伤申诉", "资金周转断裂"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("officer", "boss"),
        fact_lines=(
            "{self_name}的收款账户因被标注涉诈交易而冻结，当日{amount}货款被拦，需向反诈中心提交合同与发货凭证申请解冻",
            "{self_name}账户内{amount}资金被公安机关冻结，经查是上游客户资金涉诈牵连，正在准备材料申诉解冻",
        ),
        user_lines=(
            "我这钱是正经货款，货都发出去了，凭什么冻结我的账户",
            "工人等着发工资，账户一天不解冻，我这边就得停摆",
        ),
        other_lines=(
            "officer>上游一笔资金涉诈流入你的账户，需要你提供合同、发票、物流单据来证明交易真实",
            "boss>顾客的钱你先垫一下，等账户解冻了再结，别让人家等太久",
            "officer>材料齐全一般{date}左右能走完流程，你先按流程来，不要相信所谓'花钱解冻'的中介",
        ),
        app_keys=(
            ("BankApp", "账户提醒", "您的账户因司法协助冻结，可用余额 {amount} 元已暂停使用，请联系冻结机关"),
            ("SMS", "反诈中心", "您账户疑似涉诈，请勿向陌生人转账，如为正常交易请携带材料至反诈中心核实"),
        ),
        dialect_fn="rebut",
        entity_slots=("amount", "officer", "date"),
    ),
    EventFamily(
        fid="F10_INSURANCE_DENIED",
        domain="dim:finance",
        intent="INSURANCE_CLAIM_DENIED_DISPUTE",
        keywords=("保险拒赔", "理赔调查", "既往病史", "免责条款", "数据矛盾", "理赔复议", "消保投诉"),
        severity="serious",
        sensor_hints=("S00", "S01"),
        roles=("officer", "lawyer"),
        fact_lines=(
            "{self_name}的意外险理赔被以既往病史未如实告知为由拒赔，{amount}医疗费无法报销，正在申请理赔复议并向消保部门投诉",
            "保险公司以{self_name}投保前存在相关病史为由拒付{amount}理赔金，律师认为未尽明确说明义务的免责条款可主张无效",
        ),
        user_lines=(
            "我买的时候业务员什么都没问，出了事就拿既往病史堵我",
            "这{amount}是我自己垫的救命钱，你们一句话就拒赔了？",
        ),
        other_lines=(
            "officer>我们依据的是投保告知书第七条，您签字确认过",
            "lawyer>签字不代表你们尽到了明确说明义务，条款提示不足的话法院一般不支持免责",
            "officer>您可以申请复议，或者走消保投诉、诉讼渠道",
        ),
        app_keys=(
            ("InsuranceApp", "理赔结论", "尊敬的客户：您提交的理赔申请经审核属于责任免除范围，本次不予赔付，如有异议可申请复议"),
            ("BankApp", "缴费记录", "自费住院医疗支出 {amount} 元，医保报销后现金支付部分已扣款"),
        ),
        dialect_fn="rebut",
        entity_slots=("amount", "officer", "lawyer"),
    ),
    EventFamily(
        fid="F11_HIGH_YIELD_WEALTH_CRASH",
        domain="dim:finance",
        intent="HIGH_YIELD_WEALTH_PRODUCT_CRASH",
        keywords=("高息理财爆雷", "养老钱亏损", "客户经理失联", "虚假底层资产", "本息无法兑付", "集体维权", "报案登记"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("officer", "friend"),
        fact_lines=(
            "{self_name}投入{amount}养老钱购买年化 12% 的理财产品后平台停止兑付，客户经理失联，底层资产被查为虚构，正在集体报案",
            "高息理财平台爆雷，{self_name}的{amount}本息无法兑付，警方介入后认定其资金池模式涉嫌非法吸收公众存款",
        ),
        user_lines=(
            "当时他们穿着银行制服，说保本保息，我才把养老钱投进去的",
            "我不指望利息了，我只想把本金要回来，那是我一辈子攒的",
        ),
        other_lines=(
            "friend>你怎么又信这个，年化十二个点哪有这种好事，早劝过你",
            "officer>请登记投资金额与合同，我们会统一追赃，同时提醒家里老人别再投了",
            "friend>我们楼里好几个老人都在这个平台上，最多的投了{amount}",
        ),
        app_keys=(
            ("WealthApp", "兑付公告", "因底层资产处置进度不及预期，本期兑付延期，具体时间另行通知"),
            ("SMS", "客户经理", "阿姨您放心，公司有国资背景，本息绝对没问题，您再追加一点拿更高的档位"),
        ),
        dialect_fn="money",
        entity_slots=("amount", "officer", "friend"),
    ),
    EventFamily(
        fid="F12_TRAFFIC_COMPENSATION",
        domain="dim:finance",
        intent="TRAFFIC_ACCIDENT_COMPENSATION_DISPUTE",
        keywords=("交通事故赔偿", "责任认定", "医疗费垫付", "误工费争议", "保险理赔", "调解协议", "后续治疗费"),
        severity="serious",
        sensor_hints=("S01", "S02"),
        roles=("officer", "stranger", "lawyer"),
        fact_lines=(
            "{self_name}与{stranger}发生交通事故，交警认定对方主责，{amount}医疗费与误工费争议未决，双方在{legal_place}调解",
            "{self_name}被撞伤后对方仅垫付部分医药费，{amount}后续治疗与误工损失协商破裂，已申请交警调解并准备起诉",
        ),
        user_lines=(
            "医药费我一分没多要，单据都在这儿，{amount}是实际花掉的",
            "我腿还下不了床，你们不能一句'保险会赔'就把我打发了",
        ),
        other_lines=(
            "stranger>保险会赔的，你先自己垫着，别来烦我",
            "officer>事故责任认定书已经出了，赔偿项目按标准核算，双方先调解，调解不成就走诉讼",
            "lawyer>误工费需要提供工资流水和医院休假证明，材料我帮你整理",
        ),
        app_keys=(
            ("InsuranceApp", "理赔进度", "您的车险人伤案件已受理，需补充交警责任认定书与医疗票据，预计{date}前完成核赔"),
            ("WeChat", "{stranger}", "医药费你先垫着，等你出院咱们一起算，别天天打电话催"),
        ),
        dialect_fn="money",
        entity_slots=("amount", "stranger", "legal_place", "date"),
    ),
)


_SOCIAL: Tuple[EventFamily, ...] = (
    EventFamily(
        fid="S01_PATERNITY_REPORT",
        domain="dim:social",
        intent="PATERNITY_TEST_NON_BIOLOGICAL",
        keywords=("亲子鉴定", "非亲生", "十年养育", "信任崩塌", "抚养争议", "心理冲击", "结果宣读"),
        severity="serious",
        sensor_hints=("S03",),
        roles=("spouse", "doctor", "lawyer"),
        fact_lines=(
            "亲子鉴定报告显示{self_name}养育十年的孩子与其无生物学亲子关系，双方在{legal_place}当场爆发激烈争吵并谈及抚养与赔偿",
            "{self_name}收到司法鉴定意见书，排除其为孩子的生物学父亲，家庭信任彻底崩塌，正咨询抚养费返还与离婚事宜",
        ),
        user_lines=(
            "这张纸我看了一百遍……十年的感情不是说没就没的，可这口气我咽不下",
            "孩子是无辜的，这话我认，但你们谁替我想过",
        ),
        other_lines=(
            "spouse>你要我怎么办？那是十年前的事，孩子都叫你十年爸爸了！",
            "doctor>根据 DNA 分型结果，排除亲子关系的准确率超过 99.99%，报告已出具",
            "lawyer>可以主张返还抚养费并要求精神损害赔偿，但诉讼会把孩子彻底卷进来，你要想清楚",
        ),
        app_keys=(
            ("WeChat", "{spouse}", "报告我看到了，你想怎么办？咱们坐下来谈谈，别在孩子面前说"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "spouse", "legal_place"),
    ),
    EventFamily(
        fid="S02_PARTNER_SHELL",
        domain="dim:social",
        intent="PARTNER_HIDDEN_SHELL_COMPANY",
        keywords=("合伙人背叛", "另设壳公司", "转移客户名单", "知识产权侵权", "账目做手脚", "对质摊牌", "股权清算"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("partner", "lawyer", "coworker"),
        fact_lines=(
            "{self_name}发现合伙人{partner}暗中另设壳公司，将核心客户名单与专利技术转移过去，双方在办公室摊牌并要求清算股权",
            "{partner}用配偶名义注册同业公司承接原公司客户，{self_name}掌握转账与合同证据后提出股权转让与赔偿要求",
        ),
        user_lines=(
            "这么多年一起扛过来的，你在背后搞这么一套，我认你这个人真是瞎了眼",
            "客户名单、源代码、公章，你哪一样不是从我这儿顺走的",
        ),
        other_lines=(
            "partner>公司是公司的，客户愿意跟我走那是他们的选择，你别血口喷人",
            "lawyer>同业竞争、商业秘密侵权、损害公司利益，证据链够了可以直接起诉，也可以先谈股权",
            "coworker>那家新公司的注册地址我看着眼熟，就是{partner}老婆的店面",
        ),
        app_keys=(
            ("Email", "{partner}", "这批客户我先把合同转到我爱人那家公司签，价格比我们低五个点，你别多想"),
            ("BankApp", "转账记录", "对公账户向『辰星科技』转出{amount}，备注：服务费"),
        ),
        dialect_fn="rebut",
        entity_slots=("partner", "amount", "lawyer"),
    ),
    EventFamily(
        fid="S03_HARASSMENT_EVIDENCE",
        domain="dim:social",
        intent="WORKPLACE_HARASSMENT_EVIDENCE_COLLECTION",
        keywords=("言语性骚扰", "录音取证", "职场权力压迫", "微信骚扰", "举报投诉", "证人保护", "HR 处理"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("boss", "coworker", "lawyer"),
        fact_lines=(
            "{self_name}遭直属上级{self_name}以升职为条件进行言语骚扰，已用手机录音并保存聊天记录，正咨询律师与 HR 举报流程",
            "{self_name}多次遭到上级不适当言语与肢体试探，同事愿意作证，其录音与微信记录已备份，准备正式投诉",
        ),
        user_lines=(
            "我把每次对话都录了音，聊天记录也导出了，这次我不会再忍",
            "我不缺那份升职，我缺的是能安心上班的环境",
        ),
        other_lines=(
            "boss>小同志，晚上陪领导吃个饭，这点面子都不给？以后有好机会还能想着你吗",
            "coworker>你千万别一个人去，我就在楼下等你，出什么事就给我发消息",
            "lawyer>录音如不侵犯他人合法权益可作为证据使用，投诉要选对主体，先做书面举报留痕",
        ),
        app_keys=(
            ("WeChat", "{boss}", "昨晚说的事考虑得怎么样？机会难得哦，别让我失望"),
            ("Email", "HR", "关于员工投诉的受理回执：已收到您的书面材料，将在{date}前启动调查"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "boss", "date"),
    ),
    EventFamily(
        fid="S04_CUSTODY_SNATCH",
        domain="dim:social",
        intent="CUSTODY_DISPUTE_FORCED_VISIT_RECORDS",
        keywords=("抚养权争夺", "抢夺孩子", "伪造探视记录", "拒绝交接", "报警调解", "变更抚养关系", "心理伤害"),
        severity="serious",
        sensor_hints=("S02", "S03"),
        roles=("ex_spouse", "officer", "child"),
        fact_lines=(
            "{self_name}与前配偶在{legal_place}门口因交接孩子发生抢夺，对方伪造探视记录并拒绝按协议交还，警方到场调解",
            "抚养权争夺升级：{self_name}的前配偶带着数人强行带走孩子，并伪造多次探视记录作为诉讼材料，已报警并申请变更抚养关系",
        ),
        user_lines=(
            "协议写得清清楚楚，周末归我，你凭什么在学校门口把孩子拽走",
            "别在孩子面前吵，行，那咱们去派出所把话说清楚",
        ),
        other_lines=(
            "ex_spouse>孩子不想见你，你自己看看这上面的记录，我什么时候拦过你",
            "officer>双方先冷静，孩子交留在现场的一方照看，谁对谁错到法院去说",
            "child>爸爸你别拉我胳膊，疼……我不想你们吵架",
        ),
        app_keys=(
            ("WeChat", "{ex_spouse}", "以后你别来学校了，孩子我接走了，想看孩子走法律程序"),
            ("CourtApp", "开庭通知", "您申请的变更抚养关系纠纷一案定于{date}在{legal_place}开庭审理"),
        ),
        dialect_fn="threat",
        entity_slots=("ex_spouse", "legal_place", "date"),
    ),
    EventFamily(
        fid="S05_INHERITANCE_WILL",
        domain="dim:social",
        intent="INHERITANCE_WILL_NOTARIZATION_DISPUTE",
        keywords=("遗产继承", "遗嘱公证", "多子女争吵", "房产分配", "赡养义务对抗", "公证现场冲突", "诉讼分割"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("child", "lawyer", "officer"),
        fact_lines=(
            "{self_name}在{legal_place}办理遗嘱公证时，多名子女就房产与存款分配当场争吵，公证员被迫中止程序并建议先行调解",
            "因遗产分配份额分歧，{self_name}的子女在公证处拍桌争执甚至推搡，公证程序中止，遗产分割或将进入诉讼",
        ),
        user_lines=(
            "我还没老糊涂，这房子给谁我心里有数，你们谁尽过孝谁自己清楚",
            "我活着呢，你们就为了这点东西在我面前吵成这样？",
        ),
        other_lines=(
            "child>爸，我们不是惦记钱，可这分配太不公平了，大哥家这些年拿得还少吗",
            "lawyer>遗嘱可以依法变更，但公证现场争吵影响不了立遗嘱人的真实意愿，建议先做家庭调解",
            "officer>这里是公共场所，谁再推搡我就按治安案件处理",
        ),
        app_keys=(
            ("WeChat", "家族群", "爸的遗嘱我不认，房子是妈留下的，凭什么多分给老二家"),
            ("BankApp", "大额提醒", "账户支取 {amount} 元，请注意核对交易对手与用途"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "legal_place"),
    ),
    EventFamily(
        fid="S06_ELDER_CARE_SHIRKING",
        domain="dim:social",
        intent="ELDERLY_CARE_DUTY_SHIRKING",
        keywords=("赡养推诿", "兄妹失和", "医疗费分摊", "轮流照护", "老人无助", "家庭会议", "法律义务"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("child", "doctor", "lawyer"),
        fact_lines=(
            "{self_name}住院需要陪护，几个子女就医疗费与陪护排班互相推诿，老人在病床上说出'别吵了我不治了'的话",
            "因{amount}医疗费分摊谈不拢，{self_name}的子女在病房走廊争吵，护理记录显示近一周无家属陪护签字",
        ),
        user_lines=(
            "你们别吵了，我这把年纪了，治不治都行，别为我把关系弄僵",
            "我谁也不怨，就是夜里想喝口水都没人递",
        ),
        other_lines=(
            "child>上次住院就是我出的钱，这次该轮到你们了吧",
            "doctor>老人需要家属签字确认治疗方案，费用和陪护得尽快定下来，拖着对病情不好",
            "lawyer>赡养义务是法定的，推诿不履行可以起诉，但老人更希望的是你们坐下来商量",
        ),
        app_keys=(
            ("WeChat", "家族群", "这{amount}的医药费到底怎么分？我先说好，我这边真拿不出这么多"),
            ("HospitalApp", "住院费用", "本次住院预计费用 {amount} 元，请于{date}前缴纳或确认医保结算方式"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "amount", "date"),
    ),
    EventFamily(
        fid="S07_DOMESTIC_VIOLENCE",
        domain="dim:social",
        intent="DOMESTIC_VIOLENCE_NEIGHBOR_REPORT",
        keywords=("家庭暴力", "邻居报警", "伤情鉴定", "人身安全保护令", "调解室", "反复发作", "孩子目睹"),
        severity="critical",
        sensor_hints=("S01", "S02"),
        roles=("spouse", "officer", "neighbor"),
        fact_lines=(
            "{self_name}因家庭矛盾被配偶推倒在地致手臂淤青，邻居听见砸物与哭喊后报警，警方出具告诫书并建议申请人身安全保护令",
            "邻里报警称{self_name}家中传出激烈争吵与撞击声，民警到场后发现其手腕有明显抓痕，案件已受理并做伤情鉴定",
        ),
        user_lines=(
            "没事没事，就是磕了一下……你们别管我们家的事",
            "孩子还在屋里，别吓着他，我求你们小点声",
        ),
        other_lines=(
            "neighbor>我听到砸东西的声音还有人在喊救命，实在不放心才报的警",
            "officer>手腕的抓痕我们拍照留档，要不要做伤情鉴定你自己定，但这已经是第二次出警了",
            "child>妈妈你别哭，我保护你……",
        ),
        app_keys=(
            ("SMS", "派出所", "您报称的家庭纠纷已出警处置，如需申请人身安全保护令可携带材料到法院立案窗口办理"),
            ("WeChat", "{neighbor}", "你家里还好吧？刚才动静太大了，要不要来我家躲一躲"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "spouse", "neighbor"),
    ),
    EventFamily(
        fid="S08_PET_DOG_INCIDENT",
        domain="dim:social",
        intent="PET_DOG_KNOCKED_DOWN_CHILD",
        keywords=("宠物犬伤人", "孩子摔倒", "两家冲突", "疫苗费用", "派出所调解", "饲养责任", "赔礼道歉"),
        severity="serious",
        sensor_hints=("S02",),
        roles=("neighbor", "officer", "child"),
        fact_lines=(
            "{self_name}饲养的犬只扑倒邻居幼童致其额头受伤，两家在小区门口激烈争吵，派出所介入调解并商定疫苗与医药费承担",
            "犬只未拴绳扑倒幼童引发两家冲突，{self_name}被要求承担{amount}医药与疫苗费用，双方在{legal_place}接受调解",
        ),
        user_lines=(
            "狗是我没拴绳，这点我认，但孩子是自己跑过来的，不能全算我的",
            "医药费我出，可你们张口就要{amount}，这不是讹人吗",
        ),
        other_lines=(
            "neighbor>我家孩子头上缝了三针，吓到现在不敢出门，你说怎么办吧",
            "officer>饲养动物致人损害原则上由饲养人承担责任，具体金额可以协商，医疗票据要留好",
            "child>小狗扑过来的时候我好害怕……",
        ),
        app_keys=(
            ("HospitalApp", "门诊收费", "儿童外伤清创缝合，疫苗及处置费合计 {amount} 元"),
            ("WeChat", "{neighbor}", "医药费票据我都发你了，另外孩子后续复查费用你也要负责"),
        ),
        dialect_fn="rebut",
        entity_slots=("neighbor", "amount", "legal_place"),
    ),
    EventFamily(
        fid="S09_WATER_LEAK_NEIGHBOR",
        domain="dim:social",
        intent="NEIGHBOR_WATER_LEAK_DISPUTE",
        keywords=("邻里漏水", "泡坏地板", "责任划分", "维修赔偿", "物业介入", "鉴定评估", "反复漏水"),
        severity="routine",
        sensor_hints=("S00",),
        roles=("neighbor", "officer"),
        fact_lines=(
            "{self_name}家水管渗漏泡坏楼下邻居天花板与地板，邻居索赔{amount}，双方对维修方案与责任划分争执不下并请物业介入",
            "因楼上防水失效反复渗水，{self_name}与邻居在楼道激烈争执，物业与社区调解员到场测量损失并协商赔偿",
        ),
        user_lines=(
            "修我肯定给修，可开口就{amount}，我总得看看票据和评估吧",
            "这事我也有责任，但不是全责，咱们讲道理行不行",
        ),
        other_lines=(
            "neighbor>你家漏了三次了！我家吊顶全泡了，这次不给{amount}我就去法院告你",
            "officer>损失金额以维修报价和照片为准，谈不拢可以申请第三方评估，别在楼道里吵",
            "neighbor>上次你说修好，结果一个月又漏，我怎么信你",
        ),
        app_keys=(
            ("WeChat", "{neighbor}", "照片都拍给你了，吊顶＋地板一共{amount}，你看什么时候转"),
            ("PropertyApp", "报修单", "您报修的地面渗水问题已转维修班组，预计{date}上门排查"),
        ),
        dialect_fn="rebut",
        entity_slots=("neighbor", "amount", "date"),
    ),
    EventFamily(
        fid="S10_MARITAL_ASSET_HIDDEN",
        domain="dim:social",
        intent="MARITAL_ASSET_HIDDEN_TRANSFER",
        keywords=("婚内转移财产", "隐匿存款", "低价过户", "离婚财产分割", "流水追查", "撤销权诉讼", "信任破裂"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("spouse", "lawyer", "child"),
        fact_lines=(
            "{self_name}发现配偶在离婚前将{amount}存款分批转给亲属并把车低价过户给表弟，律师建议提起撤销权诉讼并申请财产保全",
            "配偶隐匿转移婚内财产：{self_name}掌握大额转账与过户记录，涉及金额{amount}，正在{legal_place}办理调查取证",
        ),
        user_lines=(
            "钱是一起挣的，你转给你姐的时候怎么不跟我说一声",
            "我不想闹，但该我的一分都不能少，这是给孩子的",
        ),
        other_lines=(
            "spouse>那是我的工资卡，我想给谁就给谁，跟你有什么关系",
            "lawyer>离婚时转移隐匿共同财产可以少分或不分，我们先把流水调出来，再做保全",
            "child>你们能不能别吵了，我不想听这些",
        ),
        app_keys=(
            ("BankApp", "大额转账", "您账户转出 {amount} 元至『张桂英』，用途：借款"),
            ("CourtApp", "立案回执", "您申请的撤销权纠纷已立案，案号已生成，开庭时间另行通知"),
        ),
        dialect_fn="rebut",
        entity_slots=("spouse", "amount", "legal_place"),
    ),
    EventFamily(
        fid="S11_SCHOOL_BULLYING",
        domain="dim:social",
        intent="SCHOOL_BULLYING_PARENT_MEETING",
        keywords=("校园欺凌", "冷暴力", "家长会", "班主任约谈", "心理创伤", "要求道歉", "转学考虑"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("teacher", "child", "parent"),
        fact_lines=(
            "{self_name}的孩子长期被同学孤立辱骂，家长会上{self_name}与对方家长争吵并要求学校书面处理，孩子情绪崩溃拒绝上学",
            "校园冷暴力事件升级：{self_name}在{place}与班主任及对方家长对质，要求公开道歉与心理干预，否则考虑转学",
        ),
        user_lines=(
            "我孩子现在一进教室就发抖，你们说这是同学间的小矛盾？",
            "我不管谁对谁错，学校必须给出书面处理结果，还要有心理老师介入",
        ),
        other_lines=(
            "teacher>我们已经批评过那几个孩子了，但家长您也要理解，青春期孩子说话没轻重",
            "parent>我家孩子就是开个玩笑，你们非要说成欺凌，那我们以后不搭理他总行了吧",
            "child>他们把我的书扔进垃圾桶，还说全班都讨厌我……我不想去了",
        ),
        app_keys=(
            ("WeChat", "班级群", "{teacher}：关于最近孩子之间发生的事，请相关家长本周五下午到校沟通"),
            ("WeChat", "{child}", "妈，今天能不能别让我去学校，我真的很难受"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "child", "teacher"),
    ),
    EventFamily(
        fid="S12_HIDDEN_TERMINAL_CANCER",
        domain="dim:social",
        intent="FAMILY_HIDDEN_TERMINAL_CANCER",
        keywords=("瞒报病情", "癌症晚期", "独生子女", "异地奔波", "病情告知", "家庭抉择", "心理崩溃"),
        severity="critical",
        sensor_hints=("S00", "S03"),
        roles=("parent", "doctor", "spouse"),
        fact_lines=(
            "{self_name}发现父母隐瞒肺癌晚期诊断已三个月，得知真相后情绪崩溃，医生就后续治疗与告知方案与家属沟通",
            "父母瞒报癌症晚期病历：{self_name}在{legal_place}复印病历时发现诊断日期早在三个月前，家属在走廊痛哭并商量如何告知",
        ),
        user_lines=(
            "你们瞒着我三个月……我在外地加班的时候，你们在医院做化疗？",
            "我不怪你们，但这个家以后的事，得我们一起商量着来",
        ),
        other_lines=(
            "parent>别治了，花那冤枉钱干啥，你们日子还长着呢……我们商量好的不告诉你",
            "doctor>目前分期较晚，治疗方案有靶向和姑息两条路，需要家属共同决定，也要考虑患者的知情意愿",
            "doctor>老人怕拖累你们，但瞒下去会造成更大的遗憾，建议循序渐进地沟通",
        ),
        app_keys=(
            ("HospitalApp", "病理报告", "病理诊断：肺腺癌，分期 IV 期；报告日期{date}，请家属携证件领取"),
            ("WeChat", "{parent}", "儿啊，妈这两天挺好的，你放心忙工作，别往回跑了"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "parent", "doctor"),
    ),
)

_CAREER: Tuple[EventFamily, ...] = (
    EventFamily(
        fid="C01_LABOR_ARBITRATION",
        domain="dim:career",
        intent="LABOR_ARBITRATION_FAKE_ATTENDANCE",
        keywords=("劳动仲裁", "伪造考勤", "违法解除", "经济补偿金", "开庭对质", "证据造假", "裁决书"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("boss", "lawyer", "coworker"),
        fact_lines=(
            "{self_name}在{legal_place}仲裁开庭时遭遇公司伪造考勤记录，对方以旷工为由解除劳动合同，其钉钉打卡与门禁记录形成反证",
            "劳动仲裁庭审中公司提交的考勤表被当庭指认造假，{self_name}要求支付违法解除赔偿金与{amount}欠薪",
        ),
        user_lines=(
            "那三天的打卡记录我手机里都有，门禁监控也能调，你们表上写旷工不心虚吗",
            "我在公司干了四年，说要开就开，连个说法都不给",
        ),
        other_lines=(
            "boss>他连续旷工三天，公司按规定解除，考勤表就是证据",
            "lawyer>我们申请调取门禁记录与服务器登录日志，纸质考勤表存在明显改动痕迹",
            "coworker>那几天他明明在，我们还一起加班到十点，我可以作证",
        ),
        app_keys=(
            ("DingTalkApp", "考勤记录", "打卡记录导出：{date} 09:02 上班打卡成功（定位：公司园区）"),
            ("Email", "公司HR", "解除劳动合同通知书：因连续旷工三日，公司决定自{date}起解除劳动合同"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "legal_place", "date"),
    ),
    EventFamily(
        fid="C02_NON_COMPETE_LAWSUIT",
        domain="dim:career",
        intent="NON_COMPETE_200W_LAWSUIT",
        keywords=("竞业限制", "索赔两百万", "违约金畸高", "跳槽竞对", "补偿金未付", "诉讼保全", "协议效力"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("lawyer", "boss"),
        fact_lines=(
            "原公司以违反竞业限制为由向{self_name}索赔{amount}，但公司连续三个月未支付竞业补偿金，律师主张违约金畸高应予调整",
            "{self_name}跳槽至同业公司后被原东家起诉索赔{amount}违约金，其银行流水显示公司从未实际支付竞业限制补偿",
        ),
        user_lines=(
            "签的时候说每月给我补偿，到现在一分钱没见着，凭什么让我守约",
            "我一个普通员工，索赔{amount}，这不是要把人一辈子压死吗",
        ),
        other_lines=(
            "lawyer>三个月未支付补偿金，劳动者可以主张解除竞业限制义务，违约金也可以请求法院调减",
            "boss>{amount}是协议里白纸黑字写的，他带走的技术资料我们还没算呢",
            "lawyer>建议先保全证据，把流水与协议原件整理清楚，开庭时对补偿金支付情况重点质证",
        ),
        app_keys=(
            ("Email", "法务部", "关于{self_name}违反《竞业限制协议》的函告：请于{date}前支付违约金{amount}，否则将提起诉讼"),
            ("BankApp", "流水查询", "近六个月工资卡流水已生成：未发现竞业限制补偿金入账记录"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "lawyer", "date"),
    ),
    EventFamily(
        fid="C03_THESIS_BLIND_REVIEW",
        domain="dim:career",
        intent="THESIS_BLIND_REVIEW_REJECTION",
        keywords=("论文盲审", "大修意见", "导师决裂", "实验数据质疑", "延毕风险", "学术申诉", "心理压力"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("teacher", "coworker"),
        fact_lines=(
            "{self_name}的学位论文盲审被两位专家要求重大修改，导师又拒绝在申诉材料上签字，双方就实验数据归属发生决裂，面临延毕",
            "盲审结果重创{self_name}：专家质疑核心数据可重复性，导师在组会上公开批评并提出撤换一作，学生考虑申请学术委员会介入",
        ),
        user_lines=(
            "数据我一共重复了六次，原始记录都在硬盘里，凭什么说我造假",
            "延毕我认，但一作要是撤了，我这三年就白干了",
        ),
        other_lines=(
            "teacher>审稿意见很尖锐，你先按意见改，别再跟我提申诉的事",
            "coworker>你导师最近在和你师兄合作的那个课题上有点着急，你别正面顶他",
            "teacher>组里的资源不是给你一个人用的，你要是不服，可以去找学院",
        ),
        app_keys=(
            ("Email", "研究生院", "盲审结果通知：您的学位论文评审意见为『修改后重审』，请在{date}前提交修改说明"),
            ("WeChat", "{teacher}", "你那部分数据我让师弟重新跑一遍，结果对不上，你先自己想想问题出在哪"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "teacher", "date"),
    ),
    EventFamily(
        fid="C04_CIVIL_SERVICE_BACKFILL",
        domain="dim:career",
        intent="CIVIL_SERVICE_BACKFILL_POLITICAL_REVIEW",
        keywords=("公考递补", "政审突击", "档案缺失", "材料补交", "竞争激烈", "单位人事", "资格复审"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("officer", "parent"),
        fact_lines=(
            "{self_name}在国家公考面试递补进入考察环节，但政审时发现档案中缺少实习鉴定材料，需在{date}前补齐否则影响录用",
            "公考递补考察突发状况：{self_name}的档案因原单位合并丢失两份材料，人事部门要求限期补交并说明情况",
        ),
        user_lines=(
            "这么难得的机会，要是因为几张纸黄了，我真不知道该怎么跟家里说",
            "我明天一早就回原单位调档案，麻烦您给我留个联系方式",
        ),
        other_lines=(
            "officer>材料必须在{date}前送到，我们只能按程序走，通融不了",
            "parent>儿子，要不托托人？咱家也没别的门路啊……",
            "officer>实习鉴定可以让原单位补开证明，档案缺失的要有情况说明并盖公章",
        ),
        app_keys=(
            ("SMS", "组织部人事科", "您好，关于您的考察材料补充事项，请于{date}前将缺失材料送至我处，逾期视为放弃"),
            ("WeChat", "{parent}", "你爸想去问问你舅，他在县里认识人，你看行不行"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "officer", "date", "parent"),
    ),
    EventFamily(
        fid="C05_CUSTOMS_SEIZURE_LC",
        domain="dim:career",
        intent="CUSTOMS_SEIZURE_LC_CRISIS",
        keywords=("海关查扣", "信用证拒付", "单证不符", "滞港费用", "客户催货", "报关行交涉", "资金链危机"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("lawyer", "client", "supplier"),
        fact_lines=(
            "{self_name}的核心外贸订单被海关以申报要素不符查扣，信用证因单证不符面临拒付，滞港费每天累积，客户要求{date}前交货",
            "出口货物在口岸被查扣，{amount}信用证存在不符点，{self_name}紧急联系报关行与银行改单，否则将承担违约赔偿",
        ),
        user_lines=(
            "这批货卡在码头一天就是好几千的滞港费，我这边真扛不住了",
            "信用证要是拒付，我前期的料款全打水漂",
        ),
        other_lines=(
            "client>我们合同写的是{date}到港，晚了我们就转单，违约金照合同走",
            "lawyer>先申请改单，再和开证行沟通不符点接不接受，同时把保险和不可抗力条款看清楚",
            "supplier>料款你答应这个月结的，别又拖，我这边也要发工资",
        ),
        app_keys=(
            ("Email", "报关行", "您的货物因申报要素不符被海关布控查验，请补充成分说明与检测报告，否则无法放行"),
            ("BankApp", "信用证通知", "境外开证行提出不符点：单据日期早于装运日期，暂缓付款，请尽快处理"),
        ),
        dialect_fn="money",
        entity_slots=("self_name", "amount", "date", "client"),
    ),
    EventFamily(
        fid="C06_LAYOFF_LIST",
        domain="dim:career",
        intent="LAYOFF_OPTIMIZATION_LIST",
        keywords=("裁员优化", "名单泄露", "N+1 补偿", "被迫签自愿离职", "谈话施压", "劳动仲裁", "再就业焦虑"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("boss", "coworker", "lawyer"),
        fact_lines=(
            "{self_name}被列入优化名单，HR 要求其当天签署『个人原因自愿离职』，{self_name}拒绝并主张 N+1 补偿与未休年假折算",
            "公司裁员谈话中{self_name}被施压签自愿离职协议，其已录音并咨询律师，坚持要求出具书面解除通知与{amount}补偿",
        ),
        user_lines=(
            "让我签自愿离职，那我失业金都拿不到，这话你们也说得出口",
            "该我的 N+1 补偿我一分不会让，不给就仲裁，我耗得起",
        ),
        other_lines=(
            "boss>公司也很难，你签个自愿离职，我们给你多算半个月，大家好聚好散",
            "lawyer>不要签自愿离职，让他们发书面解除通知，补偿标准按工作年限算，主动离职没有经济补偿",
            "coworker>名单我昨天就在小群里看到了，你自己早做打算吧",
        ),
        app_keys=(
            ("WeChat", "{coworker}", "名单出来了，你在上面，明天HR找你谈，你要提前想好怎么说"),
            ("Email", "HR", "关于岗位优化的沟通通知：请于{date}到会议室签署相关离职文件"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "date", "coworker"),
    ),
    EventFamily(
        fid="C07_WORK_INJURY_DISPUTE",
        domain="dim:career",
        intent="WORK_INJURY_RECOGNITION_DISPUTE",
        keywords=("工伤认定", "高空坠落", "未缴社保", "包工头甩责", "伤残鉴定", "仲裁诉讼", "医疗费垫付"),
        severity="critical",
        sensor_hints=("S01",),
        roles=("boss", "coworker", "lawyer"),
        fact_lines=(
            "工人在作业面坠落受伤，{self_name}因未给工人缴纳社保被要求承担全部{amount}医疗与伤残赔偿，工伤认定申请正在提交",
            "{self_name}的班组发生高空坠落事故，发包方以『无劳动关系』推责，律师建议先做工伤认定再确定赔付主体",
        ),
        user_lines=(
            "人是从我这儿上的工，这个责任我认，可总包方也得拿出说法",
            "医药费我先垫了一半，剩下的我实在拿不出来了",
        ),
        other_lines=(
            "boss>他自己没系安全带，我们总包方没有直接用工，赔偿找包工头去",
            "coworker>当时安全绳是坏的，我提醒过换新的，没人管",
            "lawyer>先申请工伤认定，同时保全现场照片和工资发放记录，用工主体责任跑不掉",
        ),
        app_keys=(
            ("HospitalApp", "急诊记录", "高处坠落伤患者：多发肋骨骨折、脾挫伤，已行急诊手术，预估费用{amount}元"),
            ("WeChat", "{boss}", "工人的事你先处理，合同里写了安全责任由你负责，别把事往公司引"),
        ),
        dialect_fn="threat",
        entity_slots=("self_name", "amount", "boss"),
    ),
    EventFamily(
        fid="C08_PROMOTION_REVIEW",
        domain="dim:career",
        intent="TITLE_PROMOTION_REVIEW_REJECTED",
        keywords=("职称评审", "材料被刷", "名额限制", "暗箱操作质疑", "补充材料", "申诉复核", "职业挫败"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("officer", "coworker"),
        fact_lines=(
            "{self_name}的职称评审在公示阶段被刷下，理由是获奖级别不达标，其质疑同批次存在名额内定，已申请复核",
            "职称评审未通过：{self_name}的材料在最后一轮被刷，单位人事称名额按比例压减，{self_name}准备补充材料申请复核",
        ),
        user_lines=(
            "我准备了两年的材料，一晚上就被刷了，连个具体理由都不给",
            "我不闹，我就想知道差在哪儿，差哪补哪儿",
        ),
        other_lines=(
            "officer>今年指标压减，评审结果是集体投票决定的，你可以按规定申请复核",
            "coworker>听说那两个名额早就定好了，你别太较真，明年再来",
            "officer>补充材料要在{date}前提交，过期视为放弃复核",
        ),
        app_keys=(
            ("Email", "人事处", "职称评审结果公示：经评审委员会投票，您未通过本次评审，如有异议请于{date}前提交复核申请"),
            ("WeChat", "{coworker}", "结果出来了吧？别灰心，这种事你懂的，明年再说"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "officer", "date"),
    ),
    EventFamily(
        fid="C09_MEDICAL_DISPUTE_ASSAULT",
        domain="dim:career",
        intent="MEDICAL_DISPUTE_ASSAULT",
        keywords=("医疗纠纷", "推搡冲突", "监控取证", "医患沟通", "报警处置", "执业保护", "情绪安抚"),
        severity="serious",
        sensor_hints=("S02", "S03"),
        roles=("patient_family", "officer", "coworker"),
        fact_lines=(
            "{self_name}在急诊与患者家属因抢救结果发生争执并被推搡撞到分诊台，医院启动纠纷处置程序并报警调取监控",
            "患者家属情绪失控推搡{self_name}并砸坏护士站物品，警方到场调取监控固定证据，医院同步启动医患沟通与心理疏导",
        ),
        user_lines=(
            "人我们已经尽力了，你怎么能动手，我们这儿还有别的病人在抢救",
            "我可以跟你解释病情，但请你把手放下，退一步说话",
        ),
        other_lines=(
            "patient_family>你们是医生啊！人进来的时候还活着，怎么就没救过来！",
            "officer>现场监控我们调取了，动手的部分请配合调查，医疗责任可以通过医调委解决",
            "coworker>李医生你没事吧？腰撞到台子上了，赶紧去做个检查",
        ),
        app_keys=(
            ("WeChat", "科室群", "急诊分诊台有家属情绪失控并推了李医生，大家先别围观，让保安和警方处理"),
            ("HospitalApp", "纠纷上报", "医疗纠纷事件已上报：涉及暴力行为，已报警并保全监控录像"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "officer"),
    ),
    EventFamily(
        fid="C10_OVERLOAD_LICENSE",
        domain="dim:career",
        intent="OVERLOAD_FINE_LICENSE_SUSPENSION",
        keywords=("超载罚款", "营运证暂扣", "路政执法", "扣分处理", "复议申辩", "生计中断", "挂靠车队"),
        severity="serious",
        sensor_hints=("S00", "S05"),
        roles=("officer", "boss"),
        fact_lines=(
            "{self_name}因车辆超载被路政处以{amount}罚款并暂扣营运证，车队老板拒绝承担罚款，其营收中断并考虑申请行政复议",
            "超限检查中{self_name}的货车被认定超载，营运证暂扣{date}，车主与挂靠公司就罚款与停运损失互相推诿",
        ),
        user_lines=(
            "货是车队给装的，装多装少我哪知道，罚款凭什么全落我头上",
            "营运证一扣，我一个月的车贷拿什么还",
        ),
        other_lines=(
            "officer>过磅单在这儿，超限百分之三十，罚款和暂扣都是按规定来的",
            "boss>装货单上你签了字的，现在跟我说不知道？罚款你自己想办法",
            "officer>对处罚有异议可以在期限内申请行政复议，材料我们给你出份清单",
        ),
        app_keys=(
            ("SMS", "路政执法", "您的车辆因超限运输被处以罚款{amount}元，营运证暂扣，请于{date}前到窗口办理"),
            ("WeChat", "{boss}", "罚款的事你别找我，公司不承担司机违规，你自己认了吧"),
        ),
        dialect_fn="threat",
        entity_slots=("self_name", "amount", "officer", "date"),
    ),
    EventFamily(
        fid="C11_PLATFORM_BAN_APPEAL",
        domain="dim:career",
        intent="PLATFORM_STORE_BAN_APPEAL",
        keywords=("平台封店", "违规判定", "申诉材料", "保证金冻结", "库存积压", "团队工资", "合规整改"),
        severity="serious",
        sensor_hints=("S00", "S03"),
        roles=("lawyer", "coworker", "partner"),
        fact_lines=(
            "{self_name}的电商店铺被判违规封停，{amount}货款与保证金被冻结，团队工资与供应商货款即将断链，正在准备申诉与合规整改",
            "平台以涉嫌刷单为由封停{self_name}的店铺，申诉窗口仅剩{date}，其聘请律师梳理交易凭证并安抚团队",
        ),
        user_lines=(
            "每一单都是真实发货，物流号都能对上，凭什么说我刷单",
            "申诉材料我今天就交，团队那边我得先稳住",
        ),
        other_lines=(
            "lawyer>先把三个月订单的物流、聊天、收款记录整理成证据包，申诉和诉讼两条路都留着",
            "coworker>仓库还有两批货压着，供应商开始催了，我们要不要先接点代发",
            "partner>账上的钱只够发这个月工资，下个月就得想别的办法了",
        ),
        app_keys=(
            ("Email", "平台风控", "您的店铺因涉嫌违规交易被限制经营，请于{date}前提交申诉材料，逾期将执行清退"),
            ("BankApp", "商户资金", "账户资金 {amount} 元已被平台冻结，解冻时间以平台通知为准"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "date", "partner"),
    ),
    EventFamily(
        fid="C12_EMBEZZLEMENT_AUDIT",
        domain="dim:career",
        intent="EMBEZZLEMENT_AUDIT_INVESTIGATION",
        keywords=("专项审计", "挪用公款", "配合调查", "账目缺口", "责任人认定", "停职检查", "家庭压力"),
        severity="serious",
        sensor_hints=("S03", "S00"),
        roles=("officer", "lawyer", "spouse"),
        fact_lines=(
            "{self_name}被要求配合{amount}资金缺口的专项审计并暂停职务，其坚持资金流向系领导指示，已委托律师并整理审批记录",
            "审计组发现{self_name}经手的{amount}款项流向关联公司，{self_name}提供审批链与邮件记录自证，家庭因此陷入紧张",
        ),
        user_lines=(
            "每一笔钱出境都有审批单，我按流程签的字，凭什么让我一个人担",
            "我是被停职了，但我没做过的事，我一个字都不会认",
        ),
        other_lines=(
            "officer>请你如实说明这{amount}的用途，同时把审批邮件和相关会议纪要提供给我们",
            "lawyer>配合调查要如实，但只说自己知道的部分，别替别人扛，也别乱说",
            "spouse>孩子在学校的费用怎么办？你要真出了事，这个家就散了",
        ),
        app_keys=(
            ("Email", "审计组", "关于{amount}资金流向的说明要求：请于{date}前提交审批记录及关联公司往来凭证"),
            ("WeChat", "{spouse}", "家里人都问我怎么回事，你倒是说句话啊，你被停职的事要瞒到什么时候"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "amount", "officer", "date"),
    ),
)


_LIFE: Tuple[EventFamily, ...] = (
    EventFamily(
        fid="L01_RENTAL_BACKFLOW",
        domain="dim:life",
        intent="RENTAL_BACKFLOW_DAMAGE_CLAIM",
        keywords=("下水倒灌", "污水浸泡", "贵重物品受损", "房东拒赔", "物业推诿", "损失评估", "租房索赔"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("landlord", "officer", "neighbor"),
        fact_lines=(
            "租住房屋下水管道倒灌，{self_name}的一批贵重物品被污水浸泡，初步损失{amount}，房东与物业互相推诿，其准备走法律途径索赔",
            "深夜下水道返水涌入房间，{self_name}价值{amount}的物品和地板全被泡毁，物业称主管道堵塞责任在楼上住户",
        ),
        user_lines=(
            "我回来一开门，地上一层黑水漂着东西，味道冲得人想吐",
            "东西是你们房子的管道堵的，损失凭什么要我自己扛",
        ),
        other_lines=(
            "landlord>房子我是租给你的，管道堵塞你也用了，责任不能全算我的",
            "officer>先把现场拍照、列损失清单，主责在哪要专业疏通报告来定，谈不拢可以起诉",
            "neighbor>这栋楼的主管道堵了小半年了，物业一直没彻底通",
        ),
        app_keys=(
            ("WeChat", "{landlord}", "我看了照片，损失最多赔你一半，你要是不认就打官司吧"),
            ("PropertyApp", "报修工单", "您的管道返水报修已受理，疏通班组到场后发现主管道堵塞严重，需楼栋协同处理"),
        ),
        dialect_fn="money",
        entity_slots=("self_name", "amount", "landlord"),
    ),
    EventFamily(
        fid="L02_FLOODED_CAR_REFUND",
        domain="dim:life",
        intent="FLOODED_CAR_THIRD_PARTY_INSPECTION",
        keywords=("事故车隐瞒", "泡水车退车", "第三方检测", "检测实锤", "上门维权", "三倍赔偿", "销售欺诈"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("merchant", "officer", "lawyer"),
        fact_lines=(
            "第三方检测报告实锤{self_name}买的二手车为泡水事故车，{self_name}带检测报告上门要求退车并主张{amount}三倍赔偿",
            "二手车商隐瞒泡水历史，{self_name}提车后查出线路锈蚀与泥沙残留，检测机构出具报告后其在车行门口维权",
        ),
        user_lines=(
            "买的时候你拍胸脯说一手的车没出过事，现在检测报告白纸黑字写着泡水",
            "退车要么三倍赔，要么咱们去{legal_place}见，我天天来",
        ),
        other_lines=(
            "merchant>车况我卖的时候就说过是二手，有点小磕碰很正常，你这报告我不认",
            "lawyer>销售方隐瞒重大瑕疵构成欺诈，可以主张退一赔三，检测报告与聊天记录都要留好",
            "officer>双方先别动手，退车和赔偿按合同和法律走，我们只维持现场秩序",
        ),
        app_keys=(
            ("WeChat", "{merchant}", "这车开着有点怪，你说的是小磕碰，怎么人家检测说泡过水？"),
            ("CarApp", "检测报告", "检测结论：涉水等级 B 级，驾驶舱地板线束锈蚀、安全带根部泥沙残留，判定为泡水车"),
        ),
        dialect_fn="threat",
        entity_slots=("self_name", "amount", "merchant", "legal_place"),
    ),
    EventFamily(
        fid="L03_OVERSEAS_ACCIDENT",
        domain="dim:life",
        intent="OVERSEAS_DRIVING_ACCIDENT_LANGUAGE_BARRIER",
        keywords=("境外自驾", "车祸求救", "语言不通", "租车保险", "当地警方", "使领馆协助", "医疗转运"),
        severity="critical",
        sensor_hints=("S01", "S05"),
        roles=("officer", "stranger", "doctor"),
        fact_lines=(
            "{self_name}在境外自驾时发生侧翻事故，因语言不通无法向当地警方说明情况，靠翻译软件与使领馆协助送医并处理保险",
            "境外公路翻车事故：{self_name}与同行人受伤被困，报警电话沟通不畅，最终通过使馆热线与租车公司救援协调送医",
        ),
        user_lines=(
            "Hello……accident……need ambulance，please……（夹杂中文）我腿动不了了",
            "谁能帮我说一句我们的位置，导航上是一条山路",
        ),
        other_lines=(
            "stranger>Sorry? I can't understand… wait, I'll call the police for you",
            "officer>Stay calm, keep your hazard lights on, help is coming in about 15 minutes",
            "doctor>Ribs and forearm fractures, we need to transfer you to the city hospital",
        ),
        app_keys=(
            ("SMS", "领保热线", "您的求助已受理，请保持手机畅通，我们将联系当地警方与翻译志愿者，另请留意保险报案电话"),
            ("CarApp", "租车订单", "您的车辆已触发紧急救援流程，救援车辆预计 20 分钟抵达定位点"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "doctor", "place"),
    ),
    EventFamily(
        fid="L04_GAS_FORGOTTEN",
        domain="dim:life",
        intent="FORGOTTEN_GAS_VALVE_ALARM",
        keywords=("煤气忘关", "燃气报警", "独居风险", "邻居敲门", "燃气公司上门", "一氧化碳中毒", "开窗通风"),
        severity="critical",
        sensor_hints=("S00", "S03"),
        roles=("neighbor", "officer", "child"),
        fact_lines=(
            "{self_name}忘记关闭煤气阀门，燃气报警器持续报警并触发邻居敲门，燃气公司上门切断阀门并开窗通风，避免了中毒事故",
            "深夜家中燃气浓度报警，{self_name}因记忆力问题忘记关火，邻居闻到异味后报警，燃气公司检测后更换了软管与阀门",
        ),
        user_lines=(
            "我就去楼下扔了个垃圾……锅还在灶上呢，我这记性真是完了",
            "谢谢你们啊，要不是你们我今天就交代在屋里了",
        ),
        other_lines=(
            "neighbor>你家门口一股煤气味，我敲门没人应，吓得我赶紧打了燃气公司和 119",
            "officer>软管都老化了，阀门也没关，这种情况建议装个燃气报警联动阀",
            "child>妈，以后出门前你再检查一遍，客厅那把椅子先别挪开",
        ),
        app_keys=(
            ("SMS", "燃气公司", "您家燃气报警已解除，检测发现软管老化，建议更换金属波纹管，维修预约请回电"),
            ("WeChat", "{child}", "妈，邻居给我打电话了，你没事吧？我明天回去给你装个自动断气的阀"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "neighbor", "child"),
    ),
    EventFamily(
        fid="L05_FIRE_EVACUATION",
        domain="dim:life",
        intent="FIRE_EVACUATION_EBIKE_CHARGING",
        keywords=("火灾疏散", "楼道起火", "电动车充电", "浓烟逃生", "消防到场", "责任追查"),
        severity="critical",
        sensor_hints=("S02", "S03"),
        roles=("neighbor", "officer", "child"),
        fact_lines=(
            "楼道内电动车充电起火，{self_name}家在浓烟中紧急疏散，消防到场后扑灭火情并追查违规充电责任人",
            "凌晨楼栋起火：{self_name}抱着老人从楼梯撤离，消防通报起火原因为一楼违规停放电动车充电",
        ),
        user_lines=(
            "烟一下子全灌进来了，我扶着老人往下走，什么都看不见",
            "谁家天天把电池拎上楼充电，这下好了吧",
        ),
        other_lines=(
            "neighbor>三楼还有人没下来！快点快点，消防车已经到楼下了！",
            "officer>所有人先到楼下集合，逐户清点人数，楼里暂时不能回",
            "child>妈妈我害怕……我们的猫还在里面",
        ),
        app_keys=(
            ("PropertyApp", "紧急通知", "本栋楼因火情实施临时封闭，请住户到楼下广场集合清点人数，勿乘电梯返回"),
            ("SMS", "消防支队", "您好，本小区昨晚火情已扑灭，起火原因初步认定为电动车违规充电，请配合调查登记"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "neighbor", "child"),
    ),
    EventFamily(
        fid="L06_ELEVATOR_ENTRAPMENT",
        domain="dim:life",
        intent="ELEVATOR_ENTRAPMENT_RESCUE",
        keywords=("电梯困人", "应急对讲失效", "密闭恐慌", "物业延误", "维保公司", "被困时长", "投诉索赔"),
        severity="serious",
        sensor_hints=("S03", "S00"),
        roles=("officer", "neighbor", "child"),
        fact_lines=(
            "{self_name}被困老旧小区电梯近{amount}分钟，应急对讲失灵，物业延迟响应，获救后出现明显恐慌并考虑投诉追责",
            "电梯突发停运困住{self_name}与同乘老人，维保人员超时未到，消防破拆后脱困，物业被要求整改并公示维保记录",
        ),
        user_lines=(
            "按了对讲没反应，手机也没信号，我敲了半小时门才有人听见",
            "里面还有一个老人，他本来就心脏不好，你们物业到底在干什么",
        ),
        other_lines=(
            "officer>维保人员还有多久到？超过 30 分钟我们就破拆，出现后果物业承担",
            "neighbor>我在楼道里听到有人喊，就赶紧打你们电话了，快点啊",
            "child>妈妈你别拍门了，我耳朵疼……",
        ),
        app_keys=(
            ("PropertyApp", "工单记录", "您的电梯困人报修已派单，维保单位预计 40 分钟到场，请保持联系"),
            ("SMS", "市场监管", "您反映的电梯困人问题已受理，我们将核查维保记录与应急联系电话有效性"),
        ),
        dialect_fn="threat",
        entity_slots=("self_name", "amount", "officer"),
    ),
    EventFamily(
        fid="L07_RAINSTORM_FLOOD",
        domain="dim:life",
        intent="RAINSTORM_FLOOD_EVACUATION",
        keywords=("暴雨内涝", "积水漫进", "紧急转移", "断电避险", "财产抢救", "救援求助", "低洼地带"),
        severity="critical",
        sensor_hints=("S05", "S02"),
        roles=("officer", "neighbor", "child"),
        fact_lines=(
            "暴雨导致内涝，{self_name}所住低洼地带积水没到小腿，与邻居合力转移老人与贵重财物并向救援队求助",
            "短时强降雨造成小区内涝，{self_name}背起老人向高层转移，地下车库车辆被淹，损失预估{amount}",
        ),
        user_lines=(
            "水涨得太快了，十分钟就到膝盖了，先把我妈背上去",
            "车还在车库呢，没办法了，人命要紧",
        ),
        other_lines=(
            "officer>所有住户往三楼以上转移，别坐电梯，电已经切了！",
            "neighbor>楼下那个坐轮椅的老爷子还在屋里，我们一起去抬",
            "child>爸爸，我的书包还在水里漂着呢……",
        ),
        app_keys=(
            ("SMS", "应急管理局", "全区暴雨红色预警，请低洼区域群众立即转移至安全地带，非必要不外出"),
            ("PropertyApp", "紧急通知", "地下车库已进水，请车主立即将车辆转移至地面或高架，物业已联系抽水抢险队"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "amount", "officer"),
    ),
    EventFamily(
        fid="L08_SNOW_DISASTER_LIVESTOCK",
        domain="dim:life",
        intent="SNOW_DISASTER_LIVESTOCK_LOSS_REPORT",
        keywords=("雪灾", "封路失联", "羊群冻损", "报灾申请", "帐篷压塌", "救灾物资", "防疫处理"),
        severity="critical",
        sensor_hints=("S05", "S00"),
        roles=("officer", "neighbor", "child"),
        fact_lines=(
            "暴雪封路三天，{self_name}的帐篷被压塌、羊群冻损大半，通过卫星电话向乡政府报灾并申请救灾物资与保险理赔",
            "牧区遭遇雪灾：{self_name}家断粮断药，乡政府组织铲雪开路送来草料与降压药，冻损牲畜数量正在统计上报",
        ),
        user_lines=(
            "雪压塌了帐篷，羊死了一半，路断了三天，连电话都打不出去",
            "我的降压药只剩两片了，先救人再管羊吧",
        ),
        other_lines=(
            "officer>我们已经在铲雪了，铲车到你们牧点大概还需要两个小时，草料跟着车走",
            "neighbor>我这边也塌了，几家人能不能先集中到冬窝子里避一避",
            "child>阿妈，羊羔还有几只活着，我抱到帐篷里了",
        ),
        app_keys=(
            ("SMS", "应急广播", "暴雪橙色预警：牧区道路封闭，请就近集中安置，有人员伤病或牲畜损失的拨打求助电话"),
            ("InsuranceApp", "报灾受理", "您提交的雪灾牲畜损失报案已受理，查勘员将在道路抢通后上门核查"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "officer", "neighbor"),
    ),
    EventFamily(
        fid="L09_PET_CRITICAL_CARE",
        domain="dim:life",
        intent="PET_CRITICAL_ILLNESS_TREATMENT_DISPUTE",
        keywords=("宠物重病", "腹膜炎", "治疗费用争议", "放弃或抢救", "宠物医院", "费用告知", "安乐抉择"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("vet", "friend", "spouse"),
        fact_lines=(
            "{self_name}的猫被诊断重度腹膜炎，宠物医院告知需{amount}治疗费用且不保证成活，双方就治疗方案与费用发生争执",
            "宠物猫病情恶化确诊传染性腹膜炎：{self_name}在抢救与安乐之间艰难抉择，并质疑医院此前延误诊断",
        ),
        user_lines=(
            "治，钱我想办法，只要还有一点希望我就试试",
            "你们上次说只是肠胃炎，现在怎么就成了腹膜炎了……",
        ),
        other_lines=(
            "vet>腹膜炎死亡率很高，治疗方案有两套，费用{amount}左右，你要有心理准备，我们也会尽全力",
            "friend>你已经尽力了，别把自己逼太紧，能治到什么程度算什么程度",
            "spouse>存款本来就不多了，你确定要全砸在这只猫身上吗",
        ),
        app_keys=(
            ("PetApp", "检查报告", "腹部超声：腹腔大量积液，冠状病毒阳性，考虑传染性腹膜炎，建议住院治疗，预估费用{amount}元"),
            ("WeChat", "{vet}", "猫咪情况有变化，今晚需要加一次输液，费用明天结算，你方便来接吗"),
        ),
        dialect_fn="plead",
        entity_slots=("self_name", "amount", "vet"),
    ),
    EventFamily(
        fid="L10_PIPE_FREEZE_BURST",
        domain="dim:life",
        intent="PIPE_FREEZE_BURST_WATER_DAMAGE",
        keywords=("管道冻裂", "喷水淹屋", "停水维修", "物业责任", "家具泡水", "极寒天气", "保险理赔"),
        severity="serious",
        sensor_hints=("S05", "S00"),
        roles=("landlord", "officer", "neighbor"),
        fact_lines=(
            "极寒天气导致水管冻裂，{self_name}家中家具被淹损失{amount}，物业与房东就维修与赔偿责任互相推诿",
            "水表后管道夜间冻裂喷水，{self_name}屋内积水数厘米，木地板与沙发泡毁，正在申请保险与追责",
        ),
        user_lines=(
            "半夜听见哗哗响，起来一看水都漫到脚脖子了",
            "天冷是老天的责任，可管道是你们房子的，损失总得有人管吧",
        ),
        other_lines=(
            "landlord>我人在外地，你先找物业关总阀，赔偿的事后面再谈",
            "officer>先把现场拍照留证，冻裂部位和维保记录是关键，谈不拢可以走诉讼",
            "neighbor>我家也冻裂了，这栋楼今年冬天已经第二次了",
        ),
        app_keys=(
            ("PropertyApp", "维修工单", "您的冻裂管道抢修已完成，水表后管段由业主自行承担，公共管段可申请物业保修"),
            ("InsuranceApp", "报案受理", "家庭财产综合险报案已受理，查勘员将在{date}上门核定水浸损失"),
        ),
        dialect_fn="money",
        entity_slots=("self_name", "amount", "landlord", "date"),
    ),
    EventFamily(
        fid="L11_THEFT_EBIKE_GOODS",
        domain="dim:life",
        intent="EBIKE_OR_GOODS_THEFT_REPORT",
        keywords=("电瓶车被盗", "监控死角", "立案受理", "生计工具", "平台赔付", "二手市场追查", "夜班风险"),
        severity="serious",
        sensor_hints=("S00", "S02"),
        roles=("officer", "coworker", "landlord"),
        fact_lines=(
            "{self_name}的电瓶车在楼下被盗，监控存在死角，报警立案后其为维持生计只能先租车跑单，同时联系平台申诉赔付",
            "送单用的电动车被撬锁偷走，{self_name}当晚无法接单，警方已调取周边监控并立案，同事自发帮忙寻找",
        ),
        user_lines=(
            "车是贷款买的，刚还完三期，现在连工具都没了",
            "我这一晚上白跑了，还得赔超时的钱……",
        ),
        other_lines=(
            "officer>监控拍到了两个戴头盔的人，车牌看不清，我们先立案，你要是看到可疑车辆随时联系",
            "coworker>我家里有辆旧车你先骑着，别耽误接单，赔偿的事慢慢说",
            "landlord>车停楼下丢了我不负责，小区监控也不是我装的",
        ),
        app_keys=(
            ("RiderApp", "装备管理", "您的车辆定位已离线超过 6 小时，如遇丢失请及时报警并在平台申请装备赔付"),
            ("SMS", "派出所", "您报称的电瓶车被盗已立案，案号已生成，请留意后续调查进展"),
        ),
        dialect_fn="threat",
        entity_slots=("self_name", "officer", "coworker"),
    ),
    EventFamily(
        fid="L12_FOOD_SAFETY_SAMPLING",
        domain="dim:life",
        intent="FOOD_SAFETY_SAMPLING_FAILURE",
        keywords=("食品抽检", "不合格通报", "停业整改", "顾客投诉", "供应商责任", "复检申请", "门店声誉"),
        severity="serious",
        sensor_hints=("S00",),
        roles=("officer", "supplier", "coworker"),
        fact_lines=(
            "{self_name}的门店被市场监管抽检发现餐具大肠菌群超标并收到不合格通报，责令停业整改，其将责任部分追溯至供应商食材",
            "食品安全抽检不合格：{self_name}的店铺被要求在{date}前完成整改并公示，供应商拒绝承担食材责任，营收大幅下滑",
        ),
        user_lines=(
            "餐具我天天消毒，谁抽检不合格我最清楚，可食材是你们供的",
            "整改我配合，但停业这几天房租工人工资谁给我出",
        ),
        other_lines=(
            "officer>整改报告要在{date}前提交，复检合格才能恢复营业，这期间不得对外供餐",
            "supplier>食材每批都有检疫合格证，你这问题多半出在餐具消毒环节，别赖我",
            "coworker>老板，隔壁店已经在门口发传单说我们家不干净了",
        ),
        app_keys=(
            ("SMS", "市场监管", "你单位在本次监督抽检中餐具大肠菌群项目不合格，请于{date}前完成整改并提交书面报告"),
            ("WeChat", "{coworker}", "今天又有两桌客人问抽检的事，我按你说的没多解释，你先想想怎么应对吧"),
        ),
        dialect_fn="rebut",
        entity_slots=("self_name", "officer", "date", "supplier"),
    ),
)


EVENT_FAMILIES: Dict[str, Tuple[EventFamily, ...]] = {
    "dim:health": _HEALTH,
    "dim:finance": _FINANCE,
    "dim:social": _SOCIAL,
    "dim:career": _CAREER,
    "dim:life": _LIFE,
}


def all_families() -> Tuple[EventFamily, ...]:
    """返回全部事件族（供覆盖率审计与测试使用）。"""

    families: list[EventFamily] = []
    for domain in DOMAIN_IDS:
        families.extend(EVENT_FAMILIES[domain])
    return tuple(families)


def family_index() -> Dict[str, EventFamily]:
    """fid -> EventFamily 映射。"""

    return {fam.fid: fam for fam in all_families()}


# 地区别名（佩戴者档案里出现的城市键 -> 已定义的地点库键）
for _alias, _target in (("guangzhou", "cantonese"), ("chengdu", "sichuan"), ("wuhan", "hubei"),
                        ("tibet_plateau", "tibet_plateau")):
    if _alias not in PLACE_BANK and _target in PLACE_BANK:
        PLACE_BANK[_alias] = PLACE_BANK[_target]


# --------------------------------------------------------------------------------------
# 修辞陷阱的"标准事实"（供出题侧生成方向性标答；大模型必须识破字面伪装）
# --------------------------------------------------------------------------------------
RHETORIC_FACTS: Dict[str, Dict[str, object]] = {
    "irony_true": {
        "dimension": None,  # 跟随主事件域
        "intent": "IRONIC_DEFAULT_ACCUSATION",
        "keywords": ("反讽", "正话反说", "严重违约", "讨债控诉", "表里不一", "按反义理解"),
        "fact_lines": (
            "{self_name}用反讽口吻控诉对方严重违约：说好{date}前还钱却人钱两失、电话拉黑，表层是夸奖实为债务违约催讨",
            "{self_name}的『你可真守信用』属正话反说，真实语义是对方长期拖欠{amount}拒不履行承诺，属于严重违约事实",
        ),
    },
    "stoic_critical": {
        "dimension": "dim:health",
        "intent": "CRITICAL_SIGNS_UNDERSTATED_BY_PATIENT",
        "keywords": ("急性脑卒中先兆", "心梗先兆", "假装坚强", "淡化病情", "必须立即送医", "黄金抢救时间窗"),
        "fact_lines": (
            "{self_name}刻意淡化病情说『别大惊小怪』，但自述眼前发黑、舌头发麻、单侧肢体无力，属于急性脑卒中/心梗先兆，必须立即送医",
            "{self_name}嘴上说没事且拒绝叫救护车，实际已出现胸闷冒冷汗与言语不利索，属于危重急症，其乐观说辞必须被一票否决",
        ),
    },
    "argot_hidden": {
        "dimension": "dim:finance",
        "intent": "CONCEALED_ARGOT_TRANSACTION_DEAL",
        "keywords": ("暗语", "行话", "隐匿交易", "走账路径", "壳公司", "高保密约定"),
        "fact_lines": (
            "{self_name}以暗语约定『老地方老陈皮拿三份、尾款走卡』，实为规避监管的隐匿交易与走账安排，涉及资金{amount}",
            "{self_name}用行话交代『货按上次走法出、账走三号壳』，属于高风险隐匿交易约定，存在洗钱与走私嫌疑",
        ),
    },
    "suicidal_metaphor": {
        "dimension": "dim:health",
        "intent": "SUICIDAL_IDEATION_METAPHOR",
        "keywords": ("自绝念头", "心理危机", "遗书", "攒药", "情绪崩塌", "立即干预监护"),
        "fact_lines": (
            "{self_name}以『不用再醒过来』的隐喻表达自绝念头并已攒够整瓶药物，属极危重心理危机，需立即监护干预",
            "{self_name}写下遗书并选定了时间，属最高级别自杀风险事件，必须立刻启动危机干预与身边看护",
        ),
    },
}


# --------------------------------------------------------------------------------------
# 低价值自言自语（口头禅发泄 / 玩笑调侃）：按铁律四属于必须剪枝的垃圾
# --------------------------------------------------------------------------------------
JUNK_SELF_TALK: Tuple[str, ...] = (
    "烦死了，累死了，这破班是一天也上不下去了",
    "哎，要是能中个五百万我就不干了",
    "算了算了，睡吧，明天再说",
    "今天这天气真够呛，冻得人骨头疼",
    "笑死，他昨天那表情我到现在还想笑",
    "随便吧，爱咋咋地，我懒得管了",
    "这日子什么时候是个头啊，算了不说了",
    "行行行，你们都对，就我不对，行了吧",
)
