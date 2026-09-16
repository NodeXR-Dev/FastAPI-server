from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


DROP = "DROP"
STORE_ONLY = "STORE_ONLY"
FULL_PROCESS = "FULL_PROCESS"


class NoiseFilterService:
    """STT 발화를 처리 단계로 분류한다.

    길이만으로 판단하면 "좋아", "반대", "철로" 같은 짧지만 의미 있는 발화까지
    버리게 되므로, 1차 판정은 정확 일치 사전으로만 수행한다.
    """

    # 정보량이 없는 순수 filler. 저장하지 않아도 되는 것들.
    DROP_TOKENS = frozenset(
        {
            "음", "으음", "어", "어어", "아", "아아", "오", "엄", "흠",
            "그", "저", "저기", "뭐", "그니까", "그러니까",
            "ㅋㅋ", "ㅋㅋㅋ", "ㅎㅎ", "ㅎㅎㅎ", "아하", "오오",
        }
    )

    # 설계 내용은 없지만 합의/반대 신호로서 가치가 있는 것들. 저장은 한다.
    STORE_ONLY_TOKENS = frozenset(
        {
            "응", "응응", "네", "넵", "예", "그래", "그렇지", "맞아", "맞아요",
            "좋아", "좋아요", "오케이", "ok", "그러자", "알겠어", "알겠습니다",
            "아니", "아니요", "아냐", "글쎄", "음글쎄",
        }
    )

    _TRAILING = " .!?~,…"

    def classify(
        self,
        *,
        normalized_text: str,
        previous_text: str | None = None,
    ) -> str:
        key = self._match_key(normalized_text)
        if not key:
            return DROP
        if previous_text is not None and key == self._match_key(previous_text):
            # STT 중복 전송. 원문은 남기되 재처리하지 않는다.
            return STORE_ONLY
        if key in self.DROP_TOKENS:
            return DROP
        if key in self.STORE_ONLY_TOKENS:
            return STORE_ONLY
        return FULL_PROCESS

    @classmethod
    def _match_key(cls, text: str) -> str:
        return (text or "").strip().strip(cls._TRAILING).strip().casefold()

    @staticmethod
    def is_shadow_mode() -> bool:
        return settings.NOISE_FILTER_MODE == "shadow"
