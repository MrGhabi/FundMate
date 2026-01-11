src/excel_parser.py
    功能描述: 解析 Excel 形式的券商报表（持仓/现金），返回 ProcessedResult 兼容格式。

    ExcelPositionParser（类）
        核心方法: parse_folder(...) 遍历指定日期及档案模式的 Excel，按券商模板抽取 holdings/cash。
        支持: IB/MS/GS 等 Excel 报表；在 BrokerStatementProcessor 中与 PDF 结果合并。
        注意: 依赖文件命名匹配日期；未匹配时返回空列表并记录警告。
