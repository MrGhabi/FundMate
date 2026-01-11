src/utils.py
    功能描述: 通用工具集，涵盖期权识别/乘数、估值、日志、输入校验、资产汇总、货币基金判断。

    def _identify_hk_option(stock_code: str, raw_description: str = None) -> bool
        功能: 判断是否港股期权（HKATS 格式如 "CLI 250929 19.00 CALL"）。
        注意: 优先使用 broker 乘数（Priority 1），此函数作为 fallback（Priority 4）。

    def is_option_contract(stock_code: str, raw_description: str = None) -> bool
        功能: 判断是否期权（含 HK/US/OTC 关键字和 OCC 格式）。
        支持: CALL/PUT/OPTION 关键字、OCC 格式（如 SBET260116P25000）。

    def get_option_multiplier(stock_code: str, raw_description: str = None, broker_multiplier: int = None) -> Union[int, float]
        功能: 返回期权乘数。
        优先级: broker_multiplier > HK 期权 (100) > US 期权 (100) > 股票/OTC (1)。
        返回类型: int 或 float（支持债券等小数乘数如 0.01）。
        注意: OTC 期权乘数始终为 1；HK 期权无法查询 Futu API 获取实际乘数。

    def calculate_position_value(price: float, holding: int, stock_code: str, raw_description: str = None, broker_multiplier: int = None) -> Tuple[float, Union[int, float]]
        功能: 计算标的市值。
        返回: (position_value, multiplier_used) 元组。
        注意: 乘数缺省则自动获取；price <= 0 时返回 (0.0, 1)。

    def setup_logging(log_dir: str, date: str) -> None
        功能: 配置 loguru 输出到指定日期目录，创建带时间戳的日志文件。
        输出: 同时写入控制台（INFO）和文件（DEBUG）。

    def validate_date_format(date_str: str) -> bool
        功能: 验证日期格式为 YYYY-MM-DD。

    def validate_broker_folder(folder_path: str) -> bool
        功能: 验证目录存在性。

    def print_processing_info(broker_folder: str, date: str, broker: str = None, force: bool = False) -> None
        功能: 控制台输出处理信息 banner。

    def print_asset_summary(results: List[ProcessedResult], date: str = None) -> None
        功能: 打印完整资产汇总（现金 + 持仓），按券商遍历并聚合跨券商持仓。
        内容: 券商列表、各账户现金/持仓/总值、跨券商持仓聚合、总计。
        注意: 期权使用 raw_description 作为唯一标识避免合并不同合约。

    def is_money_market_fund(description: str = None) -> bool
        功能: 判断描述是否货币基金；供 data_persistence 现金归类。
        规则: 描述中包含 'money market fund'（不区分大小写）。
