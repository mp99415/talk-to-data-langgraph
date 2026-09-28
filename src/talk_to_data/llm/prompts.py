"""
Prompt 模板 - 统一入口
"""

from .prompts.rewriter_prompt import CONTEXT_QUESTION_REWRITER_PROMPT, QUERY_STATE_SCHEMA, get_rewriter_prompt
from .prompts.intent_prompt import INTENT_ANALYZER_PROMPT
from .prompts.semantic_prompt import get_semantic_prompt
from .prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT, get_sql_generator_prompt
from .prompts.summarizer_prompt import RESULT_SUMMARIZER_PROMPT
from .prompts.general_answer_prompt import GENERAL_ANSWER_PROMPT
from .prompts.clarification_prompt import CLARIFICATION_GENERATOR_PROMPT

__all__ = [
    "CONTEXT_QUESTION_REWRITER_PROMPT",
    "QUERY_STATE_SCHEMA",
    "INTENT_ANALYZER_PROMPT",
    "get_semantic_prompt",
    "SQL_GENERATOR_PROMPT",
    "RESULT_SUMMARIZER_PROMPT",
    "GENERAL_ANSWER_PROMPT",
    "CLARIFICATION_GENERATOR_PROMPT",
]
