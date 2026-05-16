# 2 일만에 9 축의 production 화가 진행되었다 — llive v0.6.0 진척 업데이트

> [지난번 (2026-05-14)](./post_2026-05-14_overview.ja.md) 으로부터 2 일.
> `llmesh-llive` 는 9 축의 MVP skeleton 완성 → 첫 축의 production 화 +
> dual-license 전환까지 단숨에 진행되었습니다. **변화의 속도를 기록에 남기는** 의미에서
> 짧은 update 를 투하합니다.

## 무엇이 일어났는가 (2026-05-14 → 2026-05-16)

| 영역 | 2026-05-14 (지난번) | 2026-05-16 (지금) |
|---|---|---|
| 테스트 수 | 444 PASS | **815 PASS** (+371) |
| 아키텍처 축 | 8 설계 기둥 | **9 축 skeleton 완료** (KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL) |
| Conformance Manifest | 미집계 | **holds=24 / violated=0 / undecidable=1** |
| Approval Bus | in-memory MVP | **policy + SQLite ledger 로 production 화** (C-1 완료) |
| 라이선스 | MIT | **Apache-2.0 + Commercial 의 dual-license** 로 전환 (v0.6.0) |
| 거버넌스 | LICENSE 만 | NOTICE / CONTRIBUTING (DCO) / SECURITY / TRADEMARK 정비 |
| SPDX 헤더 | 없음 | **전 204 .py 에 `SPDX-License-Identifier: Apache-2.0`** 자동 삽입 |

## 9 축 skeleton — FullSense Spec v1.1 의 최종 형태

FullSense Spec 을 9 축까지 확장하여, 각 축을 최소 구현으로 갖췄습니다.

- **KAR (Knowledge Autarky)** — RAD 49 분야를 100 분야로 확장하는 로드맵, 지식 주권의 장기 계획
- **DTKR (Disk-Tier Knowledge Routing)** — MoE 의 디스크 버전. 1 skill = 1 파일로 동적 진화
- **APO (Autonomous Performance Optimization)** — 자기 자신을 tune (§E2 bounded modification)
- **ICP (Idle-Collaboration Protocol)** — idle 시간에 다른 Local LLM 과 협조 (LLMesh 사상 직계)
- **TLB (Thought Layer Bridge)** — 다관점 병렬의 지수 폭발을 Manifold Cache + Global Coordinator 로 억제
- **Math Toolkit** — 각 축의 수학적 근거를 RAD 코퍼스에서 직접 인용하는 운용
- **PM (Publication Media)** — asciinema / SVG / GIF / mp4 를 README 에 임베드하는 설명력 강화
- **RPAR (Robotic Process Automation Realisation)** — Sandbox → Permitted-action 의 단계 이행
- **SIL (Self-Interrogation Layer)** — 5 Interrogator 로 자신을 다각도로 추궁하는 내성층

Conformance Manifest 가 **holds=24 / violated=0** 으로 갖춰졌으므로, 9 축의 MVP 는 사양 적합.

## Approval Bus 의 production 화 (C-1 완료)

RPA (Robotic Process Automation) 로 외부 부작용을 다룰 때, **승인 버스** 가 핵심입니다.
v0.5.x 에서는 in-memory MVP 였지만, v0.6.0 에서 다음을 production 화:

- **Policy 추상화** — `AllowList` / `DenyList` / `CompositePolicy` 로 auto-approve / deny. `deny_overrides(allow, deny)` 헬퍼로 「deny 를 우선」의 전형을 1 줄로 구성
- **SQLite 영속화** — stdlib `sqlite3` 만. schema v1 (requests / responses / meta) 로 재기동 후에도 replay
- **하위 호환성** — `ApprovalBus()` 인수 없이는 구 동작과 완전 일치 (기존 8 건 테스트 무수정)

`@govern(policy)` 를 ProductionOutputBus 에 통합하는 C-2 가 다음 타깃.

## Dual-license 로 전환한 이유

OSS 보급을 최우선으로 하면서, 장기적으로 「특허 공격에 노출되지 않을 것」「상용 전개의 여지를 남길 것」을 양립하기 위해, v0.6.0 에서 **MIT → Apache-2.0 + Commercial** 로 전환했습니다.

- Apache-2.0 = OSS 이용자에게 **명시적인 특허 grant** + 기여자의 특허 소송 리스크 경감
- Commercial = SLA / 보상 / 클로즈드소스 통합이 필요한 기업용으로 별도 프레임

이와 함께 NOTICE / CONTRIBUTING (DCO 1.1) / SECURITY / TRADEMARK 를 정비. `@apache` / `@cncf` 맥락에서 익숙한 OSS 관행에 맞춘 형태로 정렬되었습니다.

## 커리어 관점에서 무엇이 늘었는가

지난번 기사에서 쓴 「설계 판단의 축적」에, 이 2 일로 4 개 추가:

1. **9 축 spec 을 unit test 로 고정화하는 경험** — 형식 검증이 아닌 runtime conformance manifest 로 「사양에 준수하는 것을 매번 CI 로 검증」
2. **승인 버스의 production 화** — auto-policy + persistent ledger + 하위 호환의 3 박자를, 추가로 non-breaking 으로 넣는 설계
3. **OSS 와 상용의 경계를 긋는 실무** — MIT 를 선택할지 Apache 를 선택할지, dual-license 의 이유를 Stakeholder 에게 설명할 수 있는 어휘
4. **SPDX / NOTICE / DCO / SBOM 의 운용** — 「코드 품질」뿐만 아니라 「라이선스 품질」을 CI 로 측정하는 발상

특히 3 은, AI 스타트업·규제 산업의 AI 도입 팀 모두 **실은 문서 쪽에서 멈추는** 영역입니다.

## 여기까지의 숫자

- **v0.6.0** (오늘 cut) — 9 축 skeleton + C-1 production + dual-license
- **815 tests / ruff clean** (v0.5.0 444 + 371)
- PyPI: `pip install llmesh-llive`
- 4 리포지토리 병행 운용: llive / llmesh / llove / llmesh-demos

## 무엇을 보여주고 싶은가

짧게 말하면 「**개인 프로젝트라도 여기까지 다듬을 수 있다**」를 실증하고 싶습니다.
2 일로 이 페이스를 지속할 수 있는 것은, 로드맵이 구체적 + 테스트가 먼저 쓰여 있어 0→1 의 견적이 어긋나지 않는 것, Spec 이 CLAUDE.md 와 CONTRIBUTING.md 로 고정되어 있어 의사결정의 왕복이 적은 것이 양 바퀴입니다.

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #OpenSource #ApacheLicense #개인개발 #커리어
