# app/core/performance.py

from collections import defaultdict


class PerformanceTracker:
    """
    서버 실행 중 단계별 평균 처리 시간을 저장하는 간단한 tracker.

    주의:
    - 서버 재시작하면 평균값은 초기화됨
    - 운영 환경에서는 Prometheus, Grafana 같은 모니터링 도구를 붙이는 게 더 좋음
    """

    def __init__(self):
        self.total_time_by_stage: dict[str, float] = defaultdict(float)
        self.count_by_stage: dict[str, int] = defaultdict(int)

    def record(self, stage: str, elapsed_ms: float) -> float:
        """
        특정 stage의 실행 시간을 기록하고 평균 시간을 반환한다.
        """
        self.total_time_by_stage[stage] += elapsed_ms
        self.count_by_stage[stage] += 1

        return self.total_time_by_stage[stage] / self.count_by_stage[stage]


performance_tracker = PerformanceTracker()