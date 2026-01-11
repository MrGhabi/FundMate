src/enums.py
    功能描述: 枚举定义，统一上下文标识。

    class PositionContext(Enum)
        成员: BASE（基准报表）、TC（交易确认增量）。
        用途: 标记 Position 来源，便于跟踪与调试。
