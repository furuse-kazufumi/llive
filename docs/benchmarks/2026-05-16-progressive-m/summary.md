# llive progressive validation matrix

> on-prem only (Ollama). One Brief per cell, all flowing through
> the Brief API → FullSenseLoop pipeline (LLIVE-001 + LLIVE-002).

## Wall-time matrix (ms)

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 89484 |
| `qwen2.5:14b` | 122160 |
| `qwen2.5:7b` | 122134 |


## LLM-only wall time (ms; loop overhead excluded)

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 89468 |
| `qwen2.5:14b` | 122112 |
| `qwen2.5:7b` | 122076 |


## Loop decision

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | note |
| `qwen2.5:14b` | note |
| `qwen2.5:7b` | note |


## Salience score

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 0.7 |
| `qwen2.5:14b` | 0.7 |
| `qwen2.5:7b` | 0.7 |


## Curiosity score

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 1.0 |
| `qwen2.5:14b` | 1.0 |
| `qwen2.5:7b` | 1.0 |


## Thought text length (chars)

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 334 |
| `qwen2.5:14b` | 222 |
| `qwen2.5:7b` | 222 |


## Per-cell ledger entries

| model \ size | m |
| --- | --- |
| `llama3.2:latest` | 5 |
| `qwen2.5:14b` | 5 |
| `qwen2.5:7b` | 5 |
