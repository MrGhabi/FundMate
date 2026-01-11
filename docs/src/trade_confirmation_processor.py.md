src/trade_confirmation_processor.py
    功能描述: TC 增量处理器。以基准日持仓为底，解析 TC Excel，按日期范围应用买卖/卖空/回补，更新持仓与现金，再统一定价落盘。

    class Transaction
        字段: date, broker, stock_code, direction, quantity, avg_price, amount_usd, currency, market。
        用途: 标准化 TC 行为，便于过滤和应用。

    standardize_option_format / _normalize_equity_code / _remove_leading_prefix
        功能: 清洗/标准化股票与期权代码（含 HK numeric→HKATS、US/HK option 字符串），确保 TC 与基准匹配。

    _parse_tc_excel(file_path, file_date) -> List[Transaction]
        功能: 读取 TC Excel，校验必需列；规范方向（SELLSHORT 设为 SELL 且数量转负）；清理代码（去 Equity/路由前缀/Bloomberg 后缀）；金额取绝对值。
        重要: SELL SHORT 首笔开空数量为负；BUY/BUYCOVER 正数。

    _apply_transactions(base_results, transactions, broker_statement_dates, target_date, fallback_base_date)
        功能: 按券商分组过滤日期范围（含特殊 inclusive_start_brokers），依次应用交易，处理完后清除 0 仓位。
        时间窗口: 默认 (statement_date, target_date]，但对 LB 等特例 inclusive_start_brokers，会包含 statement_date 当日的 TC（例如基准报表 07-31，需叠加 07-31 当日 LB 的 TC）。

    _apply_buy(result, txn)
        功能: 找到持仓则加仓；不存在则新建正仓；现金扣减 txn.amount_usd。

    _apply_sell(result, txn)
        功能: 统一入口处理 SELL/SELL SHORT。若 quantity<0（卖空开仓或加深空头）：不存在则新建空仓（负仓），存在则减持；现金增加。若 quantity>0 且无持仓则报错（仅普通卖出才要求持仓）。允许在已有空头上继续增加空。

    _find_position(...)
        功能: 用标准化后的代码匹配 Position（含 option parser fuzzy），确保 TC 与基准合并。

    _update_prices(results, target_date, exchange_rates)
        功能: 汇总唯一标的获取行情（Futu/Akshare），回填 final_price/optimized_price_currency，计算 position_value_usd。
        价格优先级: Futu 行情 > TC 成交价（无行情时兜底，source=TC transaction price）> broker_price；全部缺失才记入 price_failures。

    TC 价格缓存
        解析 TC 时为每个标的缓存第一条成交价（avg_price, currency），供行情缺失时兜底。

    process_with_trade_confirmation(...)
        功能: 外部入口；跑基准（可 skip 日志）→解析/过滤 TC → 应用交易 → 定价 → 持久化。

    关键注意事项
        - SELL SHORT 新开仓：数量应为负，找不到持仓会自动新建负仓；普通 SELL 找不到则报错，防误判。
        - 日期过滤：默认 (statement_date, target]，部分券商 inclusive_start 特殊处理。
        - 价格抓取失败记录于 price_failures；定价回退顺序 Futu>TC 成交价>broker 价，缺失时才记失败。
        - 基准日由 main 推断；若缺目标日前报表，会用最近日期，导致 TC 叠加在更早基准上。
