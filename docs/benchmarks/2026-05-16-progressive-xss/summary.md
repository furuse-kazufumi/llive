# llive progressive validation matrix

> on-prem only (Ollama). One Brief per cell, all flowing through
> the Brief API → FullSenseLoop pipeline (LLIVE-001 + LLIVE-002).

## Wall-time matrix (ms)

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 8908 | 43978 |
| `qwen2.5:14b` | 121560 | 122160 |
| `qwen2.5:7b` | 59447 | 94158 |


## LLM-only wall time (ms; loop overhead excluded)

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 8894 | 43962 |
| `qwen2.5:14b` | 121526 | 122118 |
| `qwen2.5:7b` | 59419 | 94138 |


## Loop decision

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | note | note |
| `qwen2.5:14b` | note | note |
| `qwen2.5:7b` | note | note |


## Salience score

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 0.7 | 0.7 |
| `qwen2.5:14b` | 0.7 | 0.7 |
| `qwen2.5:7b` | 0.7 | 0.7 |


## Curiosity score

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 1.0 | 1.0 |
| `qwen2.5:14b` | 1.0 | 1.0 |
| `qwen2.5:7b` | 1.0 | 1.0 |


## Thought text length (chars)

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 494 | 331 |
| `qwen2.5:14b` | 425 | 222 |
| `qwen2.5:7b` | 328 | 457 |


## Per-cell ledger entries

| model \ size | xs | s |
| --- | --- | --- |
| `llama3.2:latest` | 5 | 5 |
| `qwen2.5:14b` | 5 | 5 |
| `qwen2.5:7b` | 5 | 5 |
