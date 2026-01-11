src/option_parser.py
    功能描述: 期权解析注册表。统一将各类字符串解析为 ParsedOption（underlying/expiry/strike/type），供 Position 自动解析和 TC 匹配使用。

    register_parser(parser)
        功能: 向全局 ParserRegistry 注册解析器。

    parse_option(code) -> ParsedOption
        功能: 依次调用已注册解析器（OCC、HKATS、US long format、OTC 等），返回解析结果或 None。

    _init_default_parsers()
        功能: 初始化默认解析器集合；TC 模式下会额外注册 HKNumericParser（由 TradeConfirmationProcessor 注入）。

    注意事项
        - 解析顺序影响结果，应保持确定性。
        - 未解析到则返回 None，调用方需处理匹配失败。
