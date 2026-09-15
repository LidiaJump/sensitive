import re
from ..models import MaskResult, DesensitizationRule


def mask_id_card(text: str) -> MaskResult:
    """身份证号脱敏，支持15位旧证、17位（疑似缺校验位）、18位，含空格/横线分隔。"""
    potential_pattern = re.compile(
        r'(?<!\d)([1-9](?:\d|\s|[-－]){13,27}[\dXx])(?!\d)'
    )
    hits = []

    def replace(m):
        raw = m.group(1)
        clean = re.sub(r'[\s\t\-－]', '', raw)
        # 支持 15位旧身份证 / 17位疑似缺校验位 / 18位标准身份证
        if len(clean) not in (15, 17, 18):
            return raw

        if len(clean) == 18:
            year = clean[6:10]
            month = clean[10:12]
            day = clean[12:14]
            if not (year.startswith('19') or year.startswith('20')):
                return raw
            try:
                if not (1 <= int(month) <= 12):
                    return raw
                if not (1 <= int(day) <= 31):
                    return raw
            except ValueError:
                return raw
            masked = clean[:6] + '*' * 8 + clean[14:]

        elif len(clean) == 15:
            # 15位旧身份证：前6地区码 + 6位出生日期(YYMMDD) + 3位顺序码
            month = clean[8:10]
            day = clean[10:12]
            try:
                if not (1 <= int(month) <= 12):
                    return raw
                if not (1 <= int(day) <= 31):
                    return raw
            except ValueError:
                return raw
            masked = clean[:6] + '*' * 6 + clean[12:]

        else:  # 17位，疑似录入时漏掉校验位
            year = clean[6:10]
            month = clean[10:12]
            day = clean[12:14]
            if not (year.startswith('19') or year.startswith('20')):
                return raw
            try:
                if not (1 <= int(month) <= 12):
                    return raw
                if not (1 <= int(day) <= 31):
                    return raw
            except ValueError:
                return raw
            # 前6后4，中间7位打码
            masked = clean[:6] + '*' * 7 + clean[13:]

        hits.append({"original": raw, "masked": masked})
        return masked

    result = potential_pattern.sub(replace, text)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_phone(text: str) -> MaskResult:
    pattern = re.compile(
        r'(?<!\d)(1[3-9]\d[\s-]?\d{4}[\s-]?\d{4})(?!\d)'
    )
    hits = []

    def replace(m):
        raw = m.group(1)
        clean = re.sub(r'[\s-]', '', raw)
        if len(clean) != 11:
            return raw
        masked = clean[:3] + '****' + clean[7:]
        hits.append({"original": raw, "masked": masked})
        return masked

    result = pattern.sub(replace, text)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_plate(text: str) -> MaskResult:
    """车牌号脱敏：保留省份简称+发牌机关字母，序号全部打星号。
    支持普通车牌（5位序号）和新能源车牌（6位序号）。
    如 桂GA1234 → 桂G*****，京AD12345 → 京A******
    """
    pattern = re.compile(
        r'(?<![A-Z0-9])'
        r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z])'
        r'([A-Z0-9]{5,6})'
        r'(?![A-Z0-9])'
    )
    hits = []

    def replace(m):
        prefix = m.group(1)
        serial = m.group(2)
        masked = prefix + '*' * len(serial)
        hits.append({"original": m.group(0), "masked": masked})
        return masked

    result = pattern.sub(replace, text)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_social_security(text: str) -> MaskResult:
    pattern = re.compile(
        r'(?:社保编号|社保号|个人社保编号|社会保障号|社会保险号|参保编号|社保账号)'
        r'[:：\s]*'
        r'(\d{12,20})'
    )
    hits = []

    def replace(m):
        original = m.group(1)
        if len(original) <= 4:
            return m.group(0)
        masked = original[:4] + '*' * (len(original) - 8) + original[-4:]
        hits.append({"original": original, "masked": masked})
        return m.group(0).replace(original, masked)

    result = pattern.sub(replace, text)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_certificate(text: str) -> MaskResult:
    """其他证件号脱敏：土地承包经营权证、不动产权证、银行卡、统一社会信用代码等。

    匹配策略：关键词前缀（证号/证件号/权证号/卡号/账号/编号/代码）+ 16-20位字母数字。
    放在 id_card / phone 规则之后执行，避免重复匹配。
    """
    hits = []
    result = text

    keyword_pattern = re.compile(
        r'(证号|证件号|权证号|卡号|账号|编号|代码|证编号|权证编号|执照号|登记号)'
        r'[:：\s]*'
        r'([A-Za-z0-9]{16,20})'
    )

    def replace_keyword(m):
        full = m.group(0)
        cert = m.group(2)
        if '*' in cert:
            return full
        if len(cert) <= 8:
            masked = '*' * len(cert)
        else:
            masked = cert[:4] + '*' * (len(cert) - 8) + cert[-4:]
        hits.append({"original": cert, "masked": masked})
        return full.replace(cert, masked, 1)

    result = keyword_pattern.sub(replace_keyword, result)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


class NameDictRule:
    def __init__(self, names: list):
        self.names = sorted(set(names), key=len, reverse=True)
        self.pattern = None
        if self.names:
            escaped = [re.escape(n) for n in self.names if n and len(n) >= 2]
            if escaped:
                self.pattern = re.compile('|'.join(escaped))

    def mask(self, text: str) -> MaskResult:
        if not self.pattern:
            return MaskResult(masked_text=text, hit_count=0, hit_details=[])
        hits = []

        def replace(m):
            original = m.group(0)
            if len(original) <= 1:
                return original
            masked = original[0] + '*' * (len(original) - 1)
            hits.append({"original": original, "masked": masked})
            return masked

        result = self.pattern.sub(replace, text)
        return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


NAME_KEYWORDS = [
    "曾用名", "父亲", "母亲", "妻子", "爱人", "丈夫",
    "女儿", "儿子", "小孩", "孩子", "宝宝", "妈妈", "配偶",
    "参保人", "反映人", "当事人", "投诉人", "被投诉人",
    "申请人", "举报人", "联系人", "户主", "老板",
    "负责人", "厂长", "承包方", "车主", "房东", "租客",
    "家属", "老婆", "大舅子", "岳父", "岳母", "公公", "婆婆",
    "哥哥", "姐姐", "弟弟", "妹妹", "祖父", "祖母",
    "外公", "外婆", "爷爷", "奶奶", "幼儿", "婴儿",
    "侄女", "侄子", "外甥", "外甥女", "孙子", "孙女",
    "外孙", "外孙女", "大伯", "大叔", "婶婶", "舅妈",
    "姑父", "姨父", "姨妈", "表姐", "表哥", "表弟", "表妹",
    # 政务/社区职位
    "业委会主任", "村主任", "村支书", "村长", "书记", "主任", "副主任",
    "委员", "队长", "组长", "社长", "监事", "理事", "会长", "秘书长", "干事",
    # 职业
    "律师", "医生", "护士", "老师", "教师", "校长", "园长", "经理", "主管",
    "司机", "厨师", "保安", "保洁", "快递员", "外卖员", "维修工", "电工",
    "工人", "职员", "员工", "总监", "设计师", "工程师", "会计", "出纳",
    # 身份/关系
    "学生", "家长", "监护人", "业主", "住户", "居民", "村民", "市民",
    "群众", "邻居", "朋友", "同事", "病友", "老乡", "同学", "战友",
    # 法律/程序
    "原告", "被告", "第三人", "证人", "嫌疑人", "被告人", "被害人", "受害人",
    "法定代表人", "经办人", "承办人", "审核人", "审批人", "委托人", "代理人",
    "辩护人", "鉴定人", "公证人", "见证人",
    # 老年称呼
    "老爷子", "老太太", "老人家", "老两口", "家里老人", "老的",
    "爹妈", "爸妈", "爹", "娘", "老妈", "老爸", "姥姥", "姥爷",
    "大爷", "大娘", "伯娘", "叔叔", "婶子", "姑姑", "姑妈",
    "舅舅", "姨姨", "姨夫", "老丈人", "丈母娘", "家公", "家婆",
    "后爹", "后妈",
    # 配偶/伴侣
    "老公", "媳妇", "先生", "夫人", "对象", "家里那口子",
    # 平辈（含单字简称，长词优先匹配）
    "哥", "老哥", "姐", "兄弟", "嫂子", "弟妹", "弟媳妇",
    "姐夫", "妹夫", "堂哥", "堂弟", "堂姐", "堂妹",
    # 晚辈
    "娃", "闺女", "儿媳", "儿媳妇", "女婿",
    # 村务/社区/政务角色
    "村干部", "村领导", "村书记", "小组长", "社区干部", "网格员",
    "居委会的人", "物业", "物业经理", "门卫", "领导", "当官的",
    "管事的", "办事员", "窗口人员", "所长", "站长", "局长", "股长",
    "科长", "辅警", "协警", "民警", "城管", "调解员",
    # 租赁/经营/务工
    "租户", "商户", "包工头", "工头", "中间人", "介绍人",
    "隔壁家", "对门", "楼下", "楼上", "同村", "同乡",
    # 政务/职业（xx员类）
    "蔗管员", "工作人员", "办事人员", "窗口人员", "计生员", "防疫员",
    "护林员", "保洁员", "保安员", "快递员", "外卖员", "配送员",
    "车商", "药商", "经销商", "代理商", "供应商",
    # 泛称/尊称
    "阿姨", "大妈", "老师傅", "师傅", "大姐", "老弟", "妹子", "小伙子",
]

NAME_KEYWORD_PATTERN = '|'.join(sorted(NAME_KEYWORDS, key=len, reverse=True))

RELATIONSHIP_KEYWORDS = [
    "父亲", "母亲", "妻子", "爱人", "丈夫", "女儿", "儿子",
    "小孩", "孩子", "宝宝", "妈妈", "配偶", "老婆",
    "户主", "家属", "大舅子", "岳父", "岳母", "公公", "婆婆",
    "哥哥", "姐姐", "弟弟", "妹妹", "祖父", "祖母",
    "外公", "外婆", "爷爷", "奶奶", "幼儿", "婴儿",
    "老板", "负责人", "厂长", "承包方", "车主", "房东", "租客",
]

RELATIONSHIP_PATTERN = '|'.join(sorted(RELATIONSHIP_KEYWORDS, key=len, reverse=True))

NON_NAME_START_CHARS = set(
    '属于已于于到在去来需要是与及或将现对本其被该有无否能对从为让使'
    '信打开具进入出说过想看听闻觉感知道依按经过通过关于对于由于鉴于基于'
    '上述下可应即若如这那哪怎某各每另就也还又再都只才便非否'
    '电联号证码明示表给向跟叫请'
    '您'
)

# 常见姓氏（百家姓主体），用于"身份证前置"规则中校验姓名首字、剥离关系词前缀
COMMON_SURNAMES = set(
    '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜'
    '戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐'
    '费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄'
    '和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁'
    '杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍'
    '虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚'
    '程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓'
    '牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙'
    '叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双'
    '闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农'
    '温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘'
    '匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空'
    '曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公'
    '覃农班闭岑容欧卓浦邝冼庞龚蒙鄢谌谌'  # 补充南方/广西常见姓氏
)

# TOP100 常见姓氏（覆盖约99%汉族人口），用于 p8/p9/p10 等宽松规则。
# 罕见姓氏（公、家、封、曲、干、戎、暴、能、双、空、乜等）作为普通字出现频率
# 远高于作为姓氏，在宽松规则中排除，避免"物业公司""邻居家的狗"等误判；
# 罕见姓氏仍可在 p4（身份证前置）等强上下文规则中通过 COMMON_SURNAMES 识别。
TOP100_SURNAMES = set(
    '王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖'
    '田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付'
    '方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤'
    '蒙蓝农庞班闭岑容欧卓浦邝冼'  # 补充广西常见姓氏
)

# 关系词/身份词的常见尾字：当"身份证前置"匹配到的候选首字不是姓氏、
# 但去掉首字后剩余以姓氏开头时，判定首字是关系词尾字（如"母亲张小峰"→"亲"+"张小峰"）
RELATION_TAIL_CHARS = set(
    '亲主人员者方司长板东客属父母公婆哥弟妹爷奶儿子甥伯叔婶妈'
    '任理监督表代事生士官兵警师护医工的名字'
)

NON_NAME_WORDS = {
    '身份证', '身份证号', '身份证号码', '号码', '信息', '本人', '市民',
    '已经', '无法', '可以', '需要', '应该', '属于', '表示', '身份',
    '参保', '保险', '福利', '待遇', '业务', '情况', '问题', '申请',
    '办理', '相关', '如下', '根据', '按照', '由于', '基于',
    '总计', '共计', '合计', '总共', '一共', '大约', '大概',
    '随后', '然后', '之后', '之前', '现在', '目前', '此前',
    '发现', '提出', '认为', '指出', '说明', '要求', '具有',
    '同时', '同步', '随即', '随时', '后来', '一直',
    '予以', '据此', '经查', '现将', '特此', '为此', '对此',
    '此外', '另外', '不再', '尚无', '暂无', '并无',
}

# 常见动词表：关系词/关键词后面如果紧跟这些词，说明不是姓名而是动作描述
# 例如"为女儿缴纳了"中的"缴纳"不是姓名
VERB_WORDS = {
    '缴纳', '办理', '上学', '工作', '就医', '住院', '出院', '报名', '登记',
    '参保', '缴费', '报销', '申请', '审批', '审核', '核实', '处理', '解决',
    '回复', '答复', '联系', '沟通', '协调', '反映', '投诉', '举报', '咨询',
    '求助', '查询', '打印', '开具', '出具', '领取', '发放', '接收', '接受',
    '拒绝', '同意', '反对', '要求', '请求', '建议', '反馈', '回访', '复查',
    '复核', '调解', '协商', '签约', '约定', '承诺', '保证', '担保', '抵押',
    '就读', '毕业', '就业', '失业', '退休', '离职', '入职', '转正', '升职',
    '调岗', '加班', '请假', '休假', '出差', '培训', '学习', '考试', '考核',
    '评比', '评选', '表彰', '奖励', '惩罚', '处分', '警告', '记过', '撤职',
    '开除', '辞退', '辞职', '解聘', '解雇', '裁员', '下岗', '参军', '入伍',
    '退伍', '转业', '复员', '落户', '迁移', '搬迁', '拆迁', '征收', '征用',
    '补偿', '赔偿', '补助', '救济', '抚恤', '养老', '医疗', '生育', '工伤',
    '失业', '住房', '公积金', '个税', '契税', '过户', '交易', '买卖', '租赁',
    '出租', '承租', '转租', '装修', '维修', '改造', '拆除', '重建', '新建',
    '扩建', '改建', '搭建', '占用', '使用', '利用', '开发', '经营', '销售',
    '购买', '采购', '招标', '投标', '中标', '签约', '履行', '违约', '解除',
    '终止', '变更', '转让', '赠与', '继承', '分割', '合并', '分立', '解散',
    '清算', '破产', '注销', '吊销', '撤销', '取缔', '查封', '扣押', '冻结',
    '拍卖', '变卖', '折价', '抵债', '担保', '保证', '抵押', '质押', '留置',
}

POST_NAME_LOOKAHEAD = r'(?=[，,。；;（(\s、的已将于到在电话联系身份证号现去来需要对是和与与及或被本该其失办参户\d]|$)'

NAME_NEGATIVE = r'(?!证|号|码|信息|户)'


def _is_verb_or_starts_with_verb(name: str) -> bool:
    """判断候选姓名是否是常见动词或以常见动词开头（上下文感知：排除动作描述误判）。"""
    if name in VERB_WORDS:
        return True
    if len(name) >= 2 and name[:2] in VERB_WORDS:
        return True
    return False


def mask_names_by_keyword(text: str) -> MaskResult:
    hits = []
    result = text

    def make_replacer(pattern_compiled):
        def replace(m):
            keyword = m.group(1)
            name = m.group(2)
            if '*' in name:
                return m.group(0)
            if name in NON_NAME_WORDS:
                return m.group(0)
            if name[0] in NON_NAME_START_CHARS:
                return m.group(0)
            if _is_verb_or_starts_with_verb(name):
                return m.group(0)
            masked_name = name[0] + '*' * (len(name) - 1)
            offset = m.start(2) - m.start()
            match_text = m.group(0)
            hits.append({"original": name, "masked": masked_name})
            return match_text[:offset] + masked_name + match_text[offset + len(name):]
        return replace

    p1 = re.compile(
        r'(' + NAME_KEYWORD_PATTERN + r')'
        r'姓名'
        r'[:：、，,。；;\s]*'
        r'(?:身份证[号码]*[:：、\s]*)?'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + NAME_NEGATIVE
        + POST_NAME_LOOKAHEAD
    )
    result = p1.sub(make_replacer(p1), result)

    p2 = re.compile(
        r'(' + NAME_KEYWORD_PATTERN + r')'
        r'[:：、\s]+'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + NAME_NEGATIVE
        + POST_NAME_LOOKAHEAD
    )
    result = p2.sub(make_replacer(p2), result)

    p3 = re.compile(
        r'(' + RELATIONSHIP_PATTERN + r')'
        r'[:：、\s是叫为]+'          # 必须有分隔符，避免"负责人区城管局"直接连读误判
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + NAME_NEGATIVE
        + r'(?=[，,。；;（(\s、的已将于到在电话联系身份证号现去来需对被本该其失办参户\d]|$)'
    )
    result = p3.sub(make_replacer(p3), result)

    p4 = re.compile(
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        r'[，,；;、\s\]\）)】〕〉>（(]+'
        r'身份证[号码]*[:：\s]*\d'   # 后置约束：身份证后必须跟号码/冒号/数字，排除"身份证复印件""身份证、户口本"
    )

    def replace4(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        # 以"姓名/名字/信息"结尾的是字段名而非人名（如"母亲姓名、身份证"）
        if name.endswith(('姓名', '名字', '信息')):
            return m.group(0)
        # 姓氏校验：候选首字不是姓氏时，尝试剥离关系词尾字
        # 如"亲张小峰"→"亲"非姓氏，去掉后"张小峰"以姓氏"韦"开头→取"张小峰"
        if name[0] not in COMMON_SURNAMES:
            if (len(name) >= 3 and name[0] in RELATION_TAIL_CHARS
                    and name[1] in COMMON_SURNAMES):
                name = name[1:]
            else:
                return m.group(0)
        # 最终校验：首字必须是姓氏
        if name[0] not in COMMON_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p4.sub(replace4, result)

    p5 = re.compile(
        r'(?:儿名|女名|子名|孙名|名下|名)[:：、\s]+'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        r'[，,；;、\s\]\）)】〕]*'
        r'(?:身份证|证件|号码|\d{15,18})'
    )

    def replace5(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name.endswith(('姓名', '名字', '信息')):
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p5.sub(replace5, result)

    p6 = re.compile(
        r'(' + NAME_KEYWORD_PATTERN + r')'
        r'(?:信息|名字|姓名)'
        r'[:：、\s]*'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + NAME_NEGATIVE
        + POST_NAME_LOOKAHEAD
    )
    result = p6.sub(make_replacer(p6), result)

    # p7: 第一人称自述"本人XXX"——本人后直接跟姓名，无分隔符。
    # 用后置约束区分"本人张小海，男/身份证/居住于"（姓名）和"本人反映，路灯坏了"（动词）：
    # 姓名后必须是"逗号+身份描述词/数字"，或句号/分号/结尾。
    p7 = re.compile(
        r'(本人)'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + r'(?=[，,]\s*(?:男|女|身份证|身份证号|电话|手机|手机号|居住|住址|地址|年龄|岁|'
        r'出生|户籍|民族|文化|学历|职业|工作|联系|联系方式|系|是|为|\d)|[。；;]|$)'
    )

    def replace7(m):
        name = m.group(2)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name.endswith(('姓名', '名字', '信息')):
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p7.sub(replace7, result)

    # p8: 亲属/身份词后直接跟姓名（无分隔符），如"大伯张小宁""丈夫张小亮""儿子张小鹏"。
    # 用姓氏首字校验区分"大伯张小宁"（覃是姓氏→姓名）和"大伯一个人"（一非姓氏→跳过）。
    # 限定2-3字：中文姓名99%为2-3字，避免贪婪吃掉后续非姓名字（如"张小鹏今年"→只取"张小鹏"）。
    # 负向先行断言：关键词后首字不能是虚词（是/为/叫/将/被等），避免"户主是哥哥"匹配消耗
    # "哥哥"导致后续"哥哥张小辉"无法匹配。
    _non_start = ''.join(NON_NAME_START_CHARS)
    p8 = re.compile(
        r'(' + NAME_KEYWORD_PATTERN + r')'
        r'(?![' + _non_start + r'])'
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
    )

    def replace8(m):
        name = m.group(2)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name.endswith(('姓名', '名字', '信息')):
            return m.group(0)
        # 3字候选末字若是动词/虚词首字，截断为2字（如"王五出差"→"王五出"截断为"王五"）
        if len(name) == 3 and name[2] in NON_NAME_START_CHARS:
            name = name[:2]
        # 核心校验：首字必须是TOP100常见姓氏，过滤"一个人""今年""因患""公司拒"等非姓名
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p8.sub(replace8, result)

    # p9: "姓名：XXX"/"名字：XXX"独立规则——无前置身份词，"姓名/名字"后直接跟冒号/空格+姓名。
    # 后置约束：姓名后必须是标点、空格、结尾、或"电话/手机/身份证"等词，
    # 排除"姓名信息""姓名栏"等非姓名场景。
    p9 = re.compile(
        r'(?:姓名|名字)[:：\s]+'
        r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        r'(?=[，,。.；;、\s\]\）)】〕〉>）)）]|电话|手机|身份证|证件|号|$)'
    )

    def replace9(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        # "姓名："后几乎一定是姓名，姓氏校验放宽但仍保留（过滤极端误判）
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p9.sub(replace9, result)

    # p10: "XXX电话"后置规则——姓名后直接跟"电话"，用姓氏首字校验。
    # 如"张瑞电话：188****"→识别"张瑞"。
    # 过滤"联系电话""咨询电话""服务电话"等（首字非姓氏）。
    p10 = re.compile(
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
        r'电话'
    )

    def replace10(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p10.sub(replace10, result)

    # p11: 并列姓名规则——已脱敏姓名（含星号）+ 顿号/逗号/空格 + 未脱敏姓名。
    # 如"黄**、张小珍""罗** 张小琴""覃**，张小莲"。星号前缀是强信号：前面已是脱敏姓名，
    # 分隔符后大概率是并列的另一个姓名。
    p11 = re.compile(
        r'[*＊]+[、，,\s]+'
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
    )

    def replace11(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p11.sub(replace11, result)

    # p12: "XXX的姓名/身份证号/电话"——姓名后直接跟"的+身份字段"。
    # 如"以张小航的姓名申请""无法提供张小航的身份证号"。
    # 用姓氏校验过滤"当事人的姓名""受害人的身份证号"等（首字在NON_NAME_START_CHARS）。
    p12 = re.compile(
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
        r'的(?:姓名|身份证号|身份证|电话|手机号|联系方式|联系电话)'
    )

    def replace12(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p12.sub(replace12, result)

    # p13: "姓名，身份证号"——姓名后直接跟逗号+身份证号（无"身份证"字样）。
    # 如"张小涛，999999********454X"。支持纯数字身份证和已脱敏（含星号）身份证。
    p13 = re.compile(
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
        r'[，,]\s*'
        r'(?:\d{15,18}|\d{6}[*＊]+\d{3,4})[Xx]?'
    )

    def replace13(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p13.sub(replace13, result)

    # p14: "姓名+手机号"——姓名后直接跟空格/逗号/冒号+手机号（含已脱敏格式如138****0000）。
    # 如"张小豪 138****0000""张三，13800138000"。手机号是强信号：前面2-3字且首字为姓氏，
    # 大概率是姓名。
    _phone_re = r'(?:1[3-9]\d[\s-]?\d{4}[\s-]?\d{4}|1\d{2}[\s-]?\*{2,6}[\s-]?\d{3,4})'
    p14 = re.compile(
        r'([\u4e00-\u9fa5]{2,3})(?<!的)'
        r'[\s，,：:]+'
        + _phone_re
    )

    def replace14(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS:
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        if name[0] not in TOP100_SURNAMES:
            return m.group(0)
        masked_name = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked_name})
        return m.group(0).replace(name, masked_name, 1)

    result = p14.sub(replace14, result)

    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


# 机构后缀字：这些字后面跟职位词时，是"XX局局长"而非"姓+职位"
ORG_SUFFIX_CHARS = set(
    '局处科部院所站队中心厅司办组室馆社会厂店行司委府乡镇区县市省'
    '村屯组庄寨路街道巷弄小区花园公寓大厦广场城园苑居里'
)


def mask_salutation(text: str) -> MaskResult:
    hits = []
    result = text

    pattern1 = re.compile(r'(尊敬的|尊敬地|亲爱的|请输入|回复)([\u4e00-\u9fa5]{1,4})(女士|先生|同志|小姐|师傅)')

    def replace1(m):
        prefix = m.group(1)
        name = m.group(2)
        suffix = m.group(3)
        if len(name) <= 1:
            masked_name = name + '*'
        else:
            masked_name = name[0] + '*' * (len(name) - 1)
        full = prefix + masked_name + suffix
        hits.append({"original": m.group(0), "masked": full})
        return full

    result = pattern1.sub(replace1, result)

    pattern2 = re.compile(
        r'([\u4e00-\u9fa5])'
        r'(医生|护士|院长|主任|警官|警察|老师|教授|律师|会计|科长|处长|局长|所长|站长|队长|经理)'
    )

    def replace2(m):
        surname = m.group(1)
        title = m.group(2)
        if surname in NON_NAME_START_CHARS:
            return m.group(0)
        # 上下文感知："局局长""处处长"是机构名+职位，不是姓+职位
        if surname in ORG_SUFFIX_CHARS:
            return m.group(0)
        # 姓氏必须是TOP100常见姓，过滤"责令老师→令老师""数学老师→学老师""语文老师→文老师"等误判
        if surname not in TOP100_SURNAMES:
            return m.group(0)
        masked = '*' + title
        hits.append({"original": m.group(0), "masked": masked})
        return masked

    result = pattern2.sub(replace2, result)

    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_address(text: str) -> MaskResult:
    hits = []
    result = text

    # 门牌号支持阿拉伯数字与中文数字混合（如"二栋二区一单元602号"）
    CJK_D = r'[一二三四五六七八九十百零〇\d]'
    # 门牌号数字（支持横线，如2-1号）
    DOOR_NUM = r'[A-Za-z]?[\d一二三四五六七八九十百零〇-]+'
    # 楼栋号：支持纯字母(C栋)、纯数字(1栋)、字母+数字(C1栋)
    BUILDING_NUM = r'(?:[A-Za-z]' + CJK_D + r'*|' + CJK_D + r'+)'
    building_pattern = re.compile(
        r'(' + BUILDING_NUM + r')\s*(?:号楼|栋)'                     # X号楼/栋（支持C栋）
        r'(?:\s*' + CJK_D + r'+\s*区)?'                               # X区
        r'(?:\s*' + CJK_D + r'+\s*单元)?'                             # X单元
        r'(?:\s*' + CJK_D + r'+\s*楼)?'                               # X楼
        r'(?:\s*' + CJK_D + r'+\s*层)?'                               # X层
        r'(?:\s*' + DOOR_NUM + r'\s*号(?:\s*房)?)?'                   # X号/X号房（支持2-1号、C13号）
        r'(?:\s*' + CJK_D + r'+\s*室)?'                               # X室
        r'|' + CJK_D + r'+\s*单元\s*' + CJK_D + r'+\s*室'             # X单元X室
        r'|(?:(?:' + CJK_D + r'+)\s*号\s*)?' + CJK_D + r'+\s*楼\s*' + CJK_D + r'+\s*(?:房间|室|号房|房|号)'  # X楼X房间/号
        r'|' + CJK_D + r'+\s*楼\s*' + DOOR_NUM + r'\s*号'             # X楼X号（如18楼18044号）
        r'|' + CJK_D + r'+\s*单元\s*' + CJK_D + r'+\s*楼'             # X单元X楼（如3单元二楼）
        r'|' + CJK_D + r'+\s*楼\s*(?:门面|平台|天台|阁楼|储物间)'      # X楼+场所（如一楼门面、二楼平台）
        r'|[A-Za-z]' + CJK_D + r'+\s*号'                              # 字母前缀门牌号（如C13号）
    )

    def _mask_digits(s: str) -> str:
        # 阿拉伯数字、中文数字、字母统一打码（楼栋号如C栋的C也需脱敏）
        return re.sub(r'[\dA-Za-z一二三四五六七八九十百零〇]', '*', s)

    def replace_building(m):
        original = m.group(0)
        masked = _mask_digits(original)
        hits.append({"original": original, "masked": masked})
        return masked

    result = building_pattern.sub(replace_building, result)

    street_num_pattern = re.compile(
        r'([\u4e00-\u9fa5]{2,10}(?:路|街|道|巷|弄|大道))'
        r'(?:[东西南北中]\s*)?'
        r'([\d-]+)\s*号'
    )

    def replace_street(m):
        road = m.group(1)
        num = m.group(2)
        original = m.group(0)
        masked_num = re.sub(r'\d', '*', num)
        masked = road + masked_num + '号'
        hits.append({"original": original, "masked": masked})
        return masked

    result = street_num_pattern.sub(replace_street, result)

    # 地点词+门牌号：路名与门牌号之间隔了小区/商贸城名时，由地点词触发脱敏。
    # 如"示例供销小区321-4号""示例国际商贸城D区119-125号"。
    # "区"限定为字母/数字前缀（如D区、2区），避免"示例区"等行政区误触发。
    location_num_pattern = re.compile(
        r'(小区|商贸城|批发市场|农贸市场|市场|花园|公寓|大厦|广场|城|园|苑|居里|社区|村委|村委会|'
        r'[A-Za-z\d]区)'
        r'\s*([\d-]+)\s*号'
    )

    def replace_location(m):
        loc = m.group(1)
        num = m.group(2)
        original = m.group(0)
        masked_num = re.sub(r'\d', '*', num)
        masked = loc + masked_num + '号'
        hits.append({"original": original, "masked": masked})
        return masked

    result = location_num_pattern.sub(replace_location, result)

    rural_pattern = re.compile(
        r'((?:村|屯|组|队|庄|寨))\s*(\d+(?:-\d+)*)\s*号'
    )

    def replace_rural(m):
        suffix = m.group(1)
        num = m.group(2)
        original = m.group(0)
        masked_num = re.sub(r'\d', '*', num)
        masked = suffix + masked_num + '号'
        hits.append({"original": original, "masked": masked})
        return masked

    result = rural_pattern.sub(replace_rural, result)

    # ══ 兜底：地址上下文中的门牌号/巷号 ══
    # 处理前面规则漏掉的场景：
    #   "门面199号—219号"（路名+门面+号）
    #   "2巷27号"（小区+巷+号）
    #   "里面1106号"（市场+里面+号）
    # 前置锚点必须是地址特征词，避免"编号123号""订单号456号"等误判。
    # 过渡词不含数字/号/巷，避免贪婪吃掉门牌号本身。
    ADDR_ANCHORS = (
        r'路|街|道|巷|弄|大道|小区|商贸城|批发市场|农贸市场|市场|花园|公寓|大厦|广场|'
        r'城|园|苑|居里|社区|村委|村委会|村|屯|组|队|庄|寨|门面|里面|旁|附近|对面|旁边'
    )
    fallback_door = re.compile(
        r'(' + ADDR_ANCHORS + r')'
        r'([^\d一二三四五六七八九十百零〇号巷]{0,8})'
        r'([\d一二三四五六七八九十百零〇-]+)\s*(号|巷)'
        r'(?:\s*[—\-–至到]\s*([\d一二三四五六七八九十百零〇-]+)\s*(号|巷))?'
    )

    def replace_fallback(m):
        anchor = m.group(1)
        bridge = m.group(2)
        num1 = m.group(3)
        unit1 = m.group(4)
        num2 = m.group(5)
        unit2 = m.group(6)
        full = m.group(0)
        if '*' in full or '＊' in full:
            return full
        masked_num1 = re.sub(r'[\d一二三四五六七八九十百零〇]', '*', num1)
        masked = anchor + bridge + masked_num1 + unit1
        if num2 and unit2:
            masked_num2 = re.sub(r'[\d一二三四五六七八九十百零〇]', '*', num2)
            # 还原中间的连接符
            connector = full[len(anchor + bridge + num1 + unit1):-len(num2 + unit2)]
            masked += connector + masked_num2 + unit2
        hits.append({"original": full, "masked": masked})
        return masked

    # 跑两遍：第一遍脱敏"2巷"后，第二遍"巷"可作为锚点继续脱敏"27号"
    for _ in range(2):
        result = fallback_door.sub(replace_fallback, result)

    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


# 地址后可能跟随的描述性词，不应被当作"地址名单"里的姓名
ADDR_AFTER_NON_NAME = {
    '业主', '住户', '居民', '村民', '组织者', '代表', '成员', '负责人',
    '旁边', '对面', '楼下', '楼上', '附近', '周围', '那边', '这边',
    '门前', '门口', '后面', '前面', '左面', '右面', '东侧', '西侧',
    '南侧', '北侧', '经营', '出租', '承租', '居住', '落户', '入住',
    '反映', '投诉', '举报', '咨询', '求助', '来电', '电话', '反映人',
    '漏水', '渗水', '顶部', '损坏', '破损', '堵塞', '堆放', '占用',
    '停放', '开设', '做生', '个体', '商户', '商铺', '店面', '招牌',
    '广告', '噪音', '污染', '违建', '乱建', '养殖', '种植', '垃圾',
    '污水', '楼梯', '楼道', '电梯', '过道', '通道', '阳台', '飘窗',
    '墙面', '墙体', '地面', '天花', '吊顶', '门窗', '开关', '插座',
    '管线', '水箱', '泵房', '配电', '消防', '监控', '围栏', '大门',
    '围墙', '绿化', '车位', '停车', '充电', '电动车', '车辆', '机位',
    '窗口', '窗户', '房屋', '房子', '住宅', '宿舍', '小区', '单位',
    '楼顶', '屋顶', '楼层', '地下室', '车库', '马路', '路段', '区域',
    '片区', '空地', '球场', '花园', '广场', '摊位', '摆摊', '经营',
    '汽油', '煤气', '燃气', '水电', '用电', '电正常', '物业', '物业费',
    '管理费', '电梯费', '房主', '房内', '房产', '租户', '房的', '没有',
    '保洁', '卫生', '瓦房', '一层', '架空', '门面', '单据', '独栋',
    '别墅', '左梯', '右梯', '电梯',
    '楼梯间', '杂物', '内装', '装修', '组合', '提交', '齐平', '半场',
    '打球', '打球场', '隔离', '围挡', '管道', '水表', '电表', '空调',
    '热水器', '排烟', '排气', '下水', '上水', '地漏', '换气', '照明',
}


def mask_names_after_address(text: str) -> MaskResult:
    """地址后名单姓名脱敏。

    识别业主/组织者名单模式，如"2栋3号张伟、2栋4号李娜、2栋王强"。
    锚点必须包含强门牌词（号楼/栋），后跟区/单元/号/室/楼/层可选，
    再跟 2-4 字中文且以名单分隔符结尾，判定为姓名。
    排除"业主/村民/车位/窗口"等描述性词，避免误判污染业务文本。
    """
    hits = []
    result = text

    CJK_D = r'[一二三四五六七八九十百零〇\d*]'
    strong = r'(?:' + CJK_D + r'+)\s*(?:号楼|栋)'        # 强锚：必须有栋/号楼
    tail = r'(?:\s*' + CJK_D + r'+\s*(?:区|单元|号|室|楼|层))?'
    address_anchor = strong + tail + tail + tail + tail

    pattern = re.compile(
        address_anchor
        + r'([\u4e00-\u9fa5]{2,4})(?<!的)'
        + r'(?=[，,。；;、（(\s）)】〕]|$)'
    )

    def replace(m):
        name = m.group(1)
        if '*' in name:
            return m.group(0)
        if name in NON_NAME_WORDS:
            return m.group(0)
        if name[0] in NON_NAME_START_CHARS or name[0] == '的':
            return m.group(0)
        if _is_verb_or_starts_with_verb(name):
            return m.group(0)
        # 排除描述性词
        for w in ADDR_AFTER_NON_NAME:
            if w in name:
                return m.group(0)
        masked = name[0] + '*' * (len(name) - 1)
        hits.append({"original": name, "masked": masked})
        return m.group(0).replace(name, masked, 1)

    result = pattern.sub(replace, result)
    return MaskResult(masked_text=result, hit_count=len(hits), hit_details=hits)


def mask_structured_name(name: str) -> str:
    if not name or len(name) <= 1:
        return name
    return name[0] + '*' * (len(name) - 1)


def mask_structured_phone(phone: str) -> str:
    phone = str(phone).strip() if phone else ''
    clean = re.sub(r'[\s-]', '', phone)
    if len(clean) == 11 and clean.startswith('1'):
        return clean[:3] + '****' + clean[7:]
    return phone


def mask_structured_id_card(id_card: str) -> str:
    id_card = str(id_card).strip() if id_card else ''
    clean = re.sub(r'[\s\-－]', '', id_card)
    if len(clean) == 18:
        return clean[:6] + '*' * 8 + clean[14:]
    if len(clean) == 15:
        return clean[:6] + '*' * 6 + clean[12:]
    if len(clean) == 17:
        return clean[:6] + '*' * 7 + clean[13:]
    return id_card


ALL_RULES = [
    DesensitizationRule(
        rule_id="id_card",
        name="身份证号脱敏",
        pii_type="id_card",
        description="15/17/18位身份证号（支持空格/横线/全角横线分隔），保留前6后4",
        mask_func=mask_id_card,
    ),
    DesensitizationRule(
        rule_id="phone",
        name="手机号脱敏",
        pii_type="phone",
        description="11位手机号（支持空格/横线格式），保留前3后4",
        mask_func=mask_phone,
    ),
    DesensitizationRule(
        rule_id="certificate",
        name="其他证件号脱敏",
        pii_type="certificate",
        description="土地承包经营权证、不动产权证、银行卡等（关键词前缀+16-20位字母数字），保留前4后4",
        mask_func=mask_certificate,
    ),
    DesensitizationRule(
        rule_id="social_security",
        name="社保编号脱敏",
        pii_type="social_security",
        description="社保编号/参保编号，保留前4后4",
        mask_func=mask_social_security,
    ),
    DesensitizationRule(
        rule_id="name_keyword",
        name="关键词姓名脱敏",
        pii_type="name",
        description="识别'母亲姓名：XXX'、'女儿姓名：XXX'等模式中的第三方姓名，含动词上下文排除",
        mask_func=mask_names_by_keyword,
    ),
    DesensitizationRule(
        rule_id="salutation",
        name="称谓脱敏",
        pii_type="salutation",
        description="答复内容中的'尊敬的X女士/先生'及'X局长'等，排除'局局长'类机构后缀误判",
        mask_func=mask_salutation,
    ),
    DesensitizationRule(
        rule_id="address",
        name="地址脱敏",
        pii_type="address",
        description="个人地址：栋/楼/室/号/房/单元等门牌号掩码（支持中文数字）；公共地址（区/镇/村）不脱敏",
        mask_func=mask_address,
    ),
    DesensitizationRule(
        rule_id="addr_name",
        name="地址后名单姓名脱敏",
        pii_type="name",
        description="识别'2栋3号张伟、2栋王强'等业主/组织者名单模式中的姓名",
        mask_func=mask_names_after_address,
    ),
]
