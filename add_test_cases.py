import csv
import os

def add_test_cases():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv'

    # 新的测试用例列表
    new_test_cases = [
        "去年销售额是多少？",
        "前年销售额是多少？",
        "2025年的销售额是多少？",
        "2025年3月销售额是多少？",
        "2025年第一季度销售额是多少？",
        "上个月销售额是多少？",
        "上个季度销售额是多少？",
        "最近30天销售额是多少？",
        "昨天销售额是多少？",
        "今年到目前为止销售额是多少？"
    ]

    # 读取现有 CSV
    if os.path.exists(input_file):
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
            headers = reader.fieldnames

        # 获取现有的 test_case 列表
        existing_cases = [row.get('test_case', '') for row in existing_rows]
        print(f"现有 {len(existing_rows)} 条测试用例")
    else:
        existing_rows = []
        headers = ['test_case', 'run?', 'time', 'final_result', 'sql']
        existing_cases = []
        print("CSV 文件不存在，将创建新文件")

    # 添加新的测试用例
    added_count = 0
    for tc in new_test_cases:
        if tc not in existing_cases:
            new_row = {
                'test_case': tc,
                'run?': 'Y',  # 默认值设为 Y
                'time': '',
                'final_result': '',
                'sql': ''
            }
            existing_rows.append(new_row)
            added_count += 1
            print(f"  + 添加: {tc}")
        else:
            # 如果已存在，更新 run? 为 Y
            for row in existing_rows:
                if row.get('test_case') == tc:
                    row['run?'] = 'Y'
                    print(f"  ↻ 更新: {tc} -> run?=Y")

    # 写入 CSV
    with open(input_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(existing_rows)

    print(f"\n✅ 完成！新增 {added_count} 条测试用例，总计 {len(existing_rows)} 条")
    print(f"   文件: {input_file}")

    # 预览
    print("\n预览（所有行）:")
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            status = row.get('run?', 'N')
            print(f"  {i+1}. [{status}] {row.get('test_case', '')[:40]}...")

if __name__ == '__main__':
    add_test_cases()
