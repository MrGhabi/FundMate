src/price_fetcher.py
    功能描述: 抽象价格获取与组合估值。支持 Futu、Akshare；含期权解析与近似查找。

    normalize_symbol(raw_symbol)
        功能: 标准化标的代码供行情接口使用（去空格/大小写/补前缀）。

    get_price_akshare(symbol, date), get_price_futu(symbol, date)
        功能: 分别从 Akshare/Futu 获取历史价，返回 float 或 None。

    get_stock_price(symbol, date, source=None, raw_description=None) -> (price, source)
        功能: 统一入口，优先 Futu，失败回退 Akshare；可传 raw_description 辅助期权解析。

    calculate_portfolio_value(holdings, date, source=None, exchange_rates=None)
        功能: 为持仓列表批量取价并计算 USD 价值，返回列表/失败列表。

    parse_morgan_option(option_str), find_closest_futu_option(...), get_option_price_futu(...)
        功能: 期权工具函数，处理摩根格式、按行权价/到期日匹配最接近的 Futu 代码并取价。

    注意事项
        - 价格获取失败会返回 None 并记录；上层需决定保留券商价或跳过。
        - 期权 multiplier 由上游（Position/TC）提供或默认 100/1000。
