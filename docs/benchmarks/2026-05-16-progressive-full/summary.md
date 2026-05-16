# llive progressive validation matrix

> on-prem only (Ollama). One Brief per cell, all flowing through
> the Brief API → FullSenseLoop pipeline (LLIVE-001 + LLIVE-002).

## Wall-time matrix (ms)

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 8908 | 43978 | 89484 | 458400 | 1202282 |
| `qwen2.5:14b` | 121560 | 122160 | 122160 | 1202263 | 1202199 |
| `qwen2.5:7b` | 59447 | 94158 | 122134 | 722867 | 1202104 |


## LLM-only wall time (ms; loop overhead excluded)

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 8894 | 43962 | 89468 | 458377 | 1202090 |
| `qwen2.5:14b` | 121526 | 122118 | 122112 | 1202070 | 1202106 |
| `qwen2.5:7b` | 59419 | 94138 | 122076 | 722848 | 1202054 |


## Loop decision

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | note | note | note | note | note |
| `qwen2.5:14b` | note | note | note | note | note |
| `qwen2.5:7b` | note | note | note | note | note |


## Salience score

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 0.7 | 0.7 | 0.7 | 0.7 | 0.7 |
| `qwen2.5:14b` | 0.7 | 0.7 | 0.7 | 0.7 | 0.7 |
| `qwen2.5:7b` | 0.7 | 0.7 | 0.7 | 0.7 | 0.7 |


## Curiosity score

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| `qwen2.5:14b` | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| `qwen2.5:7b` | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |


## Thought text length (chars)

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 494 | 331 | 334 | 380 | 222 |
| `qwen2.5:14b` | 425 | 222 | 222 | 222 | 222 |
| `qwen2.5:7b` | 328 | 457 | 222 | 339 | 222 |


## Per-cell ledger entries

| model \ size | xs | s | m | l | xl |
| --- | --- | --- | --- | --- | --- |
| `llama3.2:latest` | 5 | 5 | 5 | 5 | 5 |
| `qwen2.5:14b` | 5 | 5 | 5 | 5 | 5 |
| `qwen2.5:7b` | 5 | 5 | 5 | 5 | 5 |
