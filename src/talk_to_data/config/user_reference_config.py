"""
用户引用通用配置
=================

通过配置驱动"我的X"、"本部门X"、"本区X"等用户引用场景的通用化处理。

使用方式：
    from talk_to_data.config.user_reference_config import (
        get_default_config, parse_user_reference_from_schema
    )

    config = get_default_config()
    user_ref_fields = parse_user_reference_from_schema(schema, config)
    inject_user_reference_filters(semantic_result, query_state, user_info, rewritten_q, config, user_ref_fields)

扩展性：
    - 新增字段：只需在数据库 metadata 表中配置，无需改代码
    - 新增关键词：只需扩展 config.keywords
    - 新增用户角色：扩展 config.user_role_property_map
"""

from typing import Dict, Any, List, Optional


# 默认配置
DEFAULT_CONFIG = {
    # 用户引用关键词（中文）—— 注意：单独的"我"放在最前，
    # 因为改写器可能只保留"我"字，丢失"我的"
    "user_reference_keywords": [
        "我", "我的", "我负责", "我名下", "我经手", "我签订", "我对接",
        "我自己", "归属于我", "分配给我", "属于我", "我签的", "我谈的",
        "我开的", "我做的",
    ],
    # 部门引用关键词
    "department_reference_keywords": [
        "本部门", "我们部门", "我部门", "我们组", "我组",
        "我所在部门", "归属于部门", "部门内",
    ],
    # 区域引用关键词
    "region_reference_keywords": [
        "本区", "我们区域", "我的区域", "我所在区域",
        "我们大区", "本大区",
    ],
    # 用户角色 → 用户属性的映射
    # owner/creator/approver/assignee 默认取 user_id
    # department 取 department_id, region 取 region
    "user_role_property_map": {
        "owner": ["user_id", "employee_no", "open_id"],
        "creator": ["user_id", "employee_no", "open_id"],
        "approver": ["user_id", "employee_no", "open_id"],
        "assignee": ["user_id", "employee_no", "open_id"],
        "department": ["department_id"],
        "region": ["region"],
    },
    # 占位符映射（LLM 输出中可能出现的占位符）
    "placeholder_map": {
        "${current_user_id}": "user_id",
        "${user.id}": "user_id",
        "${current_user_region}": "region",
        "${user.region}": "region",
        "${current_user_department_id}": "department_id",
        "${user.department_id}": "department_id",
    },
}


def get_default_config() -> Dict[str, Any]:
    """获取默认配置"""
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


def parse_user_reference_from_schema(
    schema: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    从 schema 中解析用户引用字段配置

    支持四种数据源（按优先级合并）：
    1. schema.user_reference_fields（直接配置）
    2. 从列注释中解析 [USER_REFERENCE] 标记
    3. 从 metadata.column_metadata 配置表中读取
    4. schema 顶层 column_metadata（兼容 schema.py 实际写入位置）
    5. 兜底启发式：根据字段名模式自动识别（如 sales_id/owner_id/creator_id/assignee_id/approver_id/department_id/region）

    返回：
        {
            "orders.sales_id": {
                "field": "sales_id",
                "table": "orders",
                "type": "owner",
                "label": "销售负责人",
            },
            ...
        }
    """
    if not isinstance(schema, dict):
        return {}

    user_ref_fields = {}

    # 方式 1: 直接配置
    direct = schema.get("user_reference_fields") or {}
    if isinstance(direct, dict):
        for key, val in direct.items():
            if isinstance(val, dict):
                user_ref_fields[key] = val

    # 方式 2: 从列注释解析 [USER_REFERENCE] 标记
    columns_dict = schema.get("columns") or {}
    if isinstance(columns_dict, dict):
        for table, cols in columns_dict.items():
            if not isinstance(cols, list):
                continue
            for col in cols:
                if not isinstance(col, dict):
                    continue
                comment = col.get("comment") or col.get("COLUMN_COMMENT") or ""
                if "[USER_REFERENCE" not in comment:
                    continue
                field_name = col.get("name") or col.get("COLUMN_NAME")
                if not field_name:
                    continue
                ref_type = "owner"
                ref_label = ""
                import re
                m = re.search(r"\[USER_REFERENCE(?::([^:\]]*))?(?::([^\]]*))?\]", comment)
                if m:
                    if m.group(1):
                        ref_type = m.group(1).strip() or "owner"
                    if m.group(2):
                        ref_label = m.group(2).strip()
                key = f"{table}.{field_name}"
                if key not in user_ref_fields:
                    user_ref_fields[key] = {
                        "field": field_name,
                        "table": table,
                        "type": ref_type,
                        "label": ref_label or "当前用户",
                    }

    # 方式 3: metadata.column_metadata
    metadata = schema.get("metadata") or {}
    if isinstance(metadata, dict):
        col_meta = metadata.get("column_metadata") or []
        if isinstance(col_meta, list):
            for row in col_meta:
                if not isinstance(row, dict):
                    continue
                if not row.get("user_reference"):
                    continue
                table = row.get("table_name")
                field = row.get("column_name")
                if not table or not field:
                    continue
                key = f"{table}.{field}"
                user_ref_fields[key] = {
                    "field": field,
                    "table": table,
                    "type": row.get("user_reference_type") or "owner",
                    "label": row.get("user_reference_label") or "当前用户",
                }

    # 方式 4: schema 顶层 column_metadata
    top_col_meta = schema.get("column_metadata") or []
    if isinstance(top_col_meta, list):
        for row in top_col_meta:
            if not isinstance(row, dict):
                continue
            if not row.get("user_reference"):
                continue
            table = row.get("table_name")
            field = row.get("column_name")
            if not table or not field:
                continue
            key = f"{table}.{field}"
            if key not in user_ref_fields:
                user_ref_fields[key] = {
                    "field": field,
                    "table": table,
                    "type": row.get("user_reference_type") or "owner",
                    "label": row.get("user_reference_label") or "当前用户",
                }

    # 方式 5: 兜底启发式（仅在 user_ref_fields 为空时启用）
    # 基于字段名模式自动识别常见用户引用字段，让方案在没有元数据时也能工作。
    if not user_ref_fields and isinstance(columns_dict, dict):
        OWNER_FIELDS = {
            "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
            "agent_id", "created_by", "updated_by", "manager_id",
            "created_by_id", "updated_by_id",
        }
        DEPARTMENT_FIELDS = {"department_id", "dept_id", "team_id", "group_id"}
        REGION_FIELDS = {"region", "area", "zone"}
        for table, cols in columns_dict.items():
            if not isinstance(cols, list):
                continue
            for col in cols:
                if not isinstance(col, dict):
                    continue
                fname = col.get("name") or col.get("COLUMN_NAME") or ""
                if not fname:
                    continue
                if fname in OWNER_FIELDS:
                    detected_type, label = "owner", "当前用户"
                elif fname in DEPARTMENT_FIELDS:
                    detected_type, label = "department", "当前部门"
                elif fname in REGION_FIELDS:
                    detected_type, label = "region", "当前区域"
                else:
                    continue
                key = f"{table}.{fname}"
                user_ref_fields[key] = {
                    "field": fname,
                    "table": table,
                    "type": detected_type,
                    "label": label,
                }

    return user_ref_fields


def _detect_reference_in_question(
    rewritten_q: str,
    config: Dict[str, Any],
) -> Dict[str, bool]:
    """
    检测问题中包含的用户引用类型

    返回: {"user_ref": bool, "department_ref": bool, "region_ref": bool}
    """
    if not rewritten_q:
        return {"user_ref": False, "department_ref": False, "region_ref": False}

    result = {
        "user_ref": False,
        "department_ref": False,
        "region_ref": False,
    }

    for kw in config.get("user_reference_keywords", []):
        if kw and kw in rewritten_q:
            result["user_ref"] = True
            break

    for kw in config.get("department_reference_keywords", []):
        if kw and kw in rewritten_q:
            result["department_ref"] = True
            break

    for kw in config.get("region_reference_keywords", []):
        if kw and kw in rewritten_q:
            result["region_ref"] = True
            break

    return result


def _resolve_user_value(
    current_user: Dict[str, Any],
    ref_type: str,
    config: Dict[str, Any],
) -> str:
    """
    根据引用类型从当前用户字典中解析出真实值

    例如: owner → 从 user_id/employee_no 中取
          department → 从 department_id 中取
    """
    if not isinstance(current_user, dict):
        return ""

    candidates = (config.get("user_role_property_map") or {}).get(ref_type, ["user_id"])
    if not candidates:
        candidates = ["user_id"]

    for key in candidates:
        val = current_user.get(key)
        if val is not None and val != "":
            return str(val)
    return ""


def _has_self_ref_marker(
    f: Dict[str, Any],
    user_reference_keywords: set,
    self_names: set,
) -> bool:
    """
    判断 filter 是否带"指代当前用户"的标记。

    只有带标记的 filter 才允许被纠正，避免误把"王五的销售额"这类
    合法过滤他人的 filter 改成当前用户。
    """
    bv = str(f.get("business_value", "") or "")
    if bv and (bv in user_reference_keywords or bv in ("当前用户", "我自己", "本人")):
        return True
    mt = str(f.get("match_type", "") or "")
    if mt == "USER_REFERENCE":
        return True
    v = str(f.get("value", "") or "")
    pv = str(f.get("physical_value", "") or "")
    if v.startswith("${") or pv.startswith("${"):
        return True
    if v in self_names or pv in self_names:
        return True
    if f.get("source") == "user_reference_injection":
        return True
    return False


def inject_user_reference_filters(
    semantic_result: Dict[str, Any],
    query_state: Dict[str, Any],
    user_info_list: Any,
    rewritten_q: str,
    config: Optional[Dict[str, Any]] = None,
    user_ref_fields: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """
    通用用户引用注入

    参数:
        semantic_result: 语义解析结果 dict，会就地修改 filters
        query_state: 查询状态 dict，会就地修改 filters
        user_info_list: 用户信息（list 或 dict）
        rewritten_q: 改写后的问题
        config: 用户引用配置（不传则用默认）
        user_ref_fields: 用户引用字段配置（不传则不注入）

    返回:
        注入的 filter 数量
    """
    if not user_info_list or not isinstance(semantic_result, dict):
        return 0
    if not user_ref_fields:
        return 0
    if config is None:
        config = get_default_config()

    current_user = user_info_list[0] if isinstance(user_info_list, list) else user_info_list
    if not isinstance(current_user, dict):
        return 0

    user_ref_kw = set(config.get("user_reference_keywords") or [])
    self_names = {
        str(current_user.get("username") or ""),
        str(current_user.get("name") or ""),
    }
    self_names.discard("")
    ref_detected = _detect_reference_in_question(rewritten_q, config)

    # 收集需要注入的字段（基于关键词检测）
    user_ref_filter_fields = set()
    for ref_cfg in user_ref_fields.values():
        ref_type = ref_cfg.get("type", "owner")
        if ref_type in ("owner", "creator", "approver", "assignee") and ref_detected["user_ref"]:
            user_ref_filter_fields.add(ref_cfg["field"])
        elif ref_type == "department" and ref_detected["department_ref"]:
            user_ref_filter_fields.add(ref_cfg["field"])
        elif ref_type == "region" and ref_detected["region_ref"]:
            user_ref_filter_fields.add(ref_cfg["field"])

    # 注意：这里不再无条件把用户引用字段加入注入范围。
    # 此前的"ref_detected 全 False 也注入"分支会让所有查询都被限定到当前用户
    # （如销售总监问"今年销售额是多少"只返回个人数据而非全公司），
    # 且"查询李四的销售额"这类他人引用会被错注入成当前用户。
    # 数据范围的安全边界由 RBAC Row Policy 兜底，不依赖此注入。

    injected = 0
    existing_filters = semantic_result.get("filters", []) or []
    qs_filters = query_state.get("filters", []) if isinstance(query_state, dict) else []

    for ref_key, ref_cfg in user_ref_fields.items():
        table = ref_cfg.get("table")
        field = ref_cfg.get("field")
        ref_type = ref_cfg.get("type", "owner")
        label = ref_cfg.get("label", "当前用户")

        if field not in user_ref_filter_fields:
            continue

        user_value = _resolve_user_value(current_user, ref_type, config)
        if not user_value:
            continue

        # 检查是否已存在
        already_has = any(
            isinstance(f, dict) and f.get("field") == field and f.get("table") == table
            for f in existing_filters
        )
        if already_has:
            continue

        user_filter = {
            "concept": label,
            "field": field,
            "table": table,
            "operator": "=",
            "value": user_value,
            "physical_value": user_value,
            "semantic_type": "dimension",
            "match_type": "USER_REF",
            "source": "user_reference_injection",
        }

        existing_filters.append(user_filter)
        if isinstance(query_state, dict):
            qs_filters.append(user_filter)
        injected += 1
        print(
            f"[DEBUG][user_ref] 注入用户引用 filter: "
            f"{table}.{field} = {user_value!r} (type={ref_type})"
        )

    if injected > 0:
        semantic_result["filters"] = existing_filters
        if isinstance(query_state, dict):
            query_state["filters"] = qs_filters

    # ========== 占位符替换 + 错误值纠正 ==========
    placeholder_map = config.get("placeholder_map") or {}

    # 构建 field → ref_type 反查表
    field_to_type = {}
    for ref_key, ref_cfg in user_ref_fields.items():
        field_to_type[ref_cfg.get("field")] = ref_cfg.get("type", "owner")

    for f in existing_filters:
        if not isinstance(f, dict):
            continue
        # 占位符替换
        pv = f.get("physical_value", "") or ""
        v = f.get("value", "") or ""
        for ph, prop_key in placeholder_map.items():
            replacement = str(current_user.get(prop_key, "") or "")
            if not replacement:
                continue
            if ph in pv:
                f["physical_value"] = pv.replace(ph, replacement)
                pv = f["physical_value"]
            if ph in v:
                f["value"] = v.replace(ph, replacement)
                v = f["value"]

        # 错误值纠正：带"自我引用"标记的用户引用字段，value/physical_value 为
        # username/name/引用关键词/空值/占位符/非数字串时，纠正为真实值
        if f.get("field") in user_ref_filter_fields and _has_self_ref_marker(
            f, user_ref_kw, self_names
        ):
            current_v = str(f.get("value", "") or "")
            current_pv = str(f.get("physical_value", "") or "")
            bad_values = {
                current_user.get("username"),
                current_user.get("name"),
                *(config.get("user_reference_keywords") or []),
                *(config.get("department_reference_keywords") or []),
                *(config.get("region_reference_keywords") or []),
            }
            bad_values.discard(None)
            bad_values = {str(x) for x in bad_values if x}
            ftype = field_to_type.get(f.get("field"), "owner")
            real_id = _resolve_user_value(current_user, ftype, config)
            if not real_id:
                continue

            # 兜底：判断当前 value 是否"看起来像真实的 user_id"
            # 真实 user_id 通常是纯数字/数字字符串，其他字符串都视为错误
            def _looks_like_real_id(val: str, real_id_val: str) -> bool:
                # 真实值匹配 → OK
                if val == real_id_val:
                    return True
                # 真实值是数字串时，只有数字串才算合法
                if real_id_val.isdigit():
                    return val.isdigit()
                return False

            needs_fix = False
            # value 检查
            is_bad_v = (
                current_v in bad_values
                or current_v == ""
                or current_v.startswith("${")
                or not _looks_like_real_id(current_v, real_id)
            )
            if is_bad_v:
                f["value"] = real_id
                needs_fix = True
            # physical_value 检查
            is_bad_pv = (
                current_pv in bad_values
                or current_pv == ""
                or current_pv.startswith("${")
                or not _looks_like_real_id(current_pv, real_id)
            )
            if is_bad_pv:
                f["physical_value"] = real_id
                needs_fix = True
            if needs_fix:
                print(
                    f"[DEBUG][user_ref] 纠正错误 filter 值: "
                    f"{f.get('field')} {current_v!r}/{current_pv!r} → {real_id!r}"
                )

    return injected


# 兜底字段名集合（模块级，供最后防线使用，不依赖 schema 元数据）
_FALLBACK_OWNER_FIELDS = {
    "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
    "agent_id", "created_by", "updated_by", "manager_id",
    "created_by_id", "updated_by_id",
}
_FALLBACK_DEPARTMENT_FIELDS = {"department_id", "dept_id", "team_id", "group_id"}
_FALLBACK_REGION_FIELDS = {"region", "area", "zone"}


def enforce_user_reference_values(
    containers: List[Dict[str, Any]],
    user_info_list: Any,
    config: Optional[Dict[str, Any]] = None,
    user_ref_fields: Optional[Dict[str, Dict[str, Any]]] = None,
    name_resolver: Optional[Any] = None,
) -> int:
    """
    最后防线：在 SQL 生成前强制纠正所有用户引用字段的 filter 值。

    与 inject_user_reference_filters 的区别：
    - 不依赖问题中的关键词（无论 LLM 是否识别出用户引用，只要字段是用户引用字段就检查）
    - 不依赖 schema 元数据是否解析成功（user_ref_fields 为空时启用字段名兜底集合）
    - 直接遍历多个 filter 容器（semantic_result.filters / query_state.filters /
      query_plan.filters / sql_query_plan.where_conditions）统一纠正

    name_resolver: 可选回调，签名为 (names: List[str]) -> Dict[str, str]，
    用于"李四的销售额"这类他人引用的人名 → user_id 解析（查 users 表）。

    返回纠正的 filter 数量。
    """
    if config is None:
        config = get_default_config()
    if not user_info_list:
        return 0
    try:
        current_user = user_info_list[0] if isinstance(user_info_list, list) else user_info_list
        if not isinstance(current_user, dict):
            return 0

        # 构建 field → type 映射：schema 配置优先，兜底字段名集合补充
        field_to_type: Dict[str, str] = {}
        if isinstance(user_ref_fields, dict):
            for ref in user_ref_fields.values():
                if isinstance(ref, dict) and ref.get("field"):
                    field_to_type[ref["field"]] = ref.get("type", "owner")
        for fname in _FALLBACK_OWNER_FIELDS:
            field_to_type.setdefault(fname, "owner")
        for fname in _FALLBACK_DEPARTMENT_FIELDS:
            field_to_type.setdefault(fname, "department")
        for fname in _FALLBACK_REGION_FIELDS:
            field_to_type.setdefault(fname, "region")

        user_reference_keywords = set(config.get("user_reference_keywords") or [])
        self_names = {
            str(current_user.get("username") or ""),
            str(current_user.get("name") or ""),
        }
        self_names.discard("")

        fixed = 0
        for container in containers:
            if not isinstance(container, dict):
                continue
            filters = container.get("filters")
            if not isinstance(filters, list):
                filters = container.get("where_conditions")
            if not isinstance(filters, list):
                continue
            for f in filters:
                if not isinstance(f, dict):
                    continue
                field = f.get("field")
                ftype = field_to_type.get(field)
                if not ftype:
                    continue
                # 只有带"自我引用"标记的 filter 才纠正，避免误改他人过滤
                if _has_self_ref_marker(f, user_reference_keywords, self_names):
                    real_id = _resolve_user_value(current_user, ftype, config)
                    if not real_id:
                        continue

                    def _is_bad(val: str) -> bool:
                        if not val or val.startswith("${"):
                            return True
                        if val == real_id:
                            return False
                        # 真实值是数字时，非数字字符串一律视为错误
                        if real_id.isdigit():
                            return not val.isdigit()
                        # 真实值非数字时，只放行完全匹配和已知引用词
                        return val in user_reference_keywords

                    changed = False
                    v = str(f.get("value", "") or "")
                    pv = str(f.get("physical_value", "") or "")
                    if _is_bad(v):
                        f["value"] = real_id
                        changed = True
                    if _is_bad(pv):
                        f["physical_value"] = real_id
                        changed = True
                    if changed:
                        f["match_type"] = f.get("match_type") or "USER_REFERENCE"
                        fixed += 1
                        print(
                            f"[DEBUG][user_ref] 最后防线纠正: "
                            f"{field} {v!r}/{pv!r} → {real_id!r}"
                        )
                elif (
                    ftype in ("owner", "creator", "approver", "assignee")
                    and name_resolver is not None
                ):
                    # 他人引用：value 是人名/用户名（非数字）时，查 users 表解析为 user_id
                    v = str(f.get("value", "") or "")
                    pv = str(f.get("physical_value", "") or "")
                    candidates = {x for x in (v, pv) if x and not x.isdigit() and not x.startswith("${")}
                    if not candidates:
                        continue
                    try:
                        name_map = name_resolver(list(candidates)) or {}
                    except Exception as e:
                        print(f"[DEBUG][user_ref] name_resolver error: {str(e)}")
                        continue
                    for key in candidates:
                        uid = name_map.get(key)
                        if uid:
                            if v == key:
                                f["value"] = uid
                            if pv == key:
                                f["physical_value"] = uid
                            f["physical_value_resolved"] = True
                            fixed += 1
                            print(f"[DEBUG][user_ref] 最后防线人名解析: {field} {key!r} → {uid!r}")
                            break
        return fixed
    except Exception as e:
        print(f"[DEBUG][user_ref] enforce_user_reference_values error: {str(e)}")
        return 0