src/webapp/app.py
    功能描述: Flask Web 应用。提供上传、运行管线、展示进度/结果/API 导出等接口；封装文件解压/归档、作业持久化、前端格式化。

    配置与常量
        BROKER_PATTERNS: Dict[str, List[str]]
            功能: 文件名模式匹配自动检测券商。
            注意: 必须与 src/metadata/detector.py 的 CANONICAL_BROKER_KEYWORDS 保持同步。

        ARCHIVE_DIR, TC_DIR: 归档目录和 TC 文件目录，可通过环境变量覆盖。

    文件与归档
        allowed_file(filename) -> bool
            功能: 检查上传文件扩展名白名单（pdf/xlsx/xls/zip/rar）。

        extract_archive(archive_path: Path, extract_to: Path) -> List[Path]
            功能: 安全解压 ZIP/RAR 归档，返回提取的允许类型文件列表。
            注意: 跳过 __MACOSX、.DS_Store、._ 前缀文件；防止路径遍历攻击。

        extract_zip_file(zip_path, extract_to) -> List[Path]
            功能: 解压 ZIP 文件（legacy 方法）。

        organize_files_by_broker(files, date, base_dir) -> Tuple[Dict, List]
            功能: 按券商/日期分组文件。

        _copy_into_archive(src_dir: Path, archive_dir: Path) -> None
            功能: 将上传文件复制到归档目录，保持子目录结构（TC 强制落入 TC 子目录）。
            注意: 使用 SHA-256 去重，相同内容跳过，不同内容追加 _uploadN 后缀。

        detect_broker_from_filename(filename) -> Optional[str]
            功能: 基于 BROKER_PATTERNS 从文件名猜测券商。

    作业与进度
        update_job_status(job_id, status, message=None, progress=None, error=None, result=None)
            功能: 更新处理作业状态；完成/失败时自动持久化到历史文件。

        _persist_job_history(job_id, job) -> None
            功能: 追加作业快照到 temp/job_history.jsonl。

        _load_job_history(limit=200) -> List[dict]
            功能: 加载最近 N 条作业历史记录。

        _compact_result(result) -> dict
            功能: 压缩作业结果，仅保留关键字段用于历史存储。

        process_multiple_brokers(job_id, broker_files, date, base_dir)
            功能: 后台线程处理多券商报表。

        run_date_pipeline(job_id: str, date: str, use_tc: bool = True)
            功能: 核心管线运行函数，执行 main.py 处理指定日期数据。
            流程: 启动 probe → 调用 process_main → 构建结果 → 更新状态。
            注意: 通过 probe 回调实时推送进度到前端。

    视图/API
        index() -> 首页/Dashboard
        positions() -> 持仓详情页
        cash() -> 现金详情页
        compare() -> 日期对比页
        about() -> 关于页
        upload_page() -> 上传页面

        upload_files() [POST]
            功能: 处理上传表单，保存文件 → 解压 → 元数据检测 → 归档。
            返回: job_id，后台异步处理。

        get_job_status(job_id) -> JSON
            功能: 查询单个作业状态。

        list_jobs() -> JSON
            功能: 列出所有作业（内存 + 持久化历史合并）。

        api_run_date() [POST]
            功能: API 触发日期管线运行。
            参数: date (YYYY-MM-DD), use_tc (bool)
            返回: job_id, status, archive_dir, tc_dir

        api_date_status() -> JSON
            功能: 检查指定日期是否有数据。

        api_summary(date) -> JSON
            功能: 获取日期摘要数据。

    数据加载
        get_available_dates() -> List[str]
            功能: 获取有处理结果的日期列表。

        load_portfolio_data(date) -> Dict
            功能: 加载指定日期的现金/持仓/元数据。

        calculate_summary(data) -> Dict
            功能: 计算投资组合摘要统计。

        calculate_comparison(data1, data2, date1, date2) -> Dict
            功能: 计算两个日期的对比数据。

        build_final_pipeline_result(date: str, result_dir: Path) -> Optional[Dict]
            功能: 读取 parquet 汇总并构建 per-broker USD 结果。
            返回: brokers 映射 + final_totals。

    辅助
        _safe_target_path(base_dir, member_name) -> Path
            功能: 防止解压时路径遍历攻击。

        _should_skip_member(name) -> bool
            功能: 判断是否跳过归档成员（__MACOSX、.DS_Store 等）。

        format_currency_filter, format_number_filter, format_percent_filter
            功能: Jinja2 模板过滤器。

    注意事项
        - 归档依赖文件命名/券商子目录，TC 文件强制放 TC 子目录以便解析。
        - 作业类型: metadata_only（上传检测）、pipeline_run（日期计算）。
        - 作业历史存储于 temp/job_history.jsonl，页面"Show Job History"使用。
        - 进度与状态通过 probe 回调和作业 JSON 提供给前端。
        - Positions 页面聚合时对价格/持仓做 NaN 保护。
