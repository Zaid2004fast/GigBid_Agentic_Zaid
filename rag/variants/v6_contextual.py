"""V6 contextual retrieval: a context line (project, industry, confirmed skills) prepended to each chunk."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V6", chunks="ctx", bm25=True)
