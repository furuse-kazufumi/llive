# llive アーキテクチャ図

> v0.2 で 6 層 → 8 層に再構成。Mermaid 図で各層・各パターン・各データフローを可視化。

## 1. 全体構成（8 層 + llmesh I/O bus）

```mermaid
flowchart TB
    subgraph L8["L8: llove HITL (TUI)"]
        direction LR
        L8A[Review Pane]
        L8B[Memory Viz]
        L8C[Candidate Arena]
    end

    subgraph L7["L7: Observability & Benchmark"]
        L7A[Tracing]
        L7B[Metrics]
        L7C[BenchmarkHarness]
    end

    subgraph L6["L6: Evolution Manager"]
        L6A[Proposal]
        L6B[Mutation]
        L6C[Static Verifier]
        L6D[Shadow Eval]
        L6E[Promote / Rollback]
    end

    subgraph L5["L5: Memory Fabric"]
        L5A[Semantic]
        L5B[Episodic]
        L5C[Structural]
        L5D[Parameter]
        L5E[Quarantine Zone]
    end

    subgraph L4["L4: Block Container Engine"]
        L4A[Container Registry]
        L4B[Sub-block Plugin Registry]
        L4C[Composer]
        L4D[Executor]
    end

    subgraph L3["L3: Core Model Adapter"]
        L3A[HF Adapter]
        L3B[vLLM Adapter]
        L3C[TGI Adapter]
    end

    subgraph L2["L2: Orchestration"]
        L2A[Pipeline]
        L2B[Router]
        L2C[Consolidation Scheduler]
    end

    subgraph L1["L1: Interface"]
        L1A[CLI]
        L1B[MCP]
        L1C[REST]
        L1D[Batch]
    end

    BUS[(llmesh I/O Bus<br/>MQTT / OPC-UA)]

    L1 --> L2
    L2 --> L3
    L2 --> L4
    L4 --> L3
    L2 --> L5
    L4 --> L5
    L6 --> L4
    L6 --> L5
    L6 -.candidate state.-> L8
    L5 -.events.-> L7
    L4 -.traces.-> L7
    L6 -.eval results.-> L7
    L7 --> L8
    L8 -.HITL commands.-> L6
    BUS <--> L5
    BUS <--> L8
```

## 2. 推論パイプライン（Pipes & Filters）

```mermaid
flowchart LR
    IN[Input] --> PP[Preprocess]
    PP --> RT[Memory Retrieval]
    RT --> RO[Router]
    RO --> BC{BlockContainer<br/>選択}
    BC -->|reasoning| C1[adaptive_reasoning_v1]
    BC -->|short context| C2[fast_path_v1]
    BC -->|long context| C3[memory_heavy_v1]
    C1 --> WR[Memory Write Gate]
    C2 --> WR
    C3 --> WR
    WR -->|surprise > θ| EP[(Episodic)]
    WR -->|否| OUT[Output]
    EP --> OUT
```

## 3. BlockContainer 内部（Composite + Chain of Responsibility）

```mermaid
flowchart TB
    subgraph BC["BlockContainer: adaptive_reasoning_v1"]
        direction TB
        S1[pre_norm] --> S2[causal_attention]
        S2 --> S3[memory_read<br/>top_k=8]
        S3 --> S4[cross_memory_attention]
        S4 --> S5[adapter<br/>task_conditioned]
        S5 --> S6[ffn_large]
        S6 --> S7[reflective_probe]
        S7 --> S8{surprise > θ?}
        S8 -->|yes| S9[memory_write]
        S8 -->|no| S10[residual]
        S9 --> S10
    end
```

## 4. Memory Fabric（CQRS + Event Sourcing）

```mermaid
flowchart LR
    subgraph WRITE["Write Path"]
        W1[Write Gate] --> W2[Surprise-Bayesian]
        W2 --> W3[Provenance Stamp]
        W3 --> W4[Zone Router]
        W4 -->|trusted| W5[(Main Zone)]
        W4 -->|untrusted| W6[(Quarantine Zone)]
    end

    subgraph READ["Read Path"]
        R1[Query] --> R2[Multi-layer Search]
        R2 --> R3{Cross-zone?}
        R3 -->|yes| R4[Signature Verify]
        R3 -->|no| R5[Direct Return]
        R4 --> R5
    end

    subgraph CONSOL["Consolidation Cycle"]
        C1[Episodic Stream] --> C2[Replay Selector]
        C2 --> C3[Summarize via LLM]
        C3 --> C4[Semantic Write]
        C3 --> C5[Structural Edge Update]
    end

    W5 --> R2
    W5 --> C1
```

## 5. Evolution Lifecycle（State + Saga）

```mermaid
stateDiagram-v2
    [*] --> draft: AI proposal
    draft --> proposed: schema validate
    proposed --> verifying: Static Verifier
    verifying --> rejected: refute
    verifying --> shadow_eval: prove or unprovable
    shadow_eval --> rejected: low score
    shadow_eval --> short_eval: top-N
    short_eval --> long_eval: pass
    long_eval --> hitl_review: pass
    hitl_review --> staging: approve
    hitl_review --> rejected: deny
    staging --> production: regression+forgetting pass
    staging --> rolled_back: forgetting detected
    production --> rolled_back: Reverse-Evolution Monitor
    rejected --> [*]
    rolled_back --> [*]
    production --> [*]: archived
```

## 6. llmesh / llove 統合フロー

```mermaid
sequenceDiagram
    participant Sensor as llmesh Sensor<br/>(MQTT/OPC-UA)
    participant Bus as llmesh I/O Bus
    participant Mem as Memory Fabric<br/>(L5)
    participant Evo as Evolution Manager<br/>(L6)
    participant TUI as llove HITL<br/>(L8)
    participant Op as Human Op

    Sensor->>Bus: sensor stream event
    Bus->>Mem: episodic write (FR-19)
    Mem->>Mem: surprise score (Bayesian)
    Mem->>Evo: trigger candidate proposal
    Evo->>Evo: AI generate diff
    Evo->>Evo: Static Verifier (FR-13)
    Evo->>Evo: Multi-precision shadow (FR-14)
    Evo->>TUI: surface top candidate
    TUI->>Op: render diff + score + viz
    Op->>TUI: approve / deny
    TUI->>Evo: Command(approve)
    Evo->>Mem: signed adapter publish (FR-18)
    Mem->>Bus: P2P distribute
    Bus->>Sensor: ack
```

## 7. パターン適用マップ（簡易）

```mermaid
mindmap
  root((llive))
    L1 Interface
      Facade
      Command
      CoR
    L2 Orchestration
      Pipes&Filters
      Mediator
    L3 CoreAdapter
      Adapter
      Proxy
    L4 Container
      Composite
      Strategy
      Builder
      Plugin
    L5 Memory
      Repository
      CQRS
      EventSourcing
      Proxy
    L6 Evolution
      Command
      Memento
      State
      Saga
    L7 Observability
      Decorator
      Observer
    L8 HITL
      MVVM
      Command
    Bus llmesh
      Adapter
      Bridge
      PubSub
```
