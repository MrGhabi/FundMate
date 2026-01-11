src/llm_handler.py
    功能描述: LLM 客户端封装。负责向指定模型（Gemini 等）发送 PDF/文本解析请求，返回结构化 JSON；内置重试与 rate limit。

    LLMHandler.__init__()
        功能: 读取 settings 中的模型与 API 配置，初始化客户端。

    send_request(content, prompt=None, temperature=0)
        功能: 通用请求接口，带重试、日志、错误处理，返回模型输出字符串/JSON。

    parse_pdf_with_prompt(pdf_path, prompt)
        功能: 读取 PDF 内容后带模板发送给模型，返回解析结果（被 pdf_processor 使用）。

    注意事项
        - 失败会抛异常，上层需捕获并决定重试次数。
        - 依赖 settings 中的 API key/endpoint，需在运行环境配置。
