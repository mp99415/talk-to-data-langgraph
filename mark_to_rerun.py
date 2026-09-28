import csv

def mark_last_year_to_rerun():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv'

    # 读取 CSV
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    # 将所有 run? 改为 Y
    for row in rows:
        row['run?'] = 'Y'

    # 写回 CSV
    with open(input_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ 已将所有 run? 改为 Y")
    print(f"   文件: {input_file}")
    print(f"   总行数: {len(rows)}")

    # 显示结果
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        print(f"\n预览:")
        for i, row in enumerate(reader):
            print(f"  {row.get('test_case', '')[:30]}... run?={row.get('run?', 'N')}")

if __name__ == '__main__':
    mark_last_year_to_rerun()
