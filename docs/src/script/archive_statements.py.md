src/script/archive_statements.py
    功能描述: CLI 脚本，批量将 data 目录下的报表按券商/日期/账户号归档到 archives 结构。

    extract_account_id(pdf_path, broker_name)
        功能: 从文件名或内容抽取账户号。

    extract_date_from_dirname(dirname)
        功能: 从目录名解析日期。

    generate_archive_filename(broker_name, date, account_id, suffix)
        功能: 生成标准归档文件名。

    copy_and_archive(source_file, dest_dir, broker_name, account_id, stmt_date, dry_run=False)
        功能: 执行实际拷贝/命名；dry_run 仅打印。

    archive_all_statements(data_dir, archive_root, ...)
        功能: 遍历 data，调用上述函数完成归档。

    main()
        功能: CLI 入口，解析参数并执行批量归档。
