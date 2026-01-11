src/prompt_templates.py
    功能描述: 存放 LLM 提示模板（解析 PDF/提取字段），被 LLMHandler 与 PDFProcessor 引用。

    模板内容
        - 券商报表解析模板：指导模型提取现金、持仓、账户号等结构化字段。
        - 其他辅助提示：错误重试或元数据探测可引用。

    注意: 变更模板需评估对解析结果的字段名/结构影响，保持与 pdf_processor 预期字段一致。
