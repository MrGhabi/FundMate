src/main.py
    功能描述: CLI 入口。解析参数（日期、是否 TC、档案目录/TC 目录、并发等），推断基准日，调用 BrokerStatementProcessor 或 TradeConfirmationProcessor，全流程落盘。

    def infer_base_date_from_broker_folder(broker_folder: str, target_date: str) -> str
        功能: 在档案模式下，从归档文件名中选取 ≤ target_date 的最新日期作为基准日。
        输入: broker_folder 路径，目标日期 YYYY-MM-DD。
        输出: 基准日字符串。
        注意: 依赖文件命名规范，若缺目标日前的报表则回退更早日期。

    def create_argument_parser() -> argparse.ArgumentParser
        功能: 构建命令行参数，包括日期、broker 过滤、档案目录、TC 目录、并发、日志等。
        输出: argparse 解析器。

    def main()
        功能: 解析参数→推断基准日→选择模式：
              - 普通模式: 直接调用 BrokerStatementProcessor.process_folder。
              - TC 模式: 先跑基准（skip_logging_setup），再调用 TradeConfirmationProcessor.process_with_trade_confirmation。
        依赖: settings 配置、probe 进度记录、DataPersistence 落盘。
        注意: 档案模式无需子目录结构；TC 模式会跳过日志初始化并重用基准结果。
