import csv

def add_run_column():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv'

    # 读取 CSV
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    # 添加 run? 列（如果在 test_case 后）
    if 'run?' not in headers:
        # 找到 test_case 的位置
        new_headers = []
        for h in headers:
            new_headers.append(h)
            if h == 'test_case' and 'run?' not in new_headers:
                new_headers.append('run?')

        # 添加 run? 列，默认为 N
        for row in rows:
            row['run?'] = 'N'

        # 写回 CSV
        with open(input_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✅ 已添加 run? 列，默认为 N")
        print(f"   文件: {input_file}")
        print(f"   总行数: {len(rows)}")
    else:
        print(f"run? 列已存在")

    # 显示结果
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        print(f"\n前3行预览:")
        for i, row in enumerate(reader):
            if i < 3:
                print(f"  {row.get('test_case', '')[:30]}... run?={row.get('run?', 'N')}")

if __name__ == '__main__':
    add_run_column()
