"""V3 cross-encoder reranking of hybrid candidates (precision at small k)."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V3", bm25=True, rerank=True)
