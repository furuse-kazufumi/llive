# LLM 의 "망각" 문제와 마주하기 위한 개인 프로젝트 — llive

> 자기 진화형 모듈식 메모리 LLM 프레임워크 `llmesh-llive` 를 설계·구현하고 있습니다.
> AI 를 더 깊이 이해하기 위해서, 그리고 자신의 엔지니어 커리어를 진정으로 어려운 문제에 묶어두기 위해서 진행 중입니다.

## 왜 시작했는가

LLM 을 실제 제품에 깊이 통합할수록, 같은 벽에 부딪히게 됩니다.

> 새로운 지식을 학습시키면, 어쩐 일인지 기존의 판단 기준이 무너진다.

이 **catastrophic forgetting (파국적 망각)** 은, 규제 산업이나 감사가 필수인 현장에서 AI 도입이 멈추는 가장 큰 이유 중 하나입니다. `llive` 는 이 문제를 「거대한 LLM 코어 가중치를 재학습하지 않고, 어떻게 능력을 지속적으로 흡수할까?」라는 설계 문제로 재정의해 진행하고 있는 개인 프로젝트입니다.

공개해보니 이것은 AI 를 **사용하는 쪽** 에서도, AI 를 **만드는 쪽** 에서도, 가장 근본적인 이해가 요구되는 주제였습니다. 업무에서 머신러닝이나 LLM 을 다루는 사람이라면 반드시 한 번은 설명 책임을 요구받는 영역입니다.

## llive 설계의 8 가지 기둥

`llmesh-llive` 는 다음 8 가지 설계 방침으로 구성되어 있습니다.

1. **고정 코어 + 가변 주변** — Decoder-only LLM 코어는 동결. Adapter / LoRA / 4 층 외부 메모리 / 가변 길이 BlockContainer 로 능력을 흡수.
2. **4 층 메모리의 책임 분리** — semantic（지식）/ episodic（경험）/ structural（관계）/ parameter（차분 가중치）.
3. **선언적 구조 기술** — sub-block 시퀀스를 YAML 로 표현. AI 가 제안·비교하기 쉬운 단위로 정렬.
4. **심사 기반 자기 진화** — 온라인은 메모리 쓰기와 가벼운 라우팅 조정만, 구조 변경은 오프라인 심사 경로로.
5. **생물학적 메모리 모델 직접 내장** — 해마-피질 consolidation cycle, surprise score, phase transition.
6. **형식 검증 부착 promotion** — Lean / Z3 / TLA+ 에 의한 구조적 불변량 검사를 LLM 평가 **이전** 에 삽입.
7. **llmesh / llove 패밀리 통합** — 산업 IoT 센서를 episodic memory 에 직결, TUI 로 HITL 을 완결.
8. **TRIZ 아이디어 발상을 내장** — 40 발명 원리 + 39×39 모순 매트릭스 + ARIZ + 9 화법을 mutation policy 로 구현하고, 메트릭 모순을 자동 검출 → 원리 매핑 → CandidateDiff 생성까지 자율 동작.

## 왜 커리어 관점에서 중요했는가

LLM 주변 기술은 진부화가 빨라, 표면적 캐치업만으로는 차별화하기 어려운 영역입니다. `llive` 를 만드는 과정에서 자신 안에 남은 것은 다음과 같은 **변호 가능한 설계 판단의 축적** 이었습니다.

- **지속 학습을 제품에 통합하는 어려움을, 책상 위가 아닌 구현 레벨에서 언어화할 수 있게** 되었다.
- **형식 검증 (Lean / Z3 / TLA+)** 을 LLM 평가 **전** 에 삽입함으로써, 평가 비용과 리스크를 낮추는 설계 패턴을 익혔다.
- **생물학적 메모리 모델을 CS 의 세계로 번역하는 작업** 을 통해, 여러 분야의 지식을 연결하는 능력이 단련되었다.
- **TRIZ 40 원리를 mutation policy** 에 녹여낸다는 「특허 세계의 지식」을 ML 에 도입하는 경험을 얻었다.
- **Ed25519 서명 + SHA-256 감사 체인** 을 지속 학습에 내장하는 설계를 경험하여, 규제 산업 AI 에 다가가기 위한 기초가 보였다.

이것들은 AI 스타트업에서도, 규제 산업의 AI 도입 팀에서도, 연구개발 팀에서도 요구되는 종류의 스킬입니다.

## 숫자로 보는 현재 위치 (2026-05-14)

- **v0.5.0** Phase 5 first wire-in 릴리스 — Rust kernel 을 핫패스에 접속.
- **444 tests / 0 lint** (v0.4.0 439 + RUST-03 parity 5).
- Z3 정적 검증 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Ed25519 Signed Adapter / SHA-256 Audit Chain 은 v0.3.0 에서 확립 완료.
- v0.4.0 에서 Rust acceleration skeleton (PyO3 0.22 + Cargo workspace + RUST-13 parity harness) 확립. v0.5.0 에서 `compute_surprise` (MEM-07) 를 Rust 경로로 자동 위임, 부재 시 numpy fallback, **1e-6 parity 보증**.
- [Unreleased]: F25 (g) `LoveBridge` writer — llive ↔ llmesh ↔ llove 를 MCP 경유로 잇는 shim 완성.
- PyPI: `pip install llmesh-llive`

## 어디로 향하는가

이 OSS 는 규제 산업 현장에서 AI 도입을 진행하고자 하는 엔지니어가 「구현 기반으로 논의할 수 있는 참조 구현」이 되는 것을 목표로 하고 있습니다. `llmesh` (온프레미스 MCP 허브) 와 `llove` (TUI dashboard) 를 조합하면, 클라우드를 사용하지 않고, 감사 증적을 남기고, 현장에서 관측 가능한 지속 학습 기반이 됩니다.

관심 있는 분은, 우선 PyPI 에서 만져 보세요. 설계 판단·실패·진화 과정을, 가능한 한 리포지토리와 docs 에 남기고 있습니다.

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #FormalVerification #OpenSource #개인개발 #커리어
