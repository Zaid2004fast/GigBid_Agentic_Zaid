"""V4 outcome-aware ranking: boost projects cited in proposals that won or got replies."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V4", bm25=True, outcome=True)
