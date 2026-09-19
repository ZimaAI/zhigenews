"""Stable errors shared by the runtime and its restricted tools."""


class HarnessError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

    def as_result(self) -> dict:
        return {"ok": False, "code": self.code, "message": str(self), "truncated": False}


class RunCancelled(HarnessError):
    def __init__(self):
        super().__init__("CANCELLED", "运行已取消，停止后续模型和工具调用。")
