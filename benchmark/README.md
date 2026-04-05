# Model Benchmark Framework

Compare LLM models on real coding tasks within Claude Code's agentic workflow.

## Quick Start

```bash
# 1. Install dependencies (outside project venv)
pip install httpx pyyaml

# 2. Ensure API keys are in backend/.env:
#    ANTHROPIC_API_KEY=sk-ant-...
#    MINIMAX_API_KEY=...
#    GROQ_API_KEY=...

# 3. For Groq (optional): start LiteLLM proxy
pip install 'litellm[proxy]'
litellm --config benchmark/litellm-config.yaml --port 4000

# 4. Run a single task
python3 -m benchmark.harness --task benchmark/tasks/t1_001_example.yaml

# 5. Run all tasks
python3 -m benchmark.harness --batch benchmark/tasks/

# 6. Generate aggregate report
python3 -m benchmark.harness --report
```

## Models

| Model | Provider | API Format | Proxy? | Pricing (in/out per M) |
|---|---|---|---|---|
| Sonnet 4.6 | Anthropic | Native | No | $3.00 / $15.00 |
| MiniMax M2.5 | MiniMax | Anthropic-compatible | No | $0.30 / $1.20 |
| Qwen3-32B | Groq | OpenAI (via LiteLLM) | Yes | $0.29 / $0.59 |
| Opus 4.6 | Anthropic | Native (judge only) | No | $5.00 / $25.00 |

## Output

- `benchmark/results/all_runs.jsonl` — raw data (append-only)
- `benchmark/results/reports/*.md` — per-task reports
- `benchmark/results/reports/cto-decision-brief.md` — aggregate analysis
- `benchmark/results/reports/failure-analysis.md` — failure patterns
- `benchmark/results/reports/enterprise-readiness.md` — enterprise pitch

## Spec

Full specification: `docs/superpowers/specs/2026-04-05-model-benchmark-framework.md`
