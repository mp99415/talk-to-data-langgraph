# Talk to Data Enterprise - LangGraph Version

基于 Dify DSL 改造的 LangGraph 架构实现。

## 安装

```bash
cd talk-to-data-langgraph
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

## 运行

```bash
python -m talk_to_data.main
```

## 项目结构

```
talk-to-data-langgraph/
├── pyproject.toml
├── .env.example
├── README.md
└── src/
    └── talk_to_data/
        ├── __init__.py
        ├── main.py
        ├── graph/
        │   ├── state.py
        │   ├── graph.py
        │   ├── nodes/
        │   │   ├── rewriter.py
        │   │   ├── merger.py
        │   │   ├── validator.py
        │   │   ├── schema.py
        │   │   ├── semantic.py
        │   │   ├── sql_gen.py
        │   │   ├── summarizer.py
        │   │   └── clarification.py
        │   └── edges/
        │       └── routers.py
        ├── llm/
        │   ├── client.py
        │   └── prompts.py
        └── tools/
            ├── database.py
            ├── metadata.py
            └── permissions.py
```
