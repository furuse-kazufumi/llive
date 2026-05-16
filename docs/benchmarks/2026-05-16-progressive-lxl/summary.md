# llive progressive validation matrix

> on-prem only (Ollama). One Brief per cell, all flowing through
> the Brief API → FullSenseLoop pipeline (LLIVE-001 + LLIVE-002).

## Wall-time matrix (ms)

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 458400 | 1202282 |
| `qwen2.5:14b` | 1202263 | 1202199 |
| `qwen2.5:7b` | 722867 | 1202104 |


## LLM-only wall time (ms; loop overhead excluded)

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 458377 | 1202090 |
| `qwen2.5:14b` | 1202070 | 1202106 |
| `qwen2.5:7b` | 722848 | 1202054 |


## Loop decision

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | note | note |
| `qwen2.5:14b` | note | note |
| `qwen2.5:7b` | note | note |


## Salience score

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 0.7 | 0.7 |
| `qwen2.5:14b` | 0.7 | 0.7 |
| `qwen2.5:7b` | 0.7 | 0.7 |


## Curiosity score

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 1.0 | 1.0 |
| `qwen2.5:14b` | 1.0 | 1.0 |
| `qwen2.5:7b` | 1.0 | 1.0 |


## Thought text length (chars)

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 380 | 222 |
| `qwen2.5:14b` | 222 | 222 |
| `qwen2.5:7b` | 339 | 222 |


## Per-cell ledger entries

| model \ size | l | xl |
| --- | --- | --- |
| `llama3.2:latest` | 5 | 5 |
| `qwen2.5:14b` | 5 | 5 |
| `qwen2.5:7b` | 5 | 5 |
