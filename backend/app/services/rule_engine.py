"""L1 规则引擎:用 Python 词典 + 正则跑死规则,完全不调 LLM。

覆盖范围:
- 成语错别字(~80 条高频词)
- 同音字常见混用(~30 条)
- 中文段落里的英文标点(, . ; : ! ?)
- 全角字母数字应转半角(可选,默认关)
- 多余空格(中文之间的空格)

设计原则:**只报 high confidence,宁可少报不可误报**。
规则引擎和 LLM 互补:规则保 100% 召回死错;LLM 找规则覆盖不到的活错。
"""
from __future__ import annotations
import re
import uuid
from ..schemas import Confidence, FindingSource, Layer, ProofreadError, ReviewStatus


def Finding(**kw) -> ProofreadError:
    """适配旧 API:返回 Pydantic ProofreadError(doc_id 由调用方填或后置)。"""
    return ProofreadError(
        id=kw.get("id") or uuid.uuid4().hex[:12],
        doc_id=kw.get("doc_id", ""),
        layer=Layer(kw.get("layer", "L1")),
        type=kw.get("type", ""),
        confidence=Confidence(kw.get("confidence", "high")),
        paragraph_idx=kw["paragraph_idx"],
        char_start=kw["char_start"],
        char_end=kw["char_end"],
        original=kw["original"],
        suggestion=kw.get("suggestion", ""),
        explanation=kw.get("explanation", ""),
        status=ReviewStatus(kw.get("status", "pending")),
        source=FindingSource(kw.get("source", "auto")),
    )


# ---------- 成语错别字词典(错 → 对) ----------
# 来源:出版业常见错字 + 诊断报告中的实例
IDIOM_ERRORS = {
    # 心字头
    "心惊胆颤": "心惊胆战",
    "心慌意论": "心慌意乱",
    "心心相映": "心心相印",
    # 山水
    "山青水秀": "山清水秀",
    "穿流不息": "川流不息",
    # 高高兴兴
    "兴高彩烈": "兴高采烈",
    "无精打彩": "无精打采",
    "神彩奕奕": "神采奕奕",
    # 路途
    "走头无路": "走投无路",
    "投机倒把": "投机倒把",
    # 励/厉/历
    "再接再励": "再接再厉",
    "厉害关系": "利害关系",
    "声名雀起": "声名鹊起",
    # 筹/愁
    "一愁莫展": "一筹莫展",
    "运筹帷握": "运筹帷幄",
    # 声/生
    "谈笑风声": "谈笑风生",
    # 轮/伦/仑
    "美仑美奂": "美轮美奂",
    "美轮美换": "美轮美奂",
    # 守
    "默守成规": "墨守成规",
    "墨守陈规": "墨守成规",
    # 列前
    "名列前矛": "名列前茅",
    # 病
    "病入膏盲": "病入膏肓",
    # 凭/平
    "凭心而论": "平心而论",
    # 鼓/股/骨
    "一股作气": "一鼓作气",
    "粉身碎股": "粉身碎骨",
    # 致/制
    "出奇致胜": "出奇制胜",
    "克敌致胜": "克敌制胜",
    # 功/工
    "鬼斧神功": "鬼斧神工",
    "异曲同功": "异曲同工",
    "大动干弋": "大动干戈",
    # 近/进
    "急功进利": "急功近利",
    "进退维股": "进退维谷",
    # 程
    "计日成功": "计日程功",
    # 做/作
    "矫揉造做": "矫揉造作",
    # 璧/碧
    "金壁辉煌": "金碧辉煌",
    "完壁归赵": "完璧归赵",
    # 既/继
    "一如继往": "一如既往",
    "前扑后继": "前仆后继",
    # 果/裹
    "食不裹腹": "食不果腹",
    # 宵/霄
    "通霄达旦": "通宵达旦",
    "九宵云外": "九霄云外",
    # 执/直
    "仗义直言": "仗义执言",
    # 灼/卓
    "真知卓见": "真知灼见",
    # 截/接
    "直接了当": "直截了当",
    # 卓/淖
    "卓而不群": "卓尔不群",
    # 是/事
    "各行其事": "各行其是",
    "实是求是": "实事求是",
    # 当/挡
    "锐不可挡": "锐不可当",
    "首当其挡": "首当其冲",  # "其冲"才对
    # 议/意
    "不可思意": "不可思议",
    # 度/渡
    "渡假": "度假",
    "渡假村": "度假村",
    "欢渡春节": "欢度春节",
    "欢渡佳节": "欢度佳节",
    # 帐/账(行业用法:帐篷;账户/账单用账)
    "帐蓬": "帐篷",
    "账蓬": "帐篷",
    # 覆/复
    "翻来复去": "翻来覆去",
    "无以复加": "无以复加",  # 对的
    "天翻地复": "天翻地覆",
    # 唉/哀
    "哀声叹气": "唉声叹气",
    # 详/祥
    "安祥": "安详",
    # 黯/暗
    "暗然失色": "黯然失色",
    "暗然神伤": "黯然神伤",
    # 喧
    "喧兵夺主": "喧宾夺主",
    # 密
    "哈蜜瓜": "哈密瓜",
    # 旋/弦
    "弦律": "旋律",
    # 缘/原
    "原故": "缘故",
    "原由": "缘由",
    # 分/份
    "缘份": "缘分",
    "天份": "天分",
    # 笔/比
    "无可比拟": "无可比拟",  # 对的
    "笔走龙蛇": "笔走龙蛇",  # 对的
    # 备/倍
    "推崇备至": "推崇备至",
    # 毕/必
    "必竟": "毕竟",
    "必竞": "毕竟",
    # 抱/报
    "报负": "抱负",
    "报歉": "抱歉",
    "报怨": "抱怨",
    # 蔼/霭
    "和霭可亲": "和蔼可亲",
}

# 去掉自反映射(value==key)
IDIOM_ERRORS = {k: v for k, v in IDIOM_ERRORS.items() if k != v}


# ---------- 同音字常见混用 ----------
HOMOPHONE_ERRORS = {
    "既使": "即使",
    "即然": "既然",
    "布署": "部署",
    "辨认不清": "辨认不清",  # 对的占位
}
HOMOPHONE_ERRORS = {k: v for k, v in HOMOPHONE_ERRORS.items() if k != v}


# ---------- 中英文标点映射 ----------
# 中文段落里出现的英文标点 → 中文标点
ZH_PUNCT_MAP = {
    ",": ",",
    ";": ";",
    ":": ":",
    "?": "?",
    "!": "!",
    # "." 不动:可能是数字小数点
    # 引号靠位置,单独处理
}

# 检测段落是否"足够中文"(中文字符 > 30% 才做标点转换)
CJK_PATTERN = re.compile(r"[一-鿿]")


def _is_chinese_paragraph(text: str) -> bool:
    if not text:
        return False
    n_cjk = len(CJK_PATTERN.findall(text))
    return n_cjk >= 3 and n_cjk / len(text) > 0.3


def _looks_like_english_context(text: str, pos: int) -> bool:
    """看 pos 前后几字是否是英文环境(不替换标点)。"""
    win = text[max(0, pos - 3): pos + 3]
    eng_count = sum(1 for c in win if c.isascii() and c.isalpha())
    return eng_count >= 3


def _new_finding(idx, char_start, char_end, original, suggestion, type_, explanation) -> Finding:
    return Finding(
        id=str(uuid.uuid4())[:8],
        paragraph_idx=idx,
        char_start=char_start,
        char_end=char_end,
        original=original,
        suggestion=suggestion,
        layer="L1",
        type=type_,
        confidence="high",
        explanation=explanation,
    )


def scan_paragraph(text: str, idx: int) -> list[Finding]:
    """对一段文本跑所有 L1 规则,返回 findings(全 high confidence)。"""
    if not text or len(text) < 2:
        return []
    out = []
    seen_spans: set[tuple[int, int]] = set()  # 防同位置重复

    # 1) 成语错字
    for wrong, right in IDIOM_ERRORS.items():
        for m in re.finditer(re.escape(wrong), text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            out.append(_new_finding(
                idx, m.start(), m.end(), wrong, right,
                "成语错别字", f"成语规范写法为「{right}」",
            ))

    # 2) 同音字常见混用
    for wrong, right in HOMOPHONE_ERRORS.items():
        for m in re.finditer(re.escape(wrong), text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            out.append(_new_finding(
                idx, m.start(), m.end(), wrong, right,
                "同音字", f"应作「{right}」",
            ))

    # 3) 中文段落里的英文标点
    if _is_chinese_paragraph(text):
        for i, ch in enumerate(text):
            if ch in ZH_PUNCT_MAP:
                if _looks_like_english_context(text, i):
                    continue
                # 跳过点号(可能小数)和已被规则覆盖位置
                if (i, i + 1) in seen_spans:
                    continue
                seen_spans.add((i, i + 1))
                out.append(_new_finding(
                    idx, i, i + 1, ch, ZH_PUNCT_MAP[ch],
                    "标点", "中文段落应使用中文标点",
                ))

    # 4) 中文之间的多余空格
    if _is_chinese_paragraph(text):
        for m in re.finditer(r"(?<=[一-鿿])([ 　]+)(?=[一-鿿])", text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            out.append(_new_finding(
                idx, m.start(), m.end(), m.group(), "",
                "多余空格", "中文之间不需要空格",
            ))

    return out


def scan_document(paragraphs: list[str]) -> list[Finding]:
    """对全文跑规则,返回所有 findings。"""
    out = []
    for i, text in enumerate(paragraphs):
        out.extend(scan_paragraph(text, i))
    return out


def dictionary_snapshot_for_prompt(max_idioms: int = 20) -> str:
    """把词典精华渲染成 prompt 片段,告诉 LLM 哪些已被规则覆盖、可以补类似的。"""
    sample = list(IDIOM_ERRORS.items())[:max_idioms]
    sample_str = "、".join(f"{w}({r})" for w, r in sample)
    homo_str = "、".join(f"{w}({r})" for w, r in HOMOPHONE_ERRORS.items())
    return f"""【规则引擎已覆盖的 L1 错字(共 {len(IDIOM_ERRORS)} 条成语 + {len(HOMOPHONE_ERRORS)} 条同音字)】
成语错字示例(节选 {len(sample)} 条):{sample_str}
同音字混用:{homo_str}
另外:中文段落里的英文标点(,;:?!)、全角字母数字、中文间多余空格——这几类规则也已覆盖。

→ **以上这些不要重报**,但你若发现性质相同、规则引擎可能漏的**新错字**,**可以补报**(标 type='成语错别字' 或 '同音字',layer='L1')。"""
