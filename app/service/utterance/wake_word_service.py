import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WakeWordMatch:
    matched: bool
    command_text: str


class WakeWordService:
    """발화에서 Agent 호출어를 찾아내고 명령 본문만 남긴다.

    STT가 "노드베어"를 "노드 베어", "노드배어" 등으로 흘려 적는 경우가 있어
    공백과 유사 표기를 허용한다.
    """

    # 두 번째 글자(베)는 STT 가 웨/에/뻬/페 등으로 흘려 적는 일이 잦아 넓게 받는다.
    # 실기 로그에서 "노드웨어" 로 들어와 호출어로 잡히지 않은 적이 있다.
    _PATTERN = re.compile(
        r"노\s*드\s*[베배웨외에뻬빼페]\s*어|노\s*드\s*웨어|node\s*bear|노드\s*bear",
        re.IGNORECASE,
    )
    # 호출어 뒤에 붙는 호격 조사와 구두점을 떼어낸다. ("노드베어야,", "노드베어!")
    # 조사는 호출어에 바로 붙고 뒤에 경계가 올 때만 제거한다.
    # 그래야 "노드베어 아까 …"의 "아까"를 깎아먹지 않는다.
    _TRAILING_PARTICLE = re.compile(
        r"^(?:[야아](?=[\s,.!?~·\-]|$))?\s*[,.!?~·\-]*\s*"
    )

    def detect(self, normalized_text: str) -> WakeWordMatch:
        text = (normalized_text or "").strip()
        match = self._PATTERN.search(text)

        if match is None:
            return WakeWordMatch(matched=False, command_text=text)

        before = text[: match.start()].strip()
        after = self._TRAILING_PARTICLE.sub("", text[match.end():]).strip()
        command_text = " ".join(part for part in (before, after) if part)

        return WakeWordMatch(matched=True, command_text=command_text)
