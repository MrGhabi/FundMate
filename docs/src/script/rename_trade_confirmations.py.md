src/script/rename_trade_confirmations.py
    功能描述: 批量重命名 TC Excel 文件为规范格式（TC-YYYY-MM-DD-*.xlsx），方便归档与解析。

    extract_date_from_filename(filename) -> str
        功能: 从原始文件名提取日期字符串。

    rename_trade_confirmations(folder, dry_run=True)
        功能: 遍历目录，按标准格式重命名；dry_run 时仅打印。

    main()
        功能: CLI 入口，解析参数并执行重命名。
