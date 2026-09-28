"""
Talk to Data Enterprise - LangGraph Version
入口文件
"""

import csv
import os
import json
import time
from typing import Dict
from dotenv import load_dotenv

# 加载 .env 文件（从项目根目录）
load_dotenv()

# 确保在导入 LLM 客户端之前环境变量已加载
from .llm.client import reset_llm
reset_llm()  # 重置可能缓存的 LLM 实例

from .graph.graph import create_graph, run_graph


# 节点列表（按执行顺序）
NODES = [
    'start',
    'get_user_info',
    'get_user_roles',
    'get_rbac_permissions',
    'get_field_permissions',
    'get_row_policies',
    'raw_authorization_normalizer',
    'permission_resolver',
    'rewriter',
    'intent_analyzer',
    'general_answer',
    'merger',
    'query_validator',
    'query_operation_normalizer',
    'schema_builder',
    'get_physical_columns',
    'get_physical_foreign_keys',
    'get_business_metadata',
    'semantic_resolver',
    'semantic_resolution_guard',
    'semantic_resolution_router',
    'filter_value_resolver',
    'semantic_clarification_context_builder',
    'value_clarification_context_builder',
    'query_plan_builder',
    'query_plan_formatter',
    'get_current_date',
    'schema_test_override',
    'value_semantic_lookup',
    'value_semantic_resolver',
    'value_lookup_prep',
    'sql_generator',
    'sql_validator',
    'sql_ast_parser',
    'permission_engine',
    'authorized_sql',
    'sql_executor',
    'security_validator',
    'result_summarizer',
    'result_validator',
    'result_adapter',
    'result_normalizer',
    'clarification_generator',
    'clarification_builder',
    'clarification_answer_handler',
    'answer_validator',
    'save_query_state',
    'clear_pending',
    'final_answer',
    'error_answer',
    'unsafe_answer',
    'semantic_error_answer',
    'permission_error_answer'
]


def truncate(value, max_length=500):
    """截断过长的值"""
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + "..."
    if isinstance(value, (list, dict)):
        s = json.dumps(value, ensure_ascii=False, default=str)
        if len(s) > max_length:
            return s[:max_length] + "..."
        return s
    return value


def run_single_test(user_id: str, user_query: str, previous_query_state: dict = None, previous_answer: str = None) -> dict:
    """运行单个测试用例

    Args:
        user_id: 用户 ID
        user_query: 用户问题
        previous_query_state: 上一轮的 Query State（用于多轮对话）
        previous_answer: 上一轮的最终回答（用于解析"它"等指代）
    """
    result = run_graph(
        user_id=user_id,
        user_query=user_query,
        previous_query_state=previous_query_state,
        previous_answer=previous_answer
    )
    return result


def run_all_tests(input_file: str, output_file: str, run_pending_only: bool = False):
    """运行所有测试用例

    Args:
        input_file: 输入 CSV 文件
        output_file: 输出 CSV 文件
        run_pending_only: 是否只执行 run?=Y 的测试用例
    """
    # 读取测试用例
    test_cases = []
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            test_cases.append(row)

    print(f"读取到 {len(test_cases)} 个测试用例")

    # 获取原始 CSV 的列（除了基础列外的额外列）
    # 去重，避免表头中有重复列名
    if test_cases:
        base_columns = ['test_case', 'time', 'final_result', 'sql', 'run?']
        all_headers = list(test_cases[0].keys())
        seen = set()
        original_headers = []
        for h in all_headers:
            if h not in base_columns and h not in seen:
                original_headers.append(h)
                seen.add(h)
        print(f"原始 CSV 额外列: {original_headers}")
    else:
        original_headers = []

    # 统计需要执行的测试用例
    pending_tests = []
    for i, tc in enumerate(test_cases):
        run_status = tc.get('run?', '').upper()
        if run_pending_only:
            # 只执行 run?=Y 的
            if run_status == 'Y':
                pending_tests.append((i, tc))
        else:
            # 执行所有
            pending_tests.append((i, tc))

    print(f"需要执行的测试用例: {len(pending_tests)}/{len(test_cases)}")

    if not pending_tests:
        print("没有需要执行的测试用例")
        return

    # 运行测试用例
    results = []
    # 多轮对话上下文：按 user_id 隔离的上一轮 query_state 缓存
    # Key: user_id, Value: 上一次成功的 query_state
    # 多轮用例（如 "销售额是多少？"）会自动复用同一个 user 的上一轮 query_state
    last_query_state_cache: Dict[str, dict] = {}
    # 上一轮最终回答缓存（用于解析"它/那家公司"等指代）
    last_answer_cache: Dict[str, str] = {}

    for i, tc in enumerate(test_cases):
        test_case = tc.get('test_case', '')
        original_run_status = tc.get('run?', '').upper()

        # 初始化结果
        result = {'test_case': test_case}

        # 保留原始列的值
        for header in original_headers:
            result[header] = tc.get(header, '')

        # 检查是否需要执行
        need_execute = any(idx == i for idx, _ in pending_tests)

        if need_execute:
            # 执行测试
            print(f"\n[{len([x for x, _ in pending_tests if x <= i])}/{len(pending_tests)}] 执行: {test_case}")

            # 初始化列
            result['time'] = ''
            result['final_result'] = ''
            result['sql'] = ''
            result['run?'] = 'N'  # 预设，执行成功后再改为 Y

            # 初始化节点列
            for node in NODES:
                result[node] = ''

            start_time = time.time()
            try:
                # 从 CSV 中读取 user_id（列名可选），缺省 1004 (wangzong, 销售总监)
                # 权限测试用例需要不同 user（如 1001 张三 - 普通销售），应在 CSV 中指定
                csv_user_id = tc.get('user_id', '').strip() or '1004'

                # 多轮对话支持：从 CSV 中读取 previous_query_state
                # 优先级: CSV 列 previous_query_state > 缓存的上一轮 query_state
                prev_qs_from_csv = tc.get('previous_query_state', '').strip()
                if prev_qs_from_csv:
                    try:
                        prev_qs = json.loads(prev_qs_from_csv) if prev_qs_from_csv != '{}' else None
                    except json.JSONDecodeError:
                        prev_qs = None
                    prev_answer = ''  # CSV 显式提供 state 时无法配对答案，不传
                else:
                    # 自动从缓存中取（同一 user_id 的上一轮 query_state 和回答）
                    prev_qs = last_query_state_cache.get(csv_user_id)
                    prev_answer = last_answer_cache.get(csv_user_id, '')

                exec_result = run_single_test(csv_user_id, test_case, prev_qs, prev_answer)
                total_elapsed = time.time() - start_time

                # 多轮对话支持：保存本轮 query_state，供同一 user 的下一轮用例使用
                # 只要本轮产出了最终答案就缓存最终 query_state（含"仅实体无指标"的状态）。
                # 旧逻辑只在 metrics 非空时缓存，NEW_TOPIC 实体查询/澄清轮之后
                # 下一轮会读到更早的陈旧状态（回归 Row15-18 实体污染的根因）
                new_qs = exec_result.get('query_state')
                if isinstance(new_qs, dict) and exec_result.get('final_answer'):
                    last_query_state_cache[csv_user_id] = new_qs

                # 更新结果
                result['time'] = round(total_elapsed, 2)

                answer = exec_result.get('final_answer') or exec_result.get('summarized_result', '')
                result['final_result'] = answer
                result['sql'] = exec_result.get('sql', '')

                # 缓存本轮回答，供同一 user 的下一轮指代解析（"它今年的利润"）
                if answer:
                    last_answer_cache[csv_user_id] = answer

                # 获取节点追踪信息
                node_timings = exec_result.get('node_timings', {})
                node_inputs = exec_result.get('node_inputs', {})
                node_outputs = exec_result.get('node_outputs', {})

                # 记录每个节点的执行结果
                # 关键节点输出加大截断上限，便于排查（如 sub_query 配置、查询计划）
                VERBOSE_NODES = {'rewriter', 'semantic_resolver', 'query_plan_builder',
                                 'query_plan_formatter', 'sql_generator', 'sql_executor'}
                for node in NODES:
                    timing = node_timings.get(node)
                    input_data = node_inputs.get(node, '')
                    output_data = node_outputs.get(node, '')

                    max_len = 2000 if node in VERBOSE_NODES else 200
                    input_str = truncate(input_data, max_len) if input_data else ''
                    output_str = truncate(output_data, max_len) if output_data else ''

                    if timing is not None:
                        result[node] = f"Y｜{timing:.2f}s｜Input：{input_str}｜Output：{output_str}"
                    else:
                        result[node] = f"N｜0.00s｜Input：{input_str}｜Output：{output_str}"

                # 检查是否成功
                if answer:
                    result['run?'] = 'N'  # 执行成功，标记为 N（已完成）
                    print(f"  ✅ 成功 - {answer[:50]}..." if len(answer) > 50 else f"  ✅ 成功 - {answer}")
                else:
                    error = exec_result.get('error') or exec_result.get('status') or '未知错误'
                    print(f"  ❌ 失败 - {error[:100]}")
                    if exec_result.get('sql'):
                        print(f"     SQL: {exec_result.get('sql', '')[:100]}")
                    result['error_answer'] = f"N｜{total_elapsed:.2f}s｜Error：{error}"

            except Exception as e:
                total_elapsed = time.time() - start_time
                error_msg = str(e)[:200]
                print(f"  ❌ 异常: {error_msg}")
                result['time'] = round(total_elapsed, 2)
                result['run?'] = 'E'  # 异常，标记为 E
                result['error_answer'] = f"N｜{total_elapsed:.2f}s｜Exception：{error_msg}"
        else:
            # 不需要执行，保留原始值
            result['time'] = tc.get('time', '')
            result['final_result'] = tc.get('final_result', '')
            result['sql'] = tc.get('sql', '')
            result['run?'] = tc.get('run?', '')

            # 保留原有节点列
            for node in NODES:
                result[node] = tc.get(node, '')

        results.append(result)

    # 定义输出列顺序
    output_headers = ['test_case', 'run?', 'time', 'final_result', 'sql'] + original_headers + NODES

    # 写入结果
    try:
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=output_headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results)
        print(f"\n✅ 测试完成，结果已保存到 {output_file}")
    except Exception as e:
        print(f"\n❌ 写入CSV失败: {e}")
        backup_file = output_file + '.backup'
        with open(backup_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=output_headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results)
        print(f"   结果已保存到备选文件: {backup_file}")

    # 统计
    # run?=N 表示已完成（不管成功失败），run?=Y 表示待执行，run?=E 表示异常
    success_count = sum(1 for r in results if r.get('run?') == 'N' and r.get('final_result'))
    pending_count = sum(1 for r in results if r.get('run?') == 'Y')
    error_count = sum(1 for r in results if r.get('run?') == 'E')
    print(f"   已完成: {success_count}/{len(results)}")
    print(f"   待执行: {pending_count}/{len(results)}")
    print(f"   异常: {error_count}/{len(results)}")


def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="运行 talk-to-data 测试用例")
    parser.add_argument(
        "input_file",
        nargs="?",
        default=None,
        help="输入 CSV 文件路径（默认 test_cases.csv）",
    )
    parser.add_argument(
        "-o", "--output-file",
        default=None,
        help="输出 CSV 文件路径（默认覆盖输入文件）",
    )
    parser.add_argument(
        "-a", "--run-all",
        action="store_true",
        help="执行所有测试用例（默认只执行 run?=Y 的测试）",
    )
    args = parser.parse_args()

    default_file = os.path.join(os.path.dirname(__file__), '..', '..', 'test_cases.csv')
    test_file = args.input_file or default_file
    output_file = args.output_file or test_file

    if os.path.exists(test_file):
        if args.run_all:
            print("=" * 60)
            print("执行模式: 执行所有测试用例")
            print(f"输入文件: {test_file}")
            print(f"输出文件: {output_file}")
            print("提示: 不带 -a 只执行 run?=Y 的测试")
            print("=" * 60)
            run_all_tests(test_file, output_file, run_pending_only=False)
        else:
            # 默认模式：只执行 run?=Y 的测试用例（需要重跑的）
            print("=" * 60)
            print("执行模式: 执行 run?=Y 的测试用例（需要重跑的）")
            print(f"输入文件: {test_file}")
            print(f"输出文件: {output_file}")
            print("执行完成后会将 run? 改为 N（已完成）")
            print("提示: 使用 --run-all 或 -a 执行所有测试")
            print("=" * 60)
            run_all_tests(test_file, output_file, run_pending_only=True)
    else:
        # 单个测试模式
        result = run_graph(
            user_id = "1004",
            user_query="今年各销售区域的销售额是多少？",
            previous_query_state=None
        )

        print(f"Answer: {result['final_answer'] or result.get('summarized_result', '')}")
        print(f"SQL: {result['sql']}")
        print(f"Node Timings: {result.get('node_timings', {})}")


if __name__ == "__main__":
    main()
