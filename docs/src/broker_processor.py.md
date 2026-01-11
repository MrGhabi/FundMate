src/broker_processor.py
    功能描述: 核心券商报表处理器。负责 PDF/Excel 报表解析、价格获取、合并持仓、生成汇总；产出 ProcessedResult 列表供持久化或 TC 使用。

    def extract_occ_code_if_present(stock_code: str) -> str
        功能: 从混合描述中抽取 OCC 期权代码，提升匹配准确度。

    @dataclass ProcessedResult
        字段: broker_name/account_id/cash_data/positions/usd_total/statement_date/position_values。
        用途: 标准化每个券商的处理结果，便于后续定价、合并和持久化。

    class BrokerStatementProcessor
        __init__()
            功能: 初始化 LLMHandler、PDFProcessor、ExcelPositionParser、PriceFetcher。

        process_folder(broker_folder, date, broker=None, force=False, max_workers=10, skip_logging_setup=False)
            功能: 入口；校验日期→准备日志→获取汇率→并发处理 PDF→处理 Excel→合并结果→交叉定价→打印汇总→记录 probe。
            输入: 目标目录（档案或实时）、日期、可选券商过滤、并发/force。
            输出: (results, exchange_rates, date) 或失败返回 None。
            注意: 档案模式直接使用目录；汇率通过 exchange_handler；会在 probe 中标记 broker 进度与财务数据。

        _process_broker_pdfs(...), _process_excel_data(...), _merge_position_data(...)
            功能: 分别处理 PDF、Excel，并将两类结果按账户/券商合并。
            依赖: PDFProcessor、ExcelPositionParser、Position 匹配与合并。

        _optimize_cross_broker_pricing(merged_results, date, exchange_rates)
            功能: 收集跨券商唯一标的，调用 PriceFetcher 获取行情，回填最终价格/货币，计算 total_position_value_usd。

        _is_archive_mode(broker_folder)
            功能: 基于路径推断档案模式（用于 Excel parser 行为）。

    关键注意事项
        - 必须先获取当日汇率（exchange_handler），失败则终止。
        - 档案模式依赖文件命名日期；缺目标日会回退最近日期。
        - probe 集成：mark_broker_start/end、set_broker_financials，用于前端进度。
