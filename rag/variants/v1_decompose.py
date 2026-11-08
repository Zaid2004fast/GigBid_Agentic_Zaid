"""V1 requirement decomposition: one dense retrieval per extracted requirement, merged with RRF."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V1", decompose=True)
