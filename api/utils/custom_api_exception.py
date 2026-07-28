from fastapi import HTTPException


class CustomAPIException(HTTPException):
    def __init__(self, status_code: int, message: str, code: str, params: dict):
        super().__init__(status_code=status_code, detail={"message": message, "code": code, "params": params})
