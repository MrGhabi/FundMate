src/position.py
    功能描述: 标准化持仓数据结构。自动解析期权、封装价格/乘数/货币等字段，提供匹配方法供 TC 与跨券商合并使用。

    class Position
        关键属性: stock_code, holding, broker_price, price_currency, final_price, optimized_price_currency, multiplier, broker, context。
        初始化: 自动调用 option_parser 解析期权（若可能），设置 multiplier。

        matches_option(other_position) -> bool
            功能: 基于解析后的期权字段（underlying/expiry/strike/OptionType）进行模糊匹配。

        to_dict()
            功能: 序列化 Position 为字典用于导出。

    注意事项
        - multiplier 可能来自券商或默认推断；缺失会影响市值计算。
        - stock_code 会在标准化时保留原字符串，解析后的字段用于匹配而非直接替换。
