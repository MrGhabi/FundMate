src/pdf_processor.py
    功能描述: 处理券商 PDF 报表（无需图像转化），按券商筛页、调用 LLM 提取账户/现金/持仓，封装为 Position/Cash 数据。

    extract_account_id(pdf_path, broker_name) -> str
        功能: 根据券商格式从文件名或内容抽取账户号。

    filter_page_indices(total_pages, broker_name) -> List[int]
        功能: 按券商规则过滤需要解析的页码，减少 LLM 成本。

    class PDFProcessor
        关键方法: process_pdf(...) 读取、预处理、调用 LLMHandler 获取结构化结果；缓存 processed PDF；为后续 BrokerStatementProcessor 提供 positions/cash。
        注意: 依赖 LLM 模板和 broker-specific 规则；遇到解密/解析异常会抛错并在上层重试。
