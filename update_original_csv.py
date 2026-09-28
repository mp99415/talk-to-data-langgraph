import csv
import re
from pathlib import Path

def parse_time_from_cell(cell):
    """从单元格中提取时间（秒）"""
    if not cell or cell == 'N｜0.00s｜Input：｜Output：':
        return 0.0
    # 匹配 Y｜0.00s 或 N｜0.00s 格式
    match = re.search(r'[YN]｜([\d.]+)s', cell)
    if match:
        return float(match.group(1))
    return 0.0

def extract_final_answer(cell):
    """从 final_answer 列提取最终回答"""
    if not cell or cell == 'N｜0.00s｜Input：｜Output：':
        return ''
    # 提取 Output：后面的内容
    match = re.search(r'Output：(\{[^}]*final_answer[^}]*\})', cell)
    if match:
        output = match.group(1)
        # 提取 final_answer 的值
        fa_match = re.search(r"'final_answer':\s*'([^']*)'", output)
        if fa_match:
            return fa_match.group(1)
    return ''

def process_csv():
    input_file = Path('/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv')

    # 读取原文件
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 获取标题行
    header = rows[0]

    # 找到 final_answer 列的索引
    final_answer_idx = None
    for i, col in enumerate(header):
        if col == 'final_answer':
            final_answer_idx = i
            break

    if final_answer_idx is None:
        print("未找到 final_answer 列")
        return

    # 处理每一行数据
    new_rows = []
    # 在 test_case 后插入 time 和 final_result
    new_rows.append([header[0], 'time', 'final_result'] + header[1:])

    for row in rows[1:]:
        if not row or not row[0].strip():
            continue

        # 计算总执行时间
        total_time = 0.0
        for cell in row:
            total_time += parse_time_from_cell(cell)

        # 提取 final_answer
        final_answer_cell = row[final_answer_idx] if final_answer_idx < len(row) else ''
        final_result = extract_final_answer(final_answer_cell)

        # 在 test_case 后插入 time 和 final_result
        new_row = [row[0], round(total_time, 2), final_result] + row[1:]
        new_rows.append(new_row)

    # 直接覆盖原文件
    with open(input_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(new_rows)

    print(f"处理完成！已更新原文件 {input_file}")
    print(f"- 总行数: {len(new_rows) - 1} (不含标题)")

    # 显示结果
    print("\n结果预览:")
    for i, row in enumerate(new_rows[:4]):
        if i == 0:
            print(f"  标题行: test_case, time, final_result, ...")
        else:
            print(f"  行 {i}: test_case={row[0][:30]}...")
            print(f"         time={row[1]}s")
            print(f"         final_result={row[2][:60]}...")

if __name__ == '__main__':
    process_csv()
