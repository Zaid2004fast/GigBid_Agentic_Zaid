"""V5 multi-vector items: summary, README and code chunks indexed separately, returned as one project."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V5", bm25=True, multivector=True)
