# Skill ON/OFF Quality Eval Fixture

이 fixture는 `tests/fixtures/black_box_repo`를 같은 prompt, repository revision,
model, runtime option, tool permission으로 Skill ON과 Skill OFF 두 번 평가하는
초기 품질 비교 사례다.

Closed/not-planned dependency인 `#22`와 `#23`은 현재 `#27` normalizer output과
`scripts/validate_report.py` schema/citation validation contract로 reconcile한다.
이 fixture는 해당 closed issue를 다시 열거나 별도 structured-output contract로
확장하지 않는다.
