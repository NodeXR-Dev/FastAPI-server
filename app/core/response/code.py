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
    # Graph
    # =========================
    GRAPH200 = "GRAPH200"  # 회의실 그래프 복원 조회 성공

    # =========================
    # Part Node
    # =========================
    PART_NODE200 = "PART_NODE200"  # 파트 노드 생성 성공
    PART_NODE201 = "PART_NODE201"  # 파트 노드 수정 성공
    PART_NODE202 = "PART_NODE202"  # 파트 노드 삭제 성공

    PART_NODE400 = "PART_NODE400"  # 잘못된 파트 노드 요청
    PART_NODE404 = "PART_NODE404"  # 파트 노드 없음

    # =========================
    # Reference
    # =========================
    REFERENCE201 = "REFERENCE201"  # 레퍼런스 저장 성공
    REFERENCE400 = "REFERENCE400"  # 잘못된 레퍼런스 요청
    REFERENCE500 = "REFERENCE500"  # 레퍼런스 저장 오류
    
    # =========================
    # Room
    # =========================
    ROOM200 = "ROOM200" # 회의실 생성 성공
    ROOM201 = "ROOM201" # 회의실 목록 조회 성공
    ROOM202 = "ROOM202" # 회의실 상세 정보 조회 성공
    ROOM203 = "ROOM203" # 회의실 최초 입장 성공
    ROOM204 = "ROOM204" # 회의실 재입장 성공
    ROOM205 = "ROON205" # 회의실 퇴장 성공
    
    ROOM400 = "ROOM400"  # 잘못된 회의실 요청
    ROOM401 = "ROOM401"  # 회의실 비밀번호 불일치
    ROOM404 = "ROOM404"  # 회의실 없음
    ROOM_MEMBER404 = "ROOM_MEMBER404" # 멤버 없음
    
    # =========================
    # Feature
    # =========================
    FEATURE200 = "FEATURE200"  # 기능 생성 성공
    FEATURE201 = "FEATURE201"  # 기능 수정 성공
    FEATURE202 = "FEATURE202"  # 기능 삭제 성공
    FEATURE203 = "FEATURE203"  # 기능 목록 조회 성공
    
    FEATURE400 = "FEATURE400"  # 잘못된 기능 요청
    FEATURE404 = "FEATURE404"  # 기능 없음
    FEATURE500 = "FEATURE500"  # 기능 추출 또는 저장 오류
    
    # =========================
    # Guide
    # =========================
    GUIDE400 = "GUIDE400"    # 발화 가이드 요청값 오류
    GUIDE500 = "GUIDE500"    # 발화 가이드 생성 오류
    
    # =========================
    # WebSocket
    # =========================
    WS200 = "WS200"          # 웹소켓 연결 성공
    WS400 = "WS400"          # 웹소켓 요청 형식 오류
    WS404 = "WS404"          # 지원하지 않는 웹소켓 이벤트
    WS409 = "WS409"          # 웹소켓 room_id 불일치
    WS500 = "WS500"          # 웹소켓 서버 오류
    
    # =========================
    # 2D Image
    # =========================
    IMG202 = "IMG202"        # 이미지 요청 성공
    IMG500 = "IMG500"
    COLOR_CHANGE201 = "2D201"
    COLOR_CHANGE400 = "2D400"
    COLOR_CHANGE404 = "2D404"

    # =========================
    # 3D Model
    # =========================
    MODEL_3D200 = "3D200"
    MODEL_3D400 = "3D400"
    MODEL_3D404 = "3D404"
    MODEL_3D500 = "3D500"
    
    HISTORY200 = "HISTORY200"
    HISTORY400 = "HISTORY400"
    HISTORY404 = "HISTORY404"
    HISTORY500 = "HISTORY500"

    # =========================
    # Report
    # =========================
    REPORT200 = "REPORT200"
    
    
RESPONSE_MESSAGES = {
    ResponseCode.BTUTT200: "버튼 조작 발화 처리 성공",
    ResponseCode.BTUTT400: "발화 요청값이 올바르지 않습니다.",
    ResponseCode.BTUTT404: "발화 처리에 필요한 리소스를 찾을 수 없습니다.",
    ResponseCode.BTUTT500: "발화 처리 중 서버 오류가 발생했습니다.",
    
    ResponseCode.UTT404: "해당 발화 객체가 존재하지 않습니다.",
    
    ResponseCode.NODE404: "해당 노드 객체가 존재하지 않습니다.",

    ResponseCode.GRAPH200: "노드 그래프 조회 성공",

    ResponseCode.PART_NODE200: "파트 노드 생성 성공",
    ResponseCode.PART_NODE201: "파트 노드 수정 성공",
    ResponseCode.PART_NODE202: "파트 노드 삭제 성공",
    ResponseCode.PART_NODE400: "잘못된 파트 노드 요청입니다.",
    ResponseCode.PART_NODE404: "파트 노드를 찾을 수 없습니다.",

    ResponseCode.REFERENCE201: "레퍼런스 저장 성공",
    ResponseCode.REFERENCE400: "잘못된 레퍼런스 요청입니다.",
    ResponseCode.REFERENCE500: "레퍼런스 저장 중 서버 오류가 발생했습니다.",
    
    ResponseCode.ROOM200: "회의실 생성 성공",
    ResponseCode.ROOM201: "회의실 목록 조회 성공",
    ResponseCode.ROOM202: "회의실 상세 정보 조회 성공",
    ResponseCode.ROOM203: "회의실 최초 입장 성공",
    ResponseCode.ROOM204: "회의실 재입장 성공",
    ResponseCode.ROOM205: "회의실 퇴장 성공",
    ResponseCode.ROOM400: "잘못된 회의실 요청입니다.",
    ResponseCode.ROOM401: "회의실 비밀번호가 일치하지 않습니다.",
    ResponseCode.ROOM404: "회의실을 찾을 수 없습니다.",
    ResponseCode.ROOM_MEMBER404: "해당 회의실에 존재하지 않는 사용자입니다.",
    
    ResponseCode.FEATURE200: "기능 생성 성공",
    ResponseCode.FEATURE201: "기능 수정 성공",
    ResponseCode.FEATURE202: "기능 삭제 성공",
    ResponseCode.FEATURE203: "기능 목록 조회 성공", 
    ResponseCode.FEATURE400: "잘못된 기능 요청입니다.",
    ResponseCode.FEATURE404: "기능을 찾을 수 없습니다.",
    ResponseCode.FEATURE500: "기능 생성 중 서버 오류가 발생했습니다.",
    
    ResponseCode.GUIDE400: "발화 가이드 요청값이 올바르지 않습니다.",
    ResponseCode.GUIDE500: "발화 가이드 생성 중 서버 오류가 발생했습니다.",
    
    ResponseCode.WS200: "회의실 웹소켓 연결 성공",
    ResponseCode.WS400: "WebSocket 요청 형식이 올바르지 않습니다.",
    ResponseCode.WS404: "지원하지 않는 WebSocket 이벤트입니다.",
    ResponseCode.WS409: "URL의 room_id와 요청 body의 room_id가 일치하지 않습니다.",
    ResponseCode.WS500: "WebSocket 이벤트 처리 중 서버 오류가 발생했습니다.",
    
    ResponseCode.IMG202: "2D 이미지 생성 요청이 접수되었습니다.",
    ResponseCode.IMG500: "2D 이미지 생성에 실패했습니다.",
    ResponseCode.COLOR_CHANGE201: "2D 색상 변경 요청 성공",
    ResponseCode.COLOR_CHANGE400: "잘못된 2D 색상 변경 요청입니다.",
    ResponseCode.COLOR_CHANGE404: "색상 변경에 필요한 리소스를 찾을 수 없습니다.",
    ResponseCode.MODEL_3D200: "3D 생성 요청 성공",
    ResponseCode.MODEL_3D400: "잘못된 3D 생성 요청입니다.",
    ResponseCode.MODEL_3D404: "3D 생성에 필요한 리소스를 찾을 수 없습니다.",
    ResponseCode.MODEL_3D500: "3D 생성 중 서버 오류가 발생했습니다.",
    
    ResponseCode.HISTORY200 : "노드 그래프 히스토리 조회 성공",
    ResponseCode.HISTORY400 : "노드 그래프 히스토리 조회 요청 실패",
    ResponseCode.HISTORY404 : "노드 그래프 히스토리가 존재하지 않습니다",
    ResponseCode.HISTORY500 :"노드 그래프 히스토리 조회 중 서버 오류가 발생했습니다",

    ResponseCode.REPORT200: "팀 프로젝트 레포트 생성 성공",
}


def get_message(code: ResponseCode) -> str:
    return RESPONSE_MESSAGES.get(code, "처리 결과 메시지가 정의되지 않았습니다.")
