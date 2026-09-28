import csv
import json
import re

def extract_full_output(cell):
    """提取完整的 Output 内容"""
    if not cell or cell == 'N｜0.00s｜Input：｜Output：':
        return {}

    # 查找完整的 JSON 对象
    match = re.search(r'Output：(\{.*)', cell, re.DOTALL)
    if not match:
        return {}

    output_text = match.group(1)

    # 尝试找到完整的 JSON（匹配花括号）
    depth = 0
    end_pos = 0
    for i, char in enumerate(output_text):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break

    json_text = output_text[:end_pos]

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        # 尝试将单引号转换为双引号
        try:
            # 替换单引号为双引号（但保留内部引号）
            fixed = re.sub(r"'([^']*)'", r'"\1"', json_text)
            return json.loads(fixed)
        except:
            return {"raw": json_text}

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases_updated.csv'

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 找到去年销售额的那一行（第3行，索引2）
    last_year_row = rows[2]  # 第3行

    print("=" * 80)
    print("分析: 去年销售额是多少？")
    print("=" * 80)

    # 找到各节点的列索引
    header = rows[0]
    node_indices = {}
    for i, col in enumerate(header):
        node_indices[col] = i

    # 1. semantic_resolver 输出
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']
        if idx < len(last_year_row):
            data = extract_full_output(last_year_row[idx])
            if data:
                semantic_result = data.get('semantic_result', {})
                metrics = semantic_result.get('metrics', [])
                print("\n1. semantic_resolver 输出:")
                print(f"   metrics 数量: {len(metrics)}")
                if metrics:
                    for m in metrics:
                        print(f"   - concept: {m.get('concept')}, field: {m.get('field')}, table: {m.get('table')}")

    # 2. query_plan_builder 输出
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        if idx < len(last_year_row):
            data = extract_full_output(last_year_row[idx])
            if data:
                query_plan = data.get('query_plan', {})
                print("\n2. query_plan_builder 输出:")
                print(f"   query_plan 状态: {query_plan.get('status')}")
                metrics = query_plan.get('metrics', [])
                print(f"   metrics 数量: {len(metrics)}")
                if metrics:
                    for m in metrics:
                        print(f"   - field: '{m.get('field')}', table: '{m.get('table')}', aggregation: '{m.get('aggregation')}'")
                time_obj = query_plan.get('time', {})
                print(f"   time: {time_obj}")

    # 3. query_plan_formatter 输出
    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        if idx < len(last_year_row):
            data = extract_full_output(last_year_row[idx])
            if data:
                sql_query_plan = data.get('sql_query_plan', {})
                select_fields = sql_query_plan.get('select_fields', [])
                print("\n3. query_plan_formatter 输出:")
                print(f"   select_fields 数量: {len(select_fields)}")
                for sf in select_fields:
                    print(f"   - field: '{sf.get('field')}', table: '{sf.get('table')}', aggregation: '{sf.get('aggregation')}'")

    # 4. sql_generator 输出
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        if idx < len(last_year_row):
            data = extract_full_output(last_year_row[idx])
            if data:
                print("\n4. sql_generator 输出:")
                print(f"   生成的 SQL: {data.get('sql', 'N/A')}")

    # 对比今年销售额
    print("\n" + "=" * 80)
    print("对比: 今年销售额是多少？")
    print("=" * 80)

    this_year_row = rows[1]  # 第2行

    # 1. semantic_resolver 输出
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']
        if idx < len(this_year_row):
            data = extract_full_output(this_year_row[idx])
            if data:
                semantic_result = data.get('semantic_result', {})
                metrics = semantic_result.get('metrics', [])
                print("\n1. semantic_resolver 输出:")
                print(f"   metrics 数量: {len(metrics)}")
                if metrics:
                    for m in metrics:
                        print(f"   - concept: {m.get('concept')}, field: {m.get('field')}, table: {m.get('table')}")

    # 2. query_plan_builder 输出
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        if idx < len(this_year_row):
            data = extract_full_output(this_year_row[idx])
            if data:
                query_plan = data.get('query_plan', {})
                print("\n2. query_plan_builder 输出:")
                print(f"   query_plan 状态: {query_plan.get('status')}")
                metrics = query_plan.get('metrics', [])
                print(f"   metrics 数量: {len(metrics)}")
                if metrics:
                    for m in metrics:
                        print(f"   - field: '{m.get('field')}', table: '{m.get('table')}', aggregation: '{m.get('aggregation')}'")
                time_obj = query_plan.get('time', {})
                print(f"   time: {time_obj}")

    # 3. query_plan_formatter 输出
    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        if idx < len(this_year_row):
            data = extract_full_output(this_year_row[idx])
            if data:
                sql_query_plan = data.get('sql_query_plan', {})
                select_fields = sql_query_plan.get('select_fields', [])
                print("\n3. query_plan_formatter 输出:")
                print(f"   select_fields 数量: {len(select_fields)}")
                for sf in select_fields:
                    print(f"   - field: '{sf.get('field')}', table: '{sf.get('table')}', aggregation: '{sf.get('aggregation')}'")

    # 4. sql_generator 输出
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        if idx < len(this_year_row):
            data = extract_full_output(this_year_row[idx])
            if data:
                print("\n4. sql_generator 输出:")
                print(f"   生成的 SQL: {data.get('sql', 'N/A')}")

if __name__ == '__main__':
    main()
