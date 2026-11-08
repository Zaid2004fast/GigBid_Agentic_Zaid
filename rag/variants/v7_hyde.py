"""V7 HyDE: retrieve with a hypothetical ideal proposal for the job (LLM when available, taxonomy-based otherwise)."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V7", hyde=True)
