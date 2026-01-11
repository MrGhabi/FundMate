src/exchange_rate_handler.py
    功能描述: 汇率获取与缓存。为指定日期获取货币互换汇率，提供多种接口供 BrokerStatementProcessor、utils、price_fetcher 使用。

    class ExchangeRateHandler
        __init__(cache_file='./out/exchange_rates_cache.json')
            功能: 初始化处理器，设置缓存文件路径和内存缓存字典。

        get_single_rate(from_currency: str, to_currency: str, date: str) -> float
            功能: 获取单一汇率，双层缓存（内存+JSON 文件），缓存未命中则调用 API。
            注意: 有 0.6s 限速防止 429 错误；失败抛异常。

        get_rates_dynamic(currencies_needed: List[str], target_currency='USD', date=None) -> Dict[str, float]
            功能: 按需动态获取汇率，返回直接转换率字典。
            示例: {'HKD': 0.128, 'CNY': 0.139, 'USD': 1.0} 表示 1 HKD = 0.128 USD。

        get_rates_legacy(date: str = None) -> Dict[str, float]
            功能: 向后兼容方法，获取 CNY/HKD→USD 汇率。
            输出: {'CNY': rate, 'HKD': rate, 'USD': 1.0}
            注意: 优先使用本地缓存 (out/exchange_rates_cache.json)，否则远程获取并写回缓存；失败抛异常。

        get_rate_lazy(from_currency: str, to_currency: str = 'USD', date: str = None) -> float
            功能: 惰性加载汇率，仅在需要时获取。
            输入: 源货币、目标货币（默认 USD）、日期（默认当日）。
            输出: 直接转换率（from_currency → to_currency）。
            注意: 同币种返回 1.0；被 utils.py 和 price_fetcher.py 广泛使用。

        convert_to_usd(amount: float, currency: str, exchange_rates: Dict[str, float] = None) -> float
            功能: 使用直接转换率将金额转换为 USD。
            注意: 未找到汇率时使用 1:1 转换并记录警告。

        _load_rate_from_json(from_currency, to_currency, date) -> Optional[float]
            功能: 从 JSON 缓存文件加载汇率。

        _save_rate_to_json(from_currency, to_currency, date, rate) -> None
            功能: 将汇率保存到 JSON 缓存文件。

    exchange_handler (单例)
        功能: 默认实例，供全局导入复用缓存。
        用法: from src.exchange_rate_handler import exchange_handler
