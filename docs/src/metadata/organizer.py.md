src/metadata/organizer.py
    功能描述: 根据探测出的 MetadataRecord 将原始报表归档到规范目录（按券商/日期），并处理变体/去重/合并（如 GSPB 现金+持仓 Excel）。

    read_metadata(jsonl_path)
        功能: 读取 detect 输出的 jsonl，生成 MetadataRecord 列表。

    organize_files(records, output_dir, dry_run=False)
        功能: 主流程。逐记录计算目标路径、创建目录、拷贝或移动文件；dry_run 时仅打印。
        注意: 会调用 _resolve_target_path/_resolve_variant_target，避免覆盖；维护已存在文件的 hash 列表。

    _compute_sha256(path), _load_archive_hashes(...)
        功能: 计算并缓存归档文件的 hash，防止重复。

    _extract_date(name)
        功能: 从文件名解析日期（YYYY-MM-DD）；找不到则返回 None。

    _resolve_target_path / _resolve_variant_target
        功能: 基于券商、日期、账户号推导标准路径；若冲突则生成 variant 目标。

    _derive_suffix_from_name
        功能: 用文件名推断类型后缀（pdf/xlsx/csv），保持扩展名一致。

    _merge_gspb_excels(position_path, cash_path, account_id, stmt_date)
        功能: 特殊处理 GSPB 现金/持仓分文件的情况，合并为单一 Excel。

    main()
        功能: CLI 入口，参数包含 metadata jsonl、输出目录、dry_run。
