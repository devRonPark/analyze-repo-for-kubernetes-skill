# 근거 패턴은 판단 규칙이 아니라 수집 규칙으로 사용한다

상태: accepted

Repository-to-Kubernetes 분석에서는 결정론적 로직과 LLM 추론을 분리된 seam으로 유지한다. 결정론적 패턴 로직은 manifest, lockfile, Dockerfile, Compose 파일, Kubernetes resource, CI workflow, framework configuration처럼 안정적인 저장소 형식에서 line-addressable typed evidence를 수집한다. 이 패턴 로직은 production readiness, deployable ownership, default deployment path, requiredness를 단독으로 결정하지 않는다.

팩트 체크 리서치 결과, 패턴 pack은 evidence-discovery accelerator로는 충분하지만 다양한 언어, framework, monorepo, 회사별 layout을 가로지르는 full analyzer로는 불충분했다. 따라서 LLM-centered triage가 semantic interpretation을 담당하고, deterministic verifier가 unsupported claim, invalid citation, schema drift, secret leakage를 차단한다.

결과적으로 새로운 ecosystem 지원은 hard-coded analyzer conclusion이 아니라 extractable evidence fact를 먼저 추가해야 한다. LLM-discovered hint는 공식 owner source가 있고, 실제 repository에서 반복 발견되며, 안정적인 path/line fact를 만들고, 읽기 비용을 낮추며, false positive 위험이 낮고, fixture로 검증 가능한 경우에만 maintained pattern으로 승격한다.
