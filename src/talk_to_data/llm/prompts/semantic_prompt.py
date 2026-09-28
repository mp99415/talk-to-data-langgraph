"""
SEMANTIC / METRIC RESOLVER Prompt
组合通用规则和业务规则
"""

from .semantic_universal_prompt import UNIVERSAL_SEMANTIC_RULES
from .semantic_business_rules import BUSINESS_RULES

SEMANTIC_RESOLVER_PROMPT_TEMPLATE = """你是企业级业务语义 → 物理数据库 Schema 解析器。

你的唯一职责是：
将当前用户的业务问题解析成结构化业务语义，并在提供的 Schema Context / Business Semantic Mapping 中寻找有依据的物理表、字段、业务值和关系映射。

你不得生成 SQL。
你不得生成 SQL 片段。
你不得生成不存在的字段或表。

{universal_rules}

{business_rules}

{schema_context}

【Query State】
{query_state}

【Rewritten Question】
{rewritten_question}

{user_context}
"""

def get_semantic_prompt(
    query_state: str,
    rewritten_question: str,
    schema_context: str,
    current_date: str = None,
    user_context: str = ""
) -> str:
    """组合通用规则和业务规则生成 Prompt"""
    from datetime import date, timedelta

    if current_date is None:
        current_date = date.today().strftime("%Y-%m-%d")

    today = date.today()
    current_year = today.year
    next_year = current_year + 1
    prev_year = current_year - 1

    # 计算上个月
    first_day_of_month = date(current_year, today.month, 1)
    last_month_end = first_day_of_month - timedelta(days=1)
    prev_month_start = date(last_month_end.year, last_month_end.month, 1).strftime("%Y-%m-%d")
    current_month_start = first_day_of_month.strftime("%Y-%m-%d")

    # 计算最近30天
    last_30_days_start = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # 填充 universal_rules 和 business_rules 中的时间占位符
    universal_rules_filled = UNIVERSAL_SEMANTIC_RULES
    business_rules_filled = BUSINESS_RULES
    replacements = {
        '{current_date}': current_date,
        '{current_year}': str(current_year),
        '{next_year}': str(next_year),
        '{prev_year}': str(prev_year),
        '{prev_month_start}': prev_month_start,
        '{current_month_start}': current_month_start,
        '{last_30_days_start}': last_30_days_start,
        '{tomorrow}': tomorrow,
        '{yesterday}': yesterday,
    }
    for placeholder, value in replacements.items():
        universal_rules_filled = universal_rules_filled.replace(placeholder, value)
        business_rules_filled = business_rules_filled.replace(placeholder, value)

    return SEMANTIC_RESOLVER_PROMPT_TEMPLATE.format(
        universal_rules=universal_rules_filled,
        business_rules=business_rules_filled,
        schema_context=schema_context,
        query_state=query_state,
        rewritten_question=rewritten_question,
        user_context=user_context or "",
    )
