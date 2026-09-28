import csv
import re

def extract_output(cell):
    """从单元格提取 Output"""
    if not cell or 'Output：' not in cell:
        return ""

    parts = cell.split('Output：', 1)
    if len(parts) < 2:
        return ""

    output = parts[1]
    return output

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases_updated.csv'

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 找到各节点的列索引
    header = rows[0]
    node_indices = {}
    for i, col in enumerate(header):
        node_indices[col] = i

    # 分析去年销售额（第3行）
    last_year_row = rows[2]

    print("=" * 80)
    print("深入分析: 去年销售额是多少？")
    print("=" * 80)

    # 1. intent_analyzer
    if 'intent_analyzer' in node_indices:
        idx = node_indices['intent_analyzer']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n1. intent_analyzer output:")
        print(output[:800] if output else "无输出")

    # 2. semantic_resolver - 完整输出
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n2. semantic_resolver output (完整):")
        print(output if output else "无输出")

    # 3. query_plan_builder - 完整输出
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n3. query_plan_builder output (完整):")
        print(output if output else "无输出")

    # 4. query_plan_formatter - 完整输出
    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n4. query_plan_formatter output (完整):")
        print(output if output else "无输出")

    # 5. sql_generator - 完整输出
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n5. sql_generator output (完整):")
        print(output if output else "无输出")

    print("\n" + "=" * 80)
    print("对比分析: 今年销售额 vs 去年销售额")
    print("=" * 80)

    this_year_row = rows[1]

    # 今年 query_plan_builder
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        cell = this_year_row[idx]
        output = extract_output(cell)
        print("\n今年 query_plan_builder output:")
        print(output[:800] if output else "无输出")

    # 去年 query_plan_builder
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print("\n去年 query_plan_builder output:")
        print(output[:800] if output else "无输出")

if __name__ == '__main__':
    main()
