"""V2 hybrid: BM25 + dense fused with reciprocal rank fusion (exact library names that embeddings blur)."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V2", bm25=True)
