"""V0 naive dense: fixed chunks over every document (past proposals included), top-k cosine on the whole job post."""
from rag.pipeline import PipelineSpec

SPEC = PipelineSpec("V0", chunks="fixed_all", evidence_only=False)
