import csv
import re

def extract_input_output(cell):
    """从单元格提取 Input 和 Output"""
    if not cell or cell == 'N｜0.00s｜Input：｜Output：':
        return "", ""

    match = re.search(r'[YN]｜[\d.]+s｜Input：(.*?)｜Output：(.*)', cell, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return "", ""

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases_updated.csv'

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    header = rows[0]
    node_indices = {}
    for i, col in enumerate(header):
        node_indices[col] = i

    last_year_row = rows[2]

    print("=" * 80)
    print("sql_generator 节点完整输入分析 - 去年销售额")
    print("=" * 80)

    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        cell = last_year_row[idx]
        input_data, output = extract_input_output(cell)

        print("\n【Input 完整内容】:")
        print(input_data)

        print("\n【Output】:")
        print(output)

        # 分析 Input 中的关键信息
        print("\n" + "=" * 80)
        print("关键信息提取")
        print("=" * 80)

        # 检查 semantic_result
        if 'semantic_result' in input_data:
            print("\n✓ Input 中包含 semantic_result")

        # 检查 query_state
        if 'query_state' in input_data:
            print("✓ Input 中包含 query_state")

        # 检查 sql_query_plan
        if 'sql_query_plan' in input_data:
            print("✓ Input 中包含 sql_query_plan")
        else:
            print("✗ Input 中不包含 sql_query_plan")

        # 检查 query_plan
        if 'query_plan' in input_data:
            print("✓ Input 中包含 query_plan")
        else:
            print("✗ Input 中不包含 query_plan")

    # 检查 query_plan_formatter 的输出
    print("\n" + "=" * 80)
    print("query_plan_formatter 输出检查")
    print("=" * 80)

    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        cell = last_year_row[idx]
        input_data, output = extract_input_output(cell)

        print("\n【query_plan_formatter Output】:")
        print(output[:1500] if len(output) > 1500 else output)

        # 检查 select_fields
        if "'field': 'amount'" in output:
            print("\n✓ Output 包含 field: 'amount'")
        elif "'field': ''" in output or "'field':" in output and "'amount'" not in output:
            print("\n✗ Output 不包含正确的 field 信息")

if __name__ == '__main__':
    main()
