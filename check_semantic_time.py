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
    print("检查去年销售额的 semantic_resolver 输出")
    print("=" * 80)

    # semantic_resolver
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']
        output = extract_output(last_year_row[idx])
        print("\nsemantic_resolver output:")
        print(output[:2000] if output else "无输出")

        # 检查是否包含 time
        if "'time':" in output:
            print("\n✓ 包含 time 信息")
        else:
            print("\n✗ 不包含 time 信息")

    # merger - query_state
    if 'merger' in node_indices:
        idx = node_indices['merger']
        output = extract_output(last_year_row[idx])
        print("\n\nmerger output (包含 query_state):")
        print(output[:2000] if output else "无输出")

        # 检查 time
        if "'time':" in output or '"time":' in output:
            print("\n✓ 包含 time 信息")
        else:
            print("\n✗ 不包含 time 信息")

if __name__ == '__main__':
    main()
