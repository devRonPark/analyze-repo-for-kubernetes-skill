# Codex UI Intake Integration

대화형 Codex 검증은 원본 repository나 한글 경로 workspace를 사용하지 않는다. projectless ASCII task를 만들고 설치된 skill의 `SKILL.md` checksum이 검증할 source revision과 일치하는지 먼저 확인한다.

## 준비

1. Codex hook을 포함해 skill을 설치하고 `/hooks`에서 이 skill의 hook을 검토·신뢰한다.
2. ASCII 이름의 projectless task를 만든다. 예: `k8s-intake-ui-validation`.
3. Target으로 사용될 repository, local checkout, archive를 이 task에 제공하지 않는다.

## 대화형 시나리오

| 입력 | 기대 결과 |
| --- | --- |
| `/analyze-repo-for-kubernetes` | source 제공 방식 질문 한 번, workspace 탐색 command 없음 |
| source 제공 방식에서 `Repository URL` 선택 | `분석할 GitHub 또는 Git repository URL을 입력해 주세요.` 질문 한 번 |
| source 제공 방식에서 `Local directory path` 선택 | `분석할 local directory path를 입력해 주세요.` 질문 한 번 |
| source 제공 방식에서 `Source archive` 선택 | `분석할 ZIP, tar, tar.gz 또는 tgz archive path를 입력해 주세요.` 질문 한 번 |
| `https://github.com/example/repo.git 를 Kubernetes 설계 준비에 활용할 수 있게 분석해` | URL 재질문 없음, 목적 질문 없음 |
| `/analyze-repo-for-kubernetes https://github.com/example/one.git`와 자연어의 다른 URL | Slash Input URL 우선 |
| `/analyze-repo-for-kubernetes .` | 목적 선택 질문 한 번, inventory command 없음 |
| `/analyze-repo-for-kubernetes . 전체 상세 보고서` | 목적 질문 없음, Target 확인 후 분석 진행 |

각 실행에서 질문 UI의 개수와 command event를 기록한다. Target 없는 첫 시나리오는 skill/AGENTS bootstrap read는 허용하지만, workspace path를 대상으로 한 `rg`, `find`, `ls`, `git` discovery가 완료되면 실패다. 첫 source 제공 방식 질문과 두 번째 target 값 질문이 같은 turn에 함께 나오면 실패다. Codex hosted web 도구는 `PreToolUse` hook 범위 밖이므로, web event가 발생하지 않았는지도 별도로 확인한다.
