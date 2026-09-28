import csv
import re

def extract_input_output(cell):
    """从单元格提取 Input 和 Output"""
    if not cell or cell == 'N｜0.00s｜Input：｜Output：':
        return "", ""

    # 匹配 Y｜0.00s｜Input：...｜Output： 格式
    match = re.search(r'[YN]｜[\d.]+s｜Input：(.+?)｜Output：(.*)', cell, re.DOTALL)
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

    print("=" * 80)
    print("分析 sql_generator 节点的输入")
    print("=" * 80)

    # 今年
    this_year_row = rows[1]
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        cell = this_year_row[idx]
        input_data, output = extract_input_output(cell)
        print("\n【今年销售额】sql_generator Input:")
        print(input_data[:1500] if input_data else "无输入")

    # 去年
    last_year_row = rows[2]
    if 'sql_generator' in node_indices:
        idx = node_indices['sql_generator']
        cell = last_year_row[idx]
        input_data, output = extract_input_output(cell)
        print("\n【去年销售额】sql_generator Input:")
        print(input_data[:1500] if input_data else "无输入")

    print("\n" + "=" * 80)
    print("对比关键差异")
    print("=" * 80)

    # 检查 semantic_result 中的 metrics
    if 'semantic_resolver' in node_indices:
        idx = node_indices['semantic_resolver']

        this_year_cell = this_year_row[idx]
        last_year_cell = last_year_row[idx]

        this_input, this_output = extract_input_output(this_year_cell)
        last_input, last_output = extract_input_output(last_year_cell)

        print("\n今年 semantic_result output 中的 metrics:")
        # 提取 metrics 部分
        metrics_match = re.search(r"'metrics':\s*\[(.*?)\]", this_output, re.DOTALL)
        if metrics_match:
            print(metrics_match.group(0)[:500])

        print("\n去年 semantic_result output 中的 metrics:")
        metrics_match = re.search(r"'metrics':\s*\[(.*?)\]", last_output, re.DOTALL)
        if metrics_match:
            print(metrics_match.group(0)[:500])

    # 检查 query_state 中的 metrics
    if 'merger' in node_indices:
        idx = node_indices['merger']

        this_year_cell = this_year_row[idx]
        last_year_cell = last_year_row[idx]

        this_input, this_output = extract_input_output(this_year_cell)
        last_input, last_output = extract_input_output(last_year_cell)

        print("\n今年 merger output 中的 query_state.metrics:")
        metrics_match = re.search(r"'metrics':\s*\[(.*?)\]", this_output, re.DOTALL)
        if metrics_match:
            print(metrics_match.group(0)[:500])

        print("\n去年 merger output 中的 query_state.metrics:")
        metrics_match = re.search(r"'metrics':\s*\[(.*?)\]", last_output, re.DOTALL)
        if metrics_match:
            print(metrics_match.group(0)[:500])

if __name__ == '__main__':
    main()
