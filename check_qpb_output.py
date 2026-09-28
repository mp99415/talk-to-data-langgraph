import csv
import re

def extract_output(cell):
    """从单元格提取 Output"""
    if not cell or 'Output：' not in cell:
        return ""
    parts = cell.split('Output：', 1)
    if len(parts) < 2:
        return ""
    return parts[1]

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv'

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    header = rows[0]
    node_indices = {}
    for i, col in enumerate(header):
        node_indices[col] = i

    last_year_row = rows[2]

    print("=" * 80)
    print("检查去年销售额的 query_plan_builder 输出")
    print("=" * 80)

    # query_plan_builder
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        output = extract_output(last_year_row[idx])
        print("\nquery_plan_builder output:")
        print(output[:3000] if output else "无输出")

        # 检查 time 信息
        if "'time':" in output:
            print("\n✓ 包含 time 信息")
            # 提取 time 部分
            time_match = re.search(r"'time':\s*(\{[^}]+\})", output)
            if time_match:
                print(f"   time 内容: {time_match.group(1)[:200]}")
        else:
            print("\n✗ 不包含 time 信息")

    # query_plan_formatter
    print("\n" + "=" * 80)
    print("检查 query_plan_formatter 输出")
    print("=" * 80)

    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        output = extract_output(last_year_row[idx])
        print("\nquery_plan_formatter output:")
        print(output[:2000] if output else "无输出")

        # 检查 where_conditions
        if "'where_conditions':" in output:
            print("\n✓ 包含 where_conditions")
            wc_match = re.search(r"'where_conditions':\s*(\[.*?\])", output, re.DOTALL)
            if wc_match:
                print(f"   where_conditions: {wc_match.group(1)[:300]}")
        else:
            print("\n✗ 不包含 where_conditions")

if __name__ == '__main__':
    main()
