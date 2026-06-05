from enum import Enum


class ResponseCode(str, Enum):
    # =========================
    # Common
    # =========================
    COMMON400 = "COMMON400"
    COMMON422 = "COMMON422"
    COMMON500 = "COMMON500"
    
    # =========================
    # Utterance
    # =========================
    BTUTT200 = "BTUTT200"   # 발화 처리 성공
    BTUTT400 = "BTUTT400"   # 발화 요청값 오류
    BTUTT404 = "BTUTT404"   # 발화 관련 리소스 없음
    BTUTT500 = "BTUTT500"   # 발화 처리 서버 오류
    UTT404 = "UTT404"       # 발화 객체 없음
    
    # =========================
    # Node
    # =========================
    NODE404 = "NODE404" # 노드 객체 없음
    
    # =========================
    # Room
    # =========================
    ROOM200 = "ROOM200" # 회의실 생성 성공
    ROOM201 = "ROOM201" # 회의실 목록 조회 성공
    ROOM202 = "ROOM202" # 회의실 상세 정보 조회 성공
    ROOM203 = "ROOM203" # 회의실 최초 입장 성공
    ROOM204 = "ROOM204" # 회의실 재입장 성공
    
    ROOM400 = "ROOM400"  # 잘못된 회의실 요청
    ROOM401 = "ROOM401"  # 회의실 비밀번호 불일치
    ROOM404 = "ROOM404"  # 회의실 없음
    
RESPONSE_MESSAGES = {
    ResponseCode.BTUTT200: "버튼 조작 발화 처리 성공",
    ResponseCode.BTUTT400: "발화 요청값이 올바르지 않습니다.",
    ResponseCode.BTUTT404: "발화 처리에 필요한 리소스를 찾을 수 없습니다.",
    ResponseCode.BTUTT500: "발화 처리 중 서버 오류가 발생했습니다.",
    ResponseCode.UTT404: "해당 발화 객체가 존재하지 않습니다.",
    ResponseCode.NODE404: "해당 노드 객체가 존재하지 않습니다.",
    ResponseCode.ROOM200: "회의실 생성 성공",
    ResponseCode.ROOM201: "회의실 목록 조회 성공",
    ResponseCode.ROOM202: "회의실 상세 정보 조회 성공",
    ResponseCode.ROOM203: "회의실 최초 입장 성공",
    ResponseCode.ROOM204: "회의실 재입장 성공"
}


def get_message(code: ResponseCode) -> str:
    return RESPONSE_MESSAGES.get(code, "처리 결과 메시지가 정의되지 않았습니다.")