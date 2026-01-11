src/config.py
    功能描述: 配置加载，封装 pydantic BaseSettings；提供路径、API Key、并发等全局配置。

    class Settings(BaseSettings)
        主要字段: LOG_DIR, OUT_DIR, ARCHIVE_DIR, TC_DIR, FUTU_* 凭据、LLM 模型名、并发/超时参数。
        功能: 从环境变量或 .env 读取配置，提供默认值。

    settings = Settings()
        功能: 全局单例，用于各模块导入。

    注意: 修改 .env 后需重启服务；路径用于档案/输出/缓存，需确保存在或由代码创建。
