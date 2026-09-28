import csv
import re

def parse_csv_line(line):
    """手动解析 CSV 行"""
    result = []
    current = []
    in_quotes = False

    for char in line:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char == ',' and not in_quotes:
            result.append(''.join(current))
            current = []
        else:
            current.append(char)

    result.append(''.join(current))
    return result

def extract_output(cell):
    """从单元格提取 Output"""
    if not cell or 'Output：' not in cell:
        return ""

    parts = cell.split('Output：')
    if len(parts) < 2:
        return ""

    output = parts[1]

    # 如果有引号包裹，去掉引号
    if output.startswith('"') and output.endswith('"'):
        output = output[1:-1]

    return output

def find_metrics_from_json(json_str):
    """从 JSON 字符串中提取 metrics"""
    # 尝试找到 metrics 部分
    metrics_match = re.search(r"'metrics':\s*\[(.*?)\]", json_str, re.DOTALL)
    if metrics_match:
        return metrics_match.group(0)
    return ""

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases_updated.csv'

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    print(f"总行数: {len(rows)}")
    print(f"列数: {len(rows[0])}")
    print(f"\n列名:\n{rows[0]}")

    # 找到各节点的列索引
    header = rows[0]
    node_indices = {}
    for i, col in enumerate(header):
        node_indices[col] = i

    print(f"\n节点索引:")
    for key in ['semantic_resolver', 'query_plan_builder', 'query_plan_formatter', 'sql_generator']:
        if key in node_indices:
            print(f"  {key}: 列 {node_indices[key]}")

    # 分析去年销售额（第3行）
    last_year_row = rows[2]

    print("\n" + "=" * 80)
    print("分析: 去年销售额是多少？")
    print("=" * 80)

    # 1. semantic_resolver
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print(f"\n1. semantic_resolver output (前500字符):")
        print(output[:500] if output else "无输出")

        if 'orders.amount' in output or 'amount' in output:
            print("   -> 包含 amount 字段")
        else:
            print("   -> 不包含 amount 字段")

    # 2. query_plan_builder
    if 'query_plan_builder' in node_indices:
        idx = node_indices['query_plan_builder']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print(f"\n2. query_plan_builder output (前500字符):")
        print(output[:500] if output else "无输出")

        if "'field': 'amount'" in output:
            print("   -> 包含 field: 'amount'")
        else:
            print("   -> 不包含 field: 'amount'")

    # 3. query_plan_formatter
    if 'query_plan_formatter' in node_indices:
        idx = node_indices['query_plan_formatter']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print(f"\n3. query_plan_formatter output (前500字符):")
        print(output[:500] if output else "无输出")

    # 4. sql_generator
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        cell = last_year_row[idx]
        output = extract_output(cell)
        print(f"\n4. sql_generator output:")
        print(output if output else "无输出")

if __name__ == '__main__':
    main()
