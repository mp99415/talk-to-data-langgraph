"""
语义解析节点
"""

import json
import re
import time
from typing import Dict, Any, Set
from ...llm.client import get_llm


def extract_keywords_from_question(question: str) -> Set[str]:
    """从问题中提取关键词"""
    if not question:
        return set()
    
    # 转换为小写进行匹配
    question_lower = question.lower()
    
    # 常见业务关键词
    business_keywords = {
        # 指标
        "销售额", "销售", "收入", "利润", "成本", "订单", "数量", "客单价", "平均", "最大", "最小", "累计", "总额",
        # 维度
        "公司", "企业", "客户", "地区", "区域", "城市", "省份", "国家", "部门", "产品", "类别", "渠道", "行业", "年度", "月份", "季度", "日期",
        # 动作
        "排名", "前几", "前N", "最高", "最低", "最好", "最差", "排序",
    }
    
    # 从问题中提取
    keywords = set()
    for kw in business_keywords:
        if kw in question:
            keywords.add(kw)
    
    # 提取英文词（表名、字段名可能用英文）
    english_words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', question)
    keywords.update([w.lower() for w in english_words if len(w) > 2])
    
    return keywords


def prune_schema_context(
    schema_text: str,
    metadata_text: str,
    keywords: Set[str]
) -> tuple[str, str]:
    """
    裁剪 Schema Context，只保留与问题相关的表和字段
    
    策略：
    1. 提取 Schema 中包含关键词的表和字段
    2. 提取 Metadata 中包含关键词的维度定义和值
    3. 如果没有任何匹配，返回空（让 LLM 根据完整 schema 判断）
    """
    if not keywords:
        return schema_text, metadata_text
    
    pruned_schema = ""
    pruned_metadata = ""
    
    # ========== 裁剪 Schema ==========
    current_table = ""
    current_fields = []
    in_table_block = False
    
    for line in schema_text.split('\n'):
        # 检测表名行
        table_match = re.match(r'^表:\s*(\w+)\s*$', line)
        if table_match:
            # 保存上一个表的数据
            if current_table and current_fields:
                # 检查表名是否包含关键词
                table_match_kw = any(kw.lower() in current_table.lower() for kw in keywords)
                field_match_kw = any(
                    any(kw.lower() in field.lower() for kw in keywords)
                    for field in current_fields
                )
                if table_match_kw or field_match_kw:
                    pruned_schema += f"\n表: {current_table}\n"
                    pruned_schema += '\n'.join(current_fields) + '\n'
            
            current_table = table_match.group(1)
            current_fields = []
            in_table_block = True
        elif in_table_block and line.strip().startswith('-'):
            current_fields.append(line)
        elif line.strip() and not line.strip().startswith('-'):
            in_table_block = False
    
    # 处理最后一个表
    if current_table and current_fields:
        table_match_kw = any(kw.lower() in current_table.lower() for kw in keywords)
        field_match_kw = any(
            any(kw.lower() in field.lower() for kw in keywords)
            for field in current_fields
        )
        if table_match_kw or field_match_kw:
            pruned_schema += f"\n表: {current_table}\n"
            pruned_schema += '\n'.join(current_fields) + '\n'
    
    # 如果裁剪后为空，保留原始 Schema（说明没有匹配到）
    if not pruned_schema.strip():
        pruned_schema = schema_text
    
    # ========== 裁剪 Metadata ==========
    if metadata_text:
        in_section = False
        current_section_lines = []
        section_name = ""
        
        for line in metadata_text.split('\n'):
            # 检测章节标题
            section_match = re.match(r'^【(.+)】$', line.strip())
            if section_match:
                # 保存上一个章节
                if current_section_lines:
                    section_content = '\n'.join(current_section_lines)
                    if any(kw.lower() in section_content.lower() for kw in keywords):
                        pruned_metadata += f"【{section_name}】\n" + section_content + "\n"
                
                section_name = section_match.group(1)
                current_section_lines = []
                in_section = True
            elif in_section and line.strip():
                current_section_lines.append(line)
            else:
                in_section = False
        
        # 处理最后一个章节
        if current_section_lines and section_name:
            section_content = '\n'.join(current_section_lines)
            if any(kw.lower() in section_content.lower() for kw in keywords):
                pruned_metadata += f"【{section_name}】\n" + section_content + "\n"
    
    # 如果裁剪后为空，保留原始 Metadata
    if not pruned_metadata.strip():
        pruned_metadata = metadata_text
    
    return pruned_schema, pruned_metadata


def create_semantic_resolver_node():
    """创建 SEMANTIC / METRIC RESOLVER 节点"""

    def semantic_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SEMANTIC RESOLVER NODE INPUT ==========")
        print(f"query_state: {state.get('query_state')}")
        
        query_state = state.get("query_state", {})
        schema = state.get("schema", {})
        metadata = state.get("metadata", {})
        
        # 格式化 Schema 信息
        columns = schema.get("columns", {})
        schema_text = "数据库表结构：\n"
        
        if isinstance(columns, dict):
            for table, cols in columns.items():
                schema_text += f"\n表: {table}\n"
                if isinstance(cols, list):
                    for col in cols:
                        if isinstance(col, dict):
                            schema_text += f"  - {col.get('name', '')} ({col.get('type', '')})"
                            if col.get('comment'):
                                schema_text += f" - {col['comment']}"
                            schema_text += "\n"
        elif isinstance(columns, list):
            # 如果是列表，按表名分组
            table_cols = {}
            for col in columns:
                if isinstance(col, dict):
                    table = col.get('TABLE_NAME', 'unknown')
                    if table not in table_cols:
                        table_cols[table] = []
                    table_cols[table].append(col)
            for table, cols in table_cols.items():
                schema_text += f"\n表: {table}\n"
                for col in cols:
                    schema_text += f"  - {col.get('COLUMN_NAME', '')} ({col.get('DATA_TYPE', '')})"
                    if col.get('COLUMN_COMMENT'):
                        schema_text += f" - {col['COLUMN_COMMENT']}"
                    schema_text += "\n"
        
        # 添加外键关系
        foreign_keys = schema.get("foreign_keys", [])
        if foreign_keys:
            schema_text += "\n【外键关系】\n"
            for fk in foreign_keys:
                if isinstance(fk, dict):
                    schema_text += f"- {fk.get('TABLE_NAME', '')}.{fk.get('COLUMN_NAME', '')} → {fk.get('REFERENCED_TABLE_NAME', '')}.{fk.get('REFERENCED_COLUMN_NAME', '')}\n"
        
        # 格式化 Metadata 信息
        metadata_text = ""
        if metadata:
            dims = metadata.get("semantic_dimensions", [])
            values = metadata.get("semantic_dimension_values", [])
            aliases = metadata.get("semantic_value_aliases", [])

            metadata_text = "\n=== 业务语义映射 ===\n"

            # 维度定义
            if dims:
                metadata_text += "\n【维度定义】\n"
                for d in dims:
                    metadata_text += f"- {d.get('dimension_name', '')} ({d.get('dimension_code', '')}): {d.get('table_name', '')}.{d.get('field_name', '')}\n"

            # 维度值
            if values:
                metadata_text += "\n【维度值映射】\n"
                for v in values:
                    metadata_text += f"  {v.get('value_name', '')} → {v.get('physical_value', '')} ({v.get('value_code', '')})\n"

            # 别名
            if aliases:
                metadata_text += "\n【值别名】\n"
                for a in aliases:
                    metadata_text += f"  {a.get('alias', '')} → {a.get('dimension_id', '')}\n"

        # 调用 LLM 进行语义解析
        llm = get_llm()

        # 使用 get_semantic_prompt 函数替换变量
        from ...llm.prompts import get_semantic_prompt
        from datetime import date
        rewritten_question = state.get("rewritten_question", "")

        # 提取当前用户信息（用于"我的"等用户引用的语义解析）
        user_info_list = state.get("user_info", []) or []
        user_context = ""
        if user_info_list:
            current_user = user_info_list[0] if isinstance(user_info_list, list) else user_info_list
            if isinstance(current_user, dict):
                user_id_val = current_user.get("user_id", "")
                username_val = current_user.get("username", "") or current_user.get("name", "")
                region_val = current_user.get("region", "")
                user_context = (
                    f"\n【当前用户信息】\n"
                    f"- user_id: {user_id_val}\n"
                    f"- username: {username_val}\n"
                    f"- region: {region_val}\n"
                    f"\n当用户问题中出现\"我的\"、\"我\"等指代当前用户的词时，必须基于以上用户信息解析：\n"
                    f"  - 如\"我的销售额\"→ 解析为按 sales_id = {user_id_val} 过滤的销售额\n"
                    f"  - 如\"我的客户\"→ 解析为按 sales_id = {user_id_val} 过滤的客户\n"
                    f"  - 如\"我负责的订单\"→ 解析为按 sales_id = {user_id_val} 过滤的订单\n"
                )

        # Schema 裁剪：只传入与问题相关的表和字段
        keywords = extract_keywords_from_question(rewritten_question)
        print(f"[DEBUG] Extracted keywords: {keywords}")

        pruned_schema, pruned_metadata = prune_schema_context(
            schema_text, metadata_text, keywords
        )
        print(f"[DEBUG] Schema pruned: {len(schema_text)} -> {len(pruned_schema)} chars")

        prompt = get_semantic_prompt(
            query_state=json.dumps(query_state, ensure_ascii=False),
            rewritten_question=rewritten_question,
            schema_context=pruned_schema + pruned_metadata,
            current_date=date.today().strftime("%Y-%m-%d"),
            user_context=user_context
        )
        
        try:
            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # 清理 JSON 格式
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            semantic_result = json.loads(content)
            
            # 调试日志
            print(f"[DEBUG] LLM semantic_result: {json.dumps(semantic_result, ensure_ascii=False)[:500]}")
            
            # 确保必要的字段存在
            if "status" not in semantic_result:
                semantic_result["status"] = "RESOLVED"
            if "resolved" not in semantic_result:
                semantic_result["resolved"] = (semantic_result.get("status") == "RESOLVED")
            
            # 确保 extensions 字段存在（用于嵌套查询等扩展功能）
            if "extensions" not in semantic_result:
                semantic_result["extensions"] = {}

            # ========== 用户引用解析（通用/配置驱动） ==========
            # 从 schema.user_reference_fields 中读取"用户引用字段配置"，
            # 自动处理"我的X"/"本部门X"/"本区X"等用户引用场景。
            # 新增字段只需在数据库 metadata 中配置，无需修改代码。
            try:
                from ...config.user_reference_config import (
                    inject_user_reference_filters,
                    get_default_config,
                )
                rewritten_q = rewritten_question or state.get("rewritten_question", "") or state.get("user_query", "")
                user_ref_fields_map = (schema or {}).get("user_reference_fields") or {}
                inject_user_reference_filters(
                    semantic_result=semantic_result,
                    query_state=query_state,
                    user_info_list=user_info_list,
                    rewritten_q=rewritten_q,
                    config=get_default_config(),
                    user_ref_fields=user_ref_fields_map,
                )
            except Exception as e:
                print(f"[DEBUG] user_reference injection error: {str(e)}")
            
            # ========== 嵌套查询处理（可选增强：失败只跳过检测，不影响主解析结果） ==========
            # 主路径：业务规则第八章指导语义解析 LLM 直接输出 extensions.sub_query
            # 兜底路径：LLM 漏检时，用正则快速检测捕获常见模式（确定性、零成本、无额外 LLM 调用）
            # 注意：必须用相对导入（与文件顶部 from ...llm.client 一致），
            #       绝对导入在部分运行方式下 ModuleNotFoundError，曾导致整个 semantic_result 被降级
            try:
                rewritten = rewritten_question or state.get("rewritten_question", "")
                metrics_list = semantic_result.get("metrics", [])
                extensions = semantic_result.get("extensions", {})
                sub_query = extensions.get("sub_query") if isinstance(extensions, dict) else None

                # 兜底：LLM 未输出 sub_query 且问题含排名词 → 正则快速检测
                if (not sub_query and len(metrics_list) >= 1 and rewritten and
                    re.search(r'最高|最低|最多|最少|最好|最差|前\d+|排名', rewritten)):
                    from ...llm.nested_query_detector import quick_detect_nested_query
                    quick_result = quick_detect_nested_query(rewritten)
                    if quick_result and quick_result.get("is_nested"):
                        sub_query = quick_result.get("sub_query", {}) or None
                        if sub_query:
                            print(f"[DEBUG] 正则兜底检测到嵌套查询: {sub_query}")

                if sub_query:
                    # 1) 字段补全：LLM 输出的 sub_query 可能缺 field/table，必须补全后才注入查询计划
                    sub_metric_name = sub_query.get("metric", "")
                    if not sub_query.get("field"):
                        # 1a) 先在 semantic_result.metrics 中查找（子指标恰好也是当前指标时）
                        for m in metrics_list:
                            concept = m.get("concept", "") or m.get("name", "") or m.get("value", "")
                            field = m.get("field", "")
                            if field and (sub_metric_name in concept or concept in sub_metric_name):
                                sub_query["field"] = field
                                sub_query["table"] = m.get("table", "orders")
                                sub_query["aggregation"] = m.get("aggregation", "SUM")
                                break
                    if not sub_query.get("field"):
                        # 1b) 查找失败时，根据 Schema 调 LLM 解析子指标物理字段
                        from ...llm.nested_query_detector import resolve_metric_field
                        field_info = resolve_metric_field(sub_metric_name, schema_text, llm)
                        if field_info:
                            sub_query["table"] = field_info.get("table", "")
                            sub_query["field"] = field_info.get("field", "")
                            sub_query["aggregation"] = field_info.get("aggregation", "SUM")

                    # 2) 时间归属：时间词在排序词之前（如"今年销售额最高"）→ 时间属于子查询
                    if sub_query.get("field") and semantic_result.get("time"):
                        ranking_match = re.search(r'最高|最低|最多|最少|前\d+', rewritten)
                        if ranking_match:
                            time_words = ["今年", "去年", "前年", "今年至今", "上个月", "上月", "本月",
                                          "上个季度", "本季度", "最近30天", "最近7天", "最近"]
                            before_ranking = rewritten[:ranking_match.start()]
                            if any(tw in before_ranking for tw in time_words):
                                if not sub_query.get("time"):
                                    sub_query["time"] = semantic_result.get("time")
                                semantic_result["time"] = None
                                print(f"[DEBUG] 时间条件归属子查询: {sub_query.get('time')}")

                    # 3) 只有拿到物理字段才写入，避免不完整的 sub_query 干扰 SQL 编译
                    if sub_query.get("field"):
                        semantic_result["extensions"]["sub_query"] = sub_query
                        print(f"[DEBUG] sub_query 最终配置: {sub_query}")
                    else:
                        semantic_result["extensions"].pop("sub_query", None)
                        print(f"[DEBUG] sub_query 缺少物理字段，已丢弃: {sub_query}")
            except Exception as nested_err:
                # 检测/补全是增强功能，任何失败都不能降级主解析结果
                print(f"[DEBUG] 嵌套查询处理失败（已跳过，不影响主结果）: {nested_err}")
            # ========== 嵌套查询处理结束 ==========
            
            # 调试日志 - 输出 extensions
            print(f"[DEBUG] semantic_result.extensions: {semantic_result.get('extensions')}")
            
            # 补全 time 字段：嵌套查询时补全到 sub_query.time（时间约束排序指标），普通查询补全到主 time
            from datetime import date
            today = date.today()
            _ext = semantic_result.get("extensions", {})
            _sub_q = _ext.get("sub_query") if isinstance(_ext, dict) else None
            _nested = bool(_sub_q and _sub_q.get("field"))

            def _fill_time(existing_obj, default_table):
                """补全时间对象的 start/end，返回补全后的 time dict"""
                time_value = "今年"
                qs_time = query_state.get("time") if isinstance(query_state, dict) else None
                if isinstance(qs_time, dict) and qs_time.get("value"):
                    time_value = qs_time.get("value")
                elif isinstance(existing_obj, dict) and existing_obj.get("value"):
                    time_value = existing_obj.get("value")

                if time_value in ("去年", "LAST_YEAR"):
                    start = f"{today.year - 1}-01-01"
                    end = f"{today.year}-01-01"
                else:  # 今年或其他
                    start = f"{today.year}-01-01"
                    end = f"{today.year + 1}-01-01"

                filled = dict(existing_obj) if isinstance(existing_obj, dict) else {}
                filled.update({
                    "name": filled.get("name", "时间"),
                    "value": time_value,
                    "type": "YEAR",
                    "start": start,
                    "end": end,
                    "field": filled.get("field", "order_date"),
                    "table": filled.get("table", default_table)
                })
                return filled

            if _nested:
                # 嵌套查询：时间补全到 sub_query.time，主查询不设时间
                if not isinstance(_sub_q.get("time"), dict) or not _sub_q["time"].get("start") or not _sub_q["time"].get("end"):
                    _sub_q["time"] = _fill_time(_sub_q.get("time"), _sub_q.get("table", "orders"))
                    print(f"[DEBUG] 嵌套查询时间补全到 sub_query.time: {_sub_q['time']}")
            else:
                time_obj = semantic_result.get("time")
                if not isinstance(time_obj, dict) or not time_obj.get("start") or not time_obj.get("end"):
                    semantic_result["time"] = _fill_time(time_obj, "orders")
            
        except Exception as e:
            print(f"[DEBUG] Semantic resolver error: {str(e)}")
            from datetime import date
            today = date.today()
            
            # 从 query_state 获取时间信息
            time_obj = query_state.get("time") if isinstance(query_state, dict) else None
            time_value = "今年"
            if isinstance(time_obj, dict):
                time_value = time_obj.get("value", "今年")
            
            # 根据时间值计算 start 和 end
            if time_value in ("去年", "LAST_YEAR"):
                start = f"{today.year - 1}-01-01"
                end = f"{today.year}-01-01"
            elif time_value in ("明年", "NEXT_YEAR"):
                start = f"{today.year + 1}-01-01"
                end = f"{today.year + 2}-01-01"
            else:  # 今年或其他
                start = f"{today.year}-01-01"
                end = f"{today.year + 1}-01-01"
            
            semantic_result = {
                "status": "RESOLVED",
                "resolved": True,
                "entities": [],
                "metrics": [{"name": "销售额", "value": "销售额"}],
                "dimensions": [],
                "filters": [],
                "time": {
                    "name": "时间",
                    "value": time_value,
                    "type": "YEAR",
                    "start": start,
                    "end": end,
                    "field": "order_date",
                    "table": "orders"
                },
                "ranking": None,
                "comparison": None,
                "error": str(e)
            }

        # ========== 实体值 → 过滤器注入 ==========
        # LLM 输出不稳定：可能把实体值放在 entities 里但不生成对应 filter
        # （如"北京云计算有限公司今年的利润是多少？"只出 entities，filters 里只有用户引用），
        # 没有 filter 时 SQL 只过滤当前用户，答案归因错误。这里补注入，
        # 并把公司实体字段归一化为 orders.customer_id（业务值），由 filter_value_resolver 解析为物理 id。
        # 防垃圾值：排名类查询 LLM 会把 entities[0].value 填成"公司"/"customer_id"等泛化词，
        # 注入前用 customers 表精确匹配验证，不是真实公司名一律跳过
        try:
            from .filter_value_resolver import query_customer_ids_by_names
            _company_concepts = ("公司", "客户", "公司名", "客户名", "公司名称", "客户名称")
            _existing_filters = semantic_result.get("filters", []) or []
            _ent_values = []
            for _ent in (semantic_result.get("entities") or []):
                if not isinstance(_ent, dict):
                    continue
                _ent_value = str(_ent.get("value") or "").strip()
                _ent_concept = str(_ent.get("concept") or "").strip()
                if not _ent_value or _ent_concept not in _company_concepts:
                    continue
                if _ent_value == _ent_concept or _ent_value in _company_concepts:
                    continue
                if _ent_value not in _ent_values:
                    _ent_values.append(_ent_value)
            # 一次性精确匹配验证，只有真实存在的公司名才注入
            _valid_name_map = query_customer_ids_by_names(_ent_values) if _ent_values else {}
            # 人名兜底："李四"这类他人姓名可能被 LLM 当作公司实体输出；
            # 能在 users 表精确匹配到真实用户的，注入 sales_id 过滤而非 customer 过滤
            from .filter_value_resolver import query_user_ids_by_names as _q_user_ids
            _non_customer = [v for v in _ent_values if v not in _valid_name_map]
            _user_name_map = _q_user_ids(_non_customer) if _non_customer else {}
            for _ent in (semantic_result.get("entities") or []):
                if not isinstance(_ent, dict):
                    continue
                _ent_value = str(_ent.get("value") or "").strip()
                _ent_concept = str(_ent.get("concept") or "").strip()
                if _ent_value not in _valid_name_map or _ent_concept not in _company_concepts:
                    continue
                # 已有同值的 filter 则跳过（LLM 已生成，如 customer_id = '北京云计算有限公司'）
                _already = any(
                    isinstance(f, dict) and str(f.get("value", "")) == _ent_value
                    for f in _existing_filters
                )
                if _already:
                    continue
                _ent_field = str(_ent.get("field") or "").strip()
                _ent_table = str(_ent.get("table") or "").strip()
                if _ent_field not in ("customer_id",):
                    # name/id 等统一归一到 customer_id（orders 表），业务名由下游解析
                    _ent_field = "customer_id"
                    _ent_table = "orders"
                _entity_filter = {
                    "concept": _ent_concept,
                    "field": _ent_field,
                    "table": _ent_table,
                    "operator": "=",
                    "value": _ent_value,
                    "physical_value": _ent_value,
                    "semantic_type": "dimension",
                    "match_type": _ent.get("match_type") or "ENTITY",
                    "source": "entity_value_injection",
                }
                _existing_filters.append(_entity_filter)
                print(f"[DEBUG][semantic] 注入实体 filter: {_ent_table}.{_ent_field} = {_ent_value!r}")

            # 人名实体注入：value 是真实用户名（非公司名）时注入 sales_id 过滤
            for _ent in (semantic_result.get("entities") or []):
                if not isinstance(_ent, dict):
                    continue
                _ent_value = str(_ent.get("value") or "").strip()
                if _ent_value not in _user_name_map:
                    continue
                _uid = _user_name_map[_ent_value]
                # LLM 已生成同值/同义 filter（如 sales_id='李四'）则跳过，避免重复条件
                _already = any(
                    isinstance(f, dict) and str(f.get("value", "")) in (_ent_value, _uid)
                    for f in _existing_filters
                )
                if _already:
                    continue
                _user_filter = {
                    "concept": str(_ent.get("concept") or "员工"),
                    "field": "sales_id",
                    "table": "orders",
                    "operator": "=",
                    "value": _uid,
                    "physical_value": _uid,
                    "physical_value_resolved": True,
                    "semantic_type": "filter",
                    "match_type": _ent.get("match_type") or "ENTITY",
                    "source": "entity_user_injection",
                }
                _existing_filters.append(_user_filter)
                print(f"[DEBUG][semantic] 人名实体注入 sales_id filter: sales_id = {_uid!r} ({_ent_value})")
            semantic_result["filters"] = _existing_filters
            if isinstance(query_state, dict) and isinstance(query_state.get("filters"), list):
                query_state["filters"].extend(
                    f for f in _existing_filters
                    if f.get("source") in ("entity_value_injection", "entity_user_injection")
                )
        except Exception as e:
            print(f"[DEBUG][semantic] 实体 filter 注入失败: {e}")

        elapsed = time.time() - start_time

        print(f"========== SEMANTIC RESOLVER NODE OUTPUT ==========")
        print(f"semantic_result: {json.dumps(semantic_result, ensure_ascii=False)[:500]}")
        print(f"[DEBUG] semantic_result.time: {semantic_result.get('time')}")
        print(f"[TIMER] Semantic Resolver: {elapsed:.2f}s")
        print(f"==================================================\n")

        # 保留 query_state 到输出
        return {
            "semantic_result": semantic_result,
            "query_state": query_state,
            "node_timings": {"semantic_resolver": elapsed}
        }

    return semantic_resolver_node


def create_value_semantic_resolver_node():
    """创建 VALUE SEMANTIC RESOLVER 节点"""
    
    def value_semantic_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        lookup_items = state.get("lookup_items", [])
        query_result = state.get("query_result", [])
        
        result = {
            "resolved": True,
            "resolved_values": []
        }
        
        return {"value_semantic_result": result}
    
    return value_semantic_resolver_node
