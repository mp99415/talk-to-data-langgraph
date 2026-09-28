"""
Prompt 模板
"""

from .rewriter_prompt import CONTEXT_QUESTION_REWRITER_PROMPT, QUERY_STATE_SCHEMA, get_rewriter_prompt
from .intent_prompt import INTENT_ANALYZER_PROMPT
from .semantic_prompt import get_semantic_prompt
from .sql_generator_prompt import SQL_GENERATOR_PROMPT, get_sql_generator_prompt
from .summarizer_prompt import RESULT_SUMMARIZER_PROMPT
from .general_answer_prompt import GENERAL_ANSWER_PROMPT
from .clarification_prompt import CLARIFICATION_GENERATOR_PROMPT

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
