src/probe.py
    功能描述: 进度与状态探针，供 Web 前端展示。记录总进度、每券商状态、文件计数、TC 文件列表等，可推送回调。

    is_enabled() -> bool
        功能: 根据环境/配置判断是否启用探针。

    start(date, use_tc, archive_dir, tc_dir, output_path, job_id=None, on_update=None)
        功能: 初始化探针上下文，记录开始时间、参数、回调。

    add_file_counts(pdf_count=0, excel_count=0), record_files(broker, files, kind)
        功能: 记录已发现文件数量及具体列表。

    mark_broker_start / mark_broker_end
        功能: 更新单券商状态（queued/processing/completed/failed），可携带错误信息。

    set_broker_financials(broker, cash, positions_value_usd)
        功能: 记录每券商现金与持仓市值，供前端表格使用。

    set_tc_files(tc_files), finalize(...)
        功能: 记录 TC 文件列表，结束时落最终状态与耗时。

    get_data(), get_brokers()
        功能: 返回当前探针快照。

    内部: _compute_progress, _push_progress
        功能: 计算并推送整体进度百分比/提示信息。
