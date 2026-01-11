src/hk_option_price_helper.py
    功能描述: 处理 HKATS 期权描述与 Futu 价格获取的辅助函数。

    parse_hk_option_description(description) -> dict|None
        功能: 从描述解析标的、到期、行权价、CP。

    construct_hk_option_code(hkats_code, expiry_date, strike, option_type) -> str
        功能: 生成 Futu 可用的 HK 期权代码。

    get_hk_option_price_from_futu(stock_code, raw_description, date) -> Optional[float]
        功能: 尝试通过解析描述/代码获取 Futu 历史价，失败返回 None。
        注意: 依赖网络接口；返回价与 multiplier 需上游处理。
