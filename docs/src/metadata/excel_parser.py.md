src/metadata/excel_parser.py
    功能描述: 针对 Excel 报表的元数据提取（账户号/日期/券商等），用于归档决策。

    核心流程
        - 加载工作簿，按券商特定表头/命名规则解析日期与账户号。
        - 产生 MetadataRecord（broker/account_id/statement_date/path）。

    注意事项
        - 依赖券商特定格式，若无法解析返回空元数据。
        - 与 organizer 搭配使用，确保文件能被放入正确子目录。
