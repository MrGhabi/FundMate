src/metadata/detector.py
    功能描述: 基于 LLM 的报表元数据探测。生成 prompt，批量迭代文件，产出 StatementMetadata 列表（含券商/日期/账户号等），供 organizer 使用。

    CANONICAL_BROKER_KEYWORDS: Dict[str, List[str]]
        功能: 定义规范券商名称到关键字列表的映射，用于 LLM 提示和结果标准化。
        注意: 必须与 webapp/app.py 的 BROKER_PATTERNS 保持同步。

    @dataclass StatementMetadata
        字段: file, broker_name, account_id, statement_date, source, extra。
        用途: 标准化元数据检测结果，source 指示来源（llm/excel_structured/csv_header/error）。

    class StatementMetadataDetector
        __init__(llm_handler=None, max_pdf_pages=2)
            功能: 初始化检测器，可选注入 LLMHandler；Excel 使用 ExcelMetadataExtractor。

        detect_pdf(path: Path) -> StatementMetadata
            功能: 使用 LLM 提取 PDF 元数据；自动解密加密 PDF（依赖 BROKER_CONFIG 密码）。
            输入: PDF 文件路径。
            输出: StatementMetadata（source="llm"）。
            异常: LLM handler 未配置或解密失败时抛出 RuntimeError/ValueError。

        detect_excel(path: Path) -> StatementMetadata
            功能: 使用 ExcelMetadataExtractor 解析 Excel 元数据。
            输入: Excel 文件路径（.xls/.xlsx）。
            输出: StatementMetadata（source="excel_structured"）。

        detect_file(path: Path) -> Optional[StatementMetadata]
            功能: 统一入口；根据后缀分派到 detect_pdf/detect_excel/_detect_csv_metadata。
            支持: .pdf, .xls, .xlsx, .csv

        _detect_csv_metadata(path: Path) -> Optional[StatementMetadata]
            功能: 检测 DBS 现金 CSV 格式（严格 5 行表结构）。
            格式要求:
                1) Name of the Bank:,DBS
                2) Date,MM/DD/YYYY
                3) USD,<number>
                4) HKD,<number>
                5) CNY,<number>
            输出: StatementMetadata（source="csv_header"，extra 含 usd/hkd/cny 金额）。

        _prepare_pdf_for_detection(path: Path) -> Path
            功能: 检测加密 PDF，使用 BROKER_CONFIG 密码解密到临时文件。
            注意: 未配置密码的加密 PDF 会抛出 ValueError。

        _normalize_date(value: str) -> Optional[str]
            功能: 将各种日期格式转换为 YYYY-MM-DD。
            支持: YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY, "Month DD, YYYY", 范围格式（取末日期）。

        _canonicalize_broker(value: str) -> Optional[str]
            功能: 将 LLM 返回的券商名标准化为 CANONICAL_BROKER_KEYWORDS 中的规范名。

    build_metadata_prompt(file_name: str) -> List[Dict[str, str]]
        功能: 构造提示，指导 LLM 识别报表属性。

    detect_paths(paths, llm_handler=None, max_workers=1) -> List[StatementMetadata]
        功能: 并发处理输入文件路径，调用 StatementMetadataDetector 获取元信息。
        注意: max_workers 控制并发；llm_handler 可注入以复用。

    iter_files(root: Path, suffixes=None) -> List[Path]
        功能: 遍历目录收集指定后缀文件（默认 .pdf/.xls/.xlsx）。
        过滤: 跳过 __MACOSX 目录、.DS_Store 文件、._ 前缀文件。

    main()
        功能: CLI 入口，读取参数（根目录/并发），调用 detect_paths 输出 jsonl。
        用法: python -m src.metadata.detector <input_dir> --output metadata.jsonl
