import csv
import re
from collections import defaultdict

def extract_node_timings(cell):
    """从单元格提取节点耗时"""
    timings = {}
    if not cell or 'Y｜' not in cell:
        return timings
    
    # 匹配格式: Y｜0.21s｜...
    pattern = r'Y｜(\d+\.?\d*)s｜'
    matches = re.findall(pattern, cell)
    
    # 找到对应的节点名称
    lines = cell.split('｜')
    for i, part in enumerate(lines):
        if part.endswith('s') and i > 0:
            # 找到节点名（在前面的部分找）
            for j in range(i-1, -1, -1):
                prev = lines[j]
                # 节点名格式
                if prev and not prev.startswith('Input：') and not prev.startswith('Output：'):
                    timing_match = re.search(r'(\d+\.?\d*)s', prev)
                    if timing_match:
                        node_name = prev.replace(timing_match.group(0), '').strip()
                        if node_name:
                            timings[node_name] = float(timing_match.group(1))
                    break
    return timings

def parse_timing(cell):
    """从单元格解析单个时间"""
    if not cell or 'Y｜' not in cell:
        return 0.0
    match = re.search(r'Y｜(\d+\.?\d*)s', cell)
    if match:
        return float(match.group(1))
    return 0.0

def main():
    input_file = '/Users/frankh/Projects/talk-to-data-langgraph/test_cases.csv'
    
    # 读取 CSV
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames
    
    # 节点列表
    nodes = [
        'start', 'get_user_info', 'get_user_roles', 'get_rbac_permissions',
        'get_field_permissions', 'get_row_policies', 'raw_authorization_normalizer',
        'permission_resolver', 'rewriter', 'intent_analyzer', 'general_answer',
        'merger', 'query_validator', 'query_operation_normalizer', 'schema_builder',
        'get_physical_columns', 'get_physical_foreign_keys', 'get_business_metadata',
        'semantic_resolver', 'semantic_resolution_guard', 'semantic_resolution_router',
        'semantic_clarification_context_builder', 'value_clarification_context_builder',
        'query_plan_builder', 'query_plan_formatter', 'get_current_date',
        'schema_test_override', 'value_semantic_lookup', 'value_semantic_resolver',
        'value_lookup_prep', 'sql_generator', 'sql_validator', 'sql_ast_parser',
        'permission_engine', 'authorized_sql', 'sql_executor', 'security_validator',
        'result_summarizer', 'result_validator', 'result_adapter', 'result_normalizer',
        'clarification_generator', 'clarification_builder', 'clarification_answer_handler',
        'answer_validator', 'save_query_state', 'clear_pending', 'final_answer',
        'error_answer', 'unsafe_answer', 'semantic_error_answer', 'permission_error_answer'
    ]
    
    # 统计每个节点的耗时
    node_total_time = defaultdict(float)
    node_count = defaultdict(int)
    node_times = defaultdict(list)
    
    for row in rows:
        test_case = row.get('test_case', 'Unknown')
        for node in nodes:
            if node in headers:
                cell = row.get(node, '')
                timing = parse_timing(cell)
                if timing > 0:
                    node_total_time[node] += timing
                    node_count[node] += 1
                    node_times[node].append((test_case, timing))
    
    # 计算平均耗时
    node_avg_time = {}
    for node in node_total_time:
        if node_count[node] > 0:
            node_avg_time[node] = node_total_time[node] / node_count[node]
    
    # 排序
    sorted_nodes = sorted(node_avg_time.items(), key=lambda x: x[1], reverse=True)
    
    print("=" * 80)
    print("节点耗时分析报告")
    print("=" * 80)
    print(f"\n分析测试用例数: {len(rows)}")
    print(f"涉及节点数: {len(node_total_time)}")
    print()
    
    # Top 3 最耗时节点
    print("🔥 TOP 3 最耗时节点（按平均耗时）:")
    print("-" * 80)
    for i, (node, avg_time) in enumerate(sorted_nodes[:3], 1):
        total = node_total_time[node]
        count = node_count[node]
        print(f"\n  {i}. {node}")
        print(f"     平均耗时: {avg_time:.2f}s")
        print(f"     总耗时:   {total:.2f}s")
        print(f"     调用次数: {count}")
        print(f"     最大耗时: {max([t for _, t in node_times[node]]):.2f}s")
    
    # Top 10 所有节点
    print("\n\n📊 TOP 10 所有节点（按平均耗时）:")
    print("-" * 80)
    print(f"{'排名':<4} {'节点名称':<40} {'平均(s)':<10} {'总耗时(s)':<12} {'次数':<6}")
    print("-" * 80)
    for i, (node, avg_time) in enumerate(sorted_nodes[:10], 1):
        total = node_total_time[node]
        count = node_count[node]
        print(f"{i:<4} {node:<40} {avg_time:<10.2f} {total:<12.2f} {count:<6}")
    
    # 各测试用例耗时
    print("\n\n📋 各测试用例耗时:")
    print("-" * 80)
    for row in rows:
        test_case = row.get('test_case', '')[:30]
        total_time = row.get('time', 'N/A')
        print(f"  • {test_case:<30} | 总耗时: {total_time}s")

if __name__ == '__main__':
    main()
