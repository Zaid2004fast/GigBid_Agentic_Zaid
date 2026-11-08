"""V9 skill graph (GraphRAG-style): skills, projects, industries and outcomes as a graph fused with hybrid retrieval."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V9", bm25=True, graph=True)
