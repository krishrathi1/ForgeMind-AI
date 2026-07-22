# Sample Documents for Evaluation

These markdown files correspond to test questions in `../sample_dataset.json`.

## Usage

1. **Index documents** into ForgeMind (via WebUI, API, or Python)
2. **Run evaluation**: `python forgemind/evaluation/eval_rag_quality.py`
3. **Expected results**: ~91-100% RAGAS score per question

## Files

- `01_forgemind_overview.md` - ForgeMind framework and hallucination problem
- `02_rag_architecture.md` - RAG system components
- `03_forgemind_improvements.md` - ForgeMind vs traditional RAG
- `04_supported_databases.md` - Vector database support
- `05_evaluation_and_deployment.md` - Metrics and deployment

## Note

Documents use clear entity-relationship patterns for ForgeMind's default entity extraction prompts. For better results with your data, customize `forgemind/prompt.py`.
