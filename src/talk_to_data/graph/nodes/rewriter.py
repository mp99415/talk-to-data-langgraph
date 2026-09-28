"""
CONTEXT QUESTION REWRITER 节点
"""

import json
import re
import time
from typing import Dict, Any
from ...llm.client import get_llm
from ...llm.prompts import get_rewriter_prompt

# 结果性描述词：出现在 rewritten_question 中说明 LLM 复述了上一轮回答，而非改写问题
_INVALID_RESULT_WORDS = ("暂无", "没有找到", "未找到", "查询结果", "条记录")

# 移除约束类追问（"不要限制地区/去掉时间限制/不要按公司分"）：
# LLM 对这类追问不稳定（常幻觉保留原约束或复述答案），用确定性规则处理
_REMOVAL_INTENT_RE = re.compile(r"(不要|不用|无需|取消|去掉|移除|删除|别)[^。？！]{0,8}(限制|筛选|过滤|按|区分)")
_REMOVAL_TARGET_RE = re.compile(r"(地区|区域|时间|日期|公司|客户|维度|状态|排名)")

# 区域切换/追加类追问（"改成华南/只看华东"）：
# LLM 对这类追问不稳定（曾把"华南"完全丢弃——既不进改写问题也不生成 filter），
# 用确定性规则处理。切换=查询对象切到地区（去掉实体+替换地区 filter）；
# 追加=在现有查询上追加地区约束（保留实体）
_REGION_SWITCH_RE = re.compile(r"(改成|换成|换到|切到|切换到|改为|改到)\s*的?(华东|华南|华北|东北|西南|西北)")
_REGION_APPEND_RE = re.compile(r"(只看|只查|仅看|仅显示|只要|只筛选|只过滤)\s*的?(华东|华南|华北|东北|西南|西北)")

# 完整独立问题判定：自带实体/维度/完整语义（区域词、公司名、最高/排名类），
# 且不含指代/省略词 → 强制 NEW_TOPIC，防止上一轮实体被错误继承
_STANDALONE_TOPIC_RE = re.compile(r"(华东|华南|华北|东北|西南)|(\S{2,12}公司)|(最高|最低|最多|最少|排名|前\d+)")
_REFERENCE_MARK_RE = re.compile(r"(它|他|她|那家|这家|该|呢|改成|只看|不要|再看|刚才|上面)")

# 主语保护：问题自带明确主语（"我/我的"用户引用，或"李四的"人名）时，
# 改写不得把主语替换成上一轮实体公司名
# （曾出现"我的销售额是多少？"被改写成"北京云计算有限公司今年的销售额是多少？"）
_SELF_REF_RE = re.compile(r"我")
_SUBJECT_OF_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,8})的")
_SUBJECT_STOPWORDS = {
    "今年", "去年", "前年", "明年", "本月", "上月", "上个月", "下个月",
    "上半年", "下半年", "华东", "华南", "华北", "东北", "西南", "西北",
    "公司", "客户", "订单",
}


def _subject_token(q: str) -> str:
    """提取"X的"形式的主语（人名等），排除时间/区域/指标词"""
    _LEADING_VERBS = ("帮我", "查询", "查一下", "查查", "看看", "看一下", "统计", "列出", "显示", "查")
    for m in _SUBJECT_OF_RE.finditer(q or ""):
        tok = m.group(1)
        for v in _LEADING_VERBS:
            if tok.startswith(v) and len(tok) > len(v):
                tok = tok[len(v):]
                break
        if len(tok) < 2:
            continue
        if tok in _SUBJECT_STOPWORDS or any(w in tok for w in _SUBJECT_STOPWORDS):
            continue
        if any(w in tok for w in ("销售额", "利润", "公司", "科技", "有限", "业绩")):
            continue
        return tok
    return ""


def _is_standalone_question(user_query: str) -> bool:
    q = (user_query or "").strip()
    if not q or _REFERENCE_MARK_RE.search(q):
        return False
    return bool(_STANDALONE_TOPIC_RE.search(q))


def _build_removal_result(user_query: str, previous_query_state_text: str) -> dict:
    """移除约束类追问的确定性改写

    rewritten_question = 由上一轮 query_state 的 [实体值][时间]指标 拼出的完整问题（不含被移除约束）
    operation = REMOVE 对应约束（merger 的 REMOVE FILTER 按字典相等移除）
    """
    try:
        ps = json.loads(previous_query_state_text) if previous_query_state_text and previous_query_state_text.strip() not in ("", "{}") else {}
    except Exception:
        ps = {}
    if not isinstance(ps, dict):
        ps = {}

    target_word = ""
    m = _REMOVAL_TARGET_RE.search(user_query or "")
    if m:
        target_word = m.group(1)
    if target_word == "区域":
        target_word = "地区"
    elif target_word == "日期":
        target_word = "时间"

    # 构造改写问题：[实体值][时间]指标是多少？
    parts = []
    entity = ps.get("entity")
    if isinstance(entity, dict):
        ev = str(entity.get("value") or "").strip()
        if ev and ev not in ("公司", "客户", str(entity.get("name") or "").strip()):
            parts.append(ev)
    t = ps.get("time") or {}
    tv = str(t.get("value") or "").strip()
    if tv and tv not in ("ALL", "TIME"):
        parts.append(tv)
    mnames = [str(mm.get("name") or "").strip() for mm in (ps.get("metrics") or []) if isinstance(mm, dict)]
    mnames = [mm for mm in mnames if mm]
    core = "和".join(mnames[:2]) if mnames else "销售额"
    rewritten = f"{''.join(parts)}{core}是多少？"

    # 构造 REMOVE 操作
    if target_word == "时间":
        op = {"operation": "REMOVE", "target": {"type": "TIME"}, "value": None}
    elif target_word in ("公司", "客户"):
        op = {"operation": "REMOVE", "target": {"type": "ENTITY"}, "value": None}
    elif target_word == "排名":
        op = {"operation": "REMOVE", "target": {"type": "RANKING"}, "value": None}
    else:
        # 地区/维度/状态/未指明 → 移除匹配的 filter；找不到匹配时 value=None 清空全部 filter
        matched = None
        for f in (ps.get("filters") or []):
            if not isinstance(f, dict):
                continue
            fname = str(f.get("name") or f.get("concept") or "").strip()
            ffield = str(f.get("field") or "").strip()
            if (target_word and (target_word in fname or target_word in ffield)) \
                    or (target_word == "地区" and "region" in ffield):
                matched = f
                break
        op = {"operation": "REMOVE", "target": {"type": "FILTER"}, "value": matched}

    return {"rewritten_question": rewritten, "relation": "FOLLOW_UP", "operations": [op]}


def _build_region_result(user_query: str, previous_query_state_text: str) -> dict | None:
    """区域切换/追加类追问的确定性改写（LLM 会把"华南"完全丢弃，需代码级保障）

    切换型（"改成华南"）：查询对象切换到地区 → REMOVE ENTITY + REPLACE FILTER 地区
    追加型（"只看华东"）：在现有查询上追加约束 → 保留实体 + REPLACE FILTER 地区
    指标/时间从上一轮 query_state 继承（省略补全语义：只替换明确改变的部分）
    """
    q = user_query or ""
    switch_m = _REGION_SWITCH_RE.search(q)
    append_m = _REGION_APPEND_RE.search(q)
    if not switch_m and not append_m:
        return None

    try:
        ps = json.loads(previous_query_state_text) if previous_query_state_text and previous_query_state_text.strip() not in ("", "{}") else {}
    except Exception:
        ps = {}
    if not isinstance(ps, dict):
        ps = {}

    region = (switch_m or append_m).group(2)
    is_switch = bool(switch_m)

    # 从上一轮状态继承指标与时间（与 _build_removal_result 相同的清洗逻辑）
    # 切换型：查询对象变成地区，不带上一轮实体；追加型：保留实体
    parts = []
    entity = ps.get("entity")
    if isinstance(entity, dict) and not is_switch:
        ev = str(entity.get("value") or "").strip()
        if ev and ev not in ("公司", "客户", str(entity.get("name") or "").strip()):
            parts.append(ev)
    t = ps.get("time") or {}
    tv = str(t.get("value") or "").strip()
    if tv and tv not in ("ALL", "TIME"):
        parts.append(tv)
    mnames = [str(mm.get("name") or "").strip() for mm in (ps.get("metrics") or []) if isinstance(mm, dict)]
    mnames = [mm for mm in mnames if mm]
    core = "和".join(mnames[:2]) if mnames else "销售额"

    rewritten = f"{''.join(parts)}{region}{core}是多少？"
    region_filter = {"concept": "地区", "field": "region", "table": "orders",
                     "operator": "=", "value": region}
    operations = [{"operation": "REPLACE", "target": {"type": "FILTER"}, "value": region_filter}]
    if is_switch:
        # 切换型：去掉上一轮实体（公司），查询对象切换到地区
        operations.insert(0, {"operation": "REMOVE", "target": {"type": "ENTITY"}, "value": None})

    print(f"[DEBUG] Rewriter 区域确定性改写: type={'SWITCH' if is_switch else 'APPEND'}, region={region}, rewritten={rewritten!r}")
    return {"rewritten_question": rewritten, "relation": "FOLLOW_UP", "operations": operations}


QUERY_STATE_SCHEMA = """
{
    "version": 3,
    "entity": null,
    "metrics": [],
    "dimensions": [],
    "filters": [],
    "time": null,
    "ranking": null,
    "comparison": null,
    "extensions": {}
}
"""


def create_rewriter_node():
    """创建 CONTEXT QUESTION REWRITER 节点"""

    def rewriter_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        llm = get_llm()

        user_query = state.get("user_query", "")
        previous_query_state_text = state.get("current_query_state_text", "{}")
        previous_answer = state.get("previous_answer", "") or ""

        prompt = get_rewriter_prompt(
            user_query=user_query,
            previous_query_state=previous_query_state_text,
            query_state_schema=QUERY_STATE_SCHEMA,
            previous_answer=previous_answer
        )

        def _parse_rw(raw: str) -> dict:
            raw = raw.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            elif raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            return json.loads(raw.strip())

        def _valid_rw(rw: str) -> bool:
            """rewritten_question 必须是待查询的问题，防止 LLM 复述上一轮回答/结果描述"""
            rw = (rw or "").strip()
            if not rw:
                return False
            # 复述上一轮回答（整句相同或是其子串）
            if previous_answer and (rw == previous_answer.strip() or rw in previous_answer):
                return False
            # 包含结果性描述词
            if any(w in rw for w in _INVALID_RESULT_WORDS):
                return False
            # 必须是疑问形态
            return any(w in rw for w in ("？", "?", "多少", "哪些", "哪家", "什么", "吗", "呢", "怎么", "如何"))

        response = llm.invoke(prompt)

        try:
            result = _parse_rw(response.content)
        except Exception as e:
            print(f"[DEBUG] Rewriter Parse Error: {e}")
            result = {}

        if not _valid_rw(result.get("rewritten_question")):
            # 纠正重试：明确告知上一次输出的问题
            corrective = (
                "\n\n【重要纠正】你刚才输出的 rewritten_question 不是有效的查询问题"
                "（可能是复述了上一轮的回答或结果描述）。\n"
                "rewritten_question 必须是一个完整的、待查询的问题"
                "（以\"是多少/有哪些/哪家\"等疑问形态结尾）。\n"
                "请严格按输出格式重新输出 JSON。"
            )
            try:
                result = _parse_rw(llm.invoke(prompt + corrective).content)
            except Exception as e:
                print(f"[DEBUG] Rewriter Retry Parse Error: {e}")
                result = {}

        if not _valid_rw(result.get("rewritten_question")):
            # 兜底降级：按无上下文的新问题处理，避免把答案当问题传播到下游
            print(f"[DEBUG] Rewriter 兜底降级: {result.get('rewritten_question')!r}")
            result = {"rewritten_question": user_query, "relation": "NEW_TOPIC", "operations": []}

        # 主语保护：问题自带明确主语（我/人名）时，改写不得引入上一轮实体公司名
        prev_entity_value = ""
        try:
            _ps = json.loads(previous_query_state_text) if previous_query_state_text else {}
            _ent = _ps.get("entity") if isinstance(_ps, dict) else None
            if isinstance(_ent, dict):
                prev_entity_value = str(_ent.get("value") or "").strip()
        except Exception:
            prev_entity_value = ""

        if prev_entity_value and prev_entity_value not in (user_query or ""):
            self_ref = bool(_SELF_REF_RE.search(user_query or ""))
            person = "" if self_ref else _subject_token(user_query or "")

            def _subject_violated(r: dict) -> bool:
                rw = str(r.get("rewritten_question") or "")
                return bool(rw) and prev_entity_value in rw

            if (self_ref or person) and _subject_violated(result):
                subject_desc = "我（当前登录用户本人）" if self_ref else f"「{person}」（某位员工）"
                corrective = (
                    f"\n\n【重要纠正】当前问题的主语是 {subject_desc}，"
                    f"与上一轮提到的公司「{prev_entity_value}」无关。"
                    "请按新话题处理：relation 用 NEW_TOPIC，rewritten_question 保留原问题主语（"
                    + ("\"我\"指当前登录用户，禁止替换为任何公司名" if self_ref else "人名保留原文")
                    + "），operations 中给出指标/时间等完整要素，禁止把上一轮实体合并进问题。请重新输出 JSON。"
                )
                try:
                    result = _parse_rw(llm.invoke(prompt + corrective).content)
                except Exception as e:
                    print(f"[DEBUG] Rewriter 主语纠正重试解析失败: {e}")
            if (self_ref or person) and _subject_violated(result):
                # 确定性兜底：保留原问题原文 + 从问题中提取指标/时间构造 ops，
                # 避免 NEW_TOPIC + 空 operations 产生空 query_state（会被 validator 拦截）
                print(f"[DEBUG] Rewriter 主语保护兜底: {result.get('rewritten_question')!r}")
                _metric_words = ("销售额", "利润", "订单量", "业绩", "数量", "成本")
                _time_words = ("去年", "今年", "上月", "本月的", "上个月", "本月", "前年", "明年")
                _ops = [
                    {"operation": "ADD", "target": {"type": "METRIC"},
                     "value": {"name": w, "value": w}}
                    for w in _metric_words if w in (user_query or "")
                ][:2]
                for w in _time_words:
                    if w.strip("的") in (user_query or ""):
                        _ops.append({"operation": "ADD", "target": {"type": "TIME"},
                                     "value": {"name": "时间", "value": w.strip("的")}})
                        break
                result = {"rewritten_question": user_query, "relation": "NEW_TOPIC", "operations": _ops}

        # 完整独立问题：确定性裁决强制 NEW_TOPIC（优先于 LLM 的 FOLLOW_UP 判断），
        # 防止上一轮实体（如公司名）被继承到无关查询。
        # 注意：只覆盖 relation/rewritten_question，必须保留 LLM 的 operations——
        # merger 在 NEW_TOPIC 时会重置状态后再应用 operations，清空会导致空 query_state
        try:
            if _is_standalone_question(user_query):
                result["rewritten_question"] = user_query
                result["relation"] = "NEW_TOPIC"
                print(f"[DEBUG] Rewriter 独立问题强制 NEW_TOPIC: {user_query}")
        except Exception as e:
            print(f"[DEBUG] Rewriter 独立问题检查失败: {e}")

        # 移除约束类追问：确定性规则最终裁决（覆盖 LLM 输出）
        try:
            if _REMOVAL_INTENT_RE.search(user_query or ""):
                result = _build_removal_result(user_query, previous_query_state_text)
                print(f"[DEBUG] Rewriter 移除约束确定性处理: {result}")
        except Exception as e:
            print(f"[DEBUG] Rewriter 移除约束处理失败: {e}")

        # 区域切换/追加类追问（"改成华南/只看华东"）：确定性规则最终裁决（覆盖 LLM 输出）
        try:
            _region_result = _build_region_result(user_query, previous_query_state_text)
            if _region_result is not None:
                result = _region_result
        except Exception as e:
            print(f"[DEBUG] Rewriter 区域约束处理失败: {e}")

        content = json.dumps(result, ensure_ascii=False)

        elapsed = time.time() - start_time

        # 调试输出
        print(f"[DEBUG] Rewriter Input: user_query={user_query}")
        print(f"[DEBUG] Rewriter Output: {content[:500]}")
        print(f"[TIMER] Rewriter: {elapsed:.2f}s")

        try:
            result = json.loads(content)
            return {
                "rewritten_question": result.get("rewritten_question", user_query),
                "relation": result.get("relation", "NEW_TOPIC"),
                "operations": result.get("operations", []),
                "node_timings": {"rewriter": elapsed}
            }
        except Exception as e:
            print(f"[DEBUG] Rewriter Parse Error: {e}")
            return {
                "rewritten_question": user_query,
                "relation": "NEW_TOPIC",
                "operations": [],
                "node_timings": {"rewriter": elapsed}
            }

    return rewriter_node


def create_intent_analyzer_node():
    """创建 INTENT ANALYZER 节点"""
    import time

    from ...llm.prompts import INTENT_ANALYZER_PROMPT

    def intent_analyzer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== INTENT ANALYZER NODE INPUT ==========")
        print(f"rewritten_question: {state.get('rewritten_question', state.get('user_query', ''))}")
        print(f"query_state: {state.get('current_query_state_text', '{}')}")
        print(f"=================================================\n")

        llm = get_llm()

        rewritten_question = state.get("rewritten_question", state.get("user_query", ""))
        query_state = state.get("current_query_state_text", "{}")

        prompt = INTENT_ANALYZER_PROMPT.format(
            rewritten_question=rewritten_question,
            query_state=query_state
        )

        response = llm.invoke(prompt)
        content = response.content

        elapsed = time.time() - start_time

        print(f"\n========== INTENT ANALYZER NODE OUTPUT ==========")
        print(f"intent: {content[:200]}")
        print(f"[TIMER] Intent Analyzer: {elapsed:.2f}s")
        print(f"=================================================\n")

        try:
            result = json.loads(content)
            return {"intent": result.get("intent", "DATA_QUERY"), "node_timings": {"intent_analyzer": elapsed}}
        except:
            return {"intent": "DATA_QUERY", "node_timings": {"intent_analyzer": elapsed}}

    return intent_analyzer_node
