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

    _PATTERN = re.compile(
        r"노\s*드\s*베\s*어|노\s*드\s*배\s*어|node\s*bear",
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
