from enum import Enum


class ResponseCode(str, Enum):
    # =========================
    # Common
    # =========================
    COMMON422 = "COMMON422"
    COMMON500 = "COMMON500"
    
    # =========================
    # Utterance
    # =========================
    BTUTT200 = "BTUTT200"   # 발화 처리 성공
    BTUTT400 = "BTUTT400"   # 발화 요청값 오류
    BTUTT404 = "BTUTT404"   # 발화 관련 리소스 없음
    BTUTT500 = "BTUTT500"   # 발화 처리 서버 오류
    
RESPONSE_MESSAGES = {
    ResponseCode.BTUTT200: "버튼 조작 발화 처리 성공",
    ResponseCode.BTUTT400: "발화 요청값이 올바르지 않습니다.",
    ResponseCode.BTUTT404: "발화 처리에 필요한 리소스를 찾을 수 없습니다.",
    ResponseCode.BTUTT500: "발화 처리 중 서버 오류가 발생했습니다.",
}


def get_message(code: ResponseCode) -> str:
    return RESPONSE_MESSAGES.get(code, "처리 결과 메시지가 정의되지 않았습니다.")