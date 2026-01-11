src/data_persistence.py
    功能描述: 结果持久化与汇总输出。负责现金/持仓 parquet、CSV、metadata 的保存，并处理货币换算、货币基金归类。

    def save_processing_results(results, date, exchange_rates, probe_data=None, skip_logging_setup=False)
        功能: 入口；聚合现金/持仓→调用下游保存函数→输出 summary/metadata。
        输入: ProcessedResult 列表、日期、汇率、可选 probe 数据。
        注意: 会在保存前将货币基金归为现金（is_money_market_fund）。

    _reclassify_money_market_funds(results)
        功能: 将识别的货币基金从持仓剔除并计入现金，避免重复计价。

    _calculate_totals(results, exchange_rates)
        功能: 汇总各币种现金与持仓价值，返回总现金/总持仓/总资产。
        依赖: exchange_rates USD/HKD/CNY；positions 的 final_price/multiplier。

    _save_cash_summary(...), _save_positions(...), _save_metadata(...), _export_csv(...)
        功能: 分别写 parquet/CSV/metadata JSON；metadata 包含汇率、券商列表、时间戳与文件名。

    关键注意事项
        - 现金数据按 USD/HKD/CNY 汇总并转换到 USD_total；缺失字段用 0。
        - 持仓需有 final_price 与 multiplier；若价格缺失保持原值，仍计入 position_value_usd。
        - Money market 归类依赖 utils.is_money_market_fund，需保持列表更新。
