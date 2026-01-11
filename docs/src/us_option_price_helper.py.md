src/us_option_price_helper.py
    功能描述: 处理美式期权描述解析与 Futu 价格查询。

    parse_us_option_description(description) -> dict|None
        功能: 提取标的、到期日、行权价、CP 信息。

    get_us_option_price_from_futu(stock_code, raw_description, date) -> (price, multiplier)
        功能: 标准化代码后从 Futu 获取历史价，推断 multiplier（通常 100）；失败返回 (None, None)。
