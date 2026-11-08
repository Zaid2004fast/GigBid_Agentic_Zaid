# My RAG pipeline kept quoting my sales pitches back to me

*Draft for LinkedIn / Medium (≈1,500 words). Edit it into your own voice before posting. Every number links to a results file in the repo.*

---

I spent the last two weeks building GigBid, a multi-agent copilot for freelancers. It reads job
posts, decides which are worth bidding on, and drafts proposals in which every claim has to be
backed by something in your portfolio. A human approves everything before it is sent.

The part I expected to be routine was retrieval: find the case study that proves you have done
"Celery background workers" or "dbt models". Embed the portfolio, embed the job, take the
nearest neighbours. That baseline is the first thing every tutorial builds.

It scored **0.001 Recall@5**. Not 0.1, but 0.001.

This post is about why, and about the less obvious thing I learned while fixing it: for this kind
of question, *structure beats similarity* by a margin that no amount of reranking closed.

## The setup

Every portfolio in the project has the messiness real portfolios have. The same project is
described three ways: a narrative case study, a terse CV bullet, and a GitHub repo whose README
sometimes says nothing more than "internal tooling for an ops team" while the code imports
Celery and Redis. Skills are often implied rather than named ("background workers that process
uploads off the request path"). And there are about 150 past proposals per freelancer, labelled
won, replied or ignored.

The evaluation set has 600 job posts across three personas (an ML engineer, a web developer, a
data analyst), with gold labels for which portfolio items prove each job's requirements. I
measured Recall@5, MRR and nDCG@10 for every variant on every job
([`rag_retrieval.json`](../../evals/results/rag_retrieval.json)).

## Finding 1: naive RAG retrieves what you *said*, not what you *did*

When I looked at what the baseline returned, the answer was obvious. Its top ten results were
almost entirely **past proposals**.

That makes sense once you see it. A job post and a proposal for a similar job are the most
similar documents in the corpus: same vocabulary, same structure, often the same phrases
copied back. A case study, written months later about what was actually built, sits much
further away in embedding space.

The problem is that a past proposal is not evidence. It is a sales pitch, and pitches inflate.
In this corpus, half of the past proposals contain an unspecific "I have extensive experience with
X and Y" line, and 6.7% name a skill that appears nowhere in the freelancer's actual work
([`proposal_audit.json`](../../evals/results/proposal_audit.json)). A writer grounded on
retrieved proposals will happily recycle those claims. The system meant to stop fabrication
becomes a laundering machine for it.

The control experiment was cheap: the same naive retriever with past proposals excluded from the
evidence index. Recall@5 went from **0.001 to 0.579**. Almost the entire failure was corpus
contamination, not chunking, the embedding model or the query.

The design rule I took from it: **outcome data and evidence are different things and belong in
different indexes.** GigBid still uses past proposals, but only as an *outcome signal* (which
projects were cited in proposals that won) and as tone exemplars, never as proof.

## Finding 2: the usual upgrades were smaller than I expected, and some were negative

With a clean evidence index, I tried the standard toolbox:

| Variant | Recall@5 | nDCG@10 |
|---|---|---|
| Naive dense, evidence only (V0e) | 0.579 | 0.434 |
| Requirement decomposition (V1) | 0.636 | 0.489 |
| Hybrid BM25 + dense, reciprocal rank fusion (V2) | 0.714 | 0.543 |
| + cross-encoder reranking (V3) | 0.712 | 0.538 |
| + outcome-aware boost (V4) | 0.716 | 0.543 |
| Multi-vector projects (V5) | 0.743 | 0.558 |
| Contextual chunk headers (V6) | 0.684 | 0.548 |
| HyDE-style query (V7) | 0.602 | 0.446 |

Hybrid retrieval was the one big, reliable step: library names like "dbt", "Celery" and
"Pinecone" are exactly what BM25 is good at and dense embeddings blur. Multi-vector indexing,
where README, code and summary are separate vectors returned as one project, helped the repos
whose README hides what the code proves.

But the cross-encoder reranker, the component every "advanced RAG" diagram includes, did
**nothing** for recall (0.712 vs 0.714) and added about five seconds per job on a CPU. Contextual
chunk headers and a HyDE-style query made things *worse*. Decomposing a job into one query per
requirement also lowered recall when fused naively, because "Python" counts as much as
"LangGraph" in a rank fusion even though one of them is in every project.

None of these are universal truths. A bigger reranker, an LLM-written HyDE document, or smarter
fusion weights might change the picture. But they are a useful corrective to adding components
because a diagram says so.

## Finding 3: structure beats similarity

The question a freelancer asks of their portfolio is not "what text is similar to this job
post?". It is "which of my projects proves I can do X, ideally for a client like this one?".
That is a structured question about skills, projects and industries.

So I built the boring thing: a small graph with skills, projects, client industries and outcomes
as nodes. A project→skill edge is weighted by how many independent sources confirm it (the case
study mentions it, the CV lists it, the code imports it). A job's requirements map to skill
nodes, and projects are ranked by weighted coverage.

| Variant | Recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| Skill graph alone (V9) | 0.926 | 0.970 | 0.783 |
| Hybrid + multi-vector + outcome + **graph** (shipped) | **0.933** | 0.968 | **0.802** |

That is a jump from roughly 0.74 to 0.93 Recall@5, larger than every similarity-based trick
combined, and it runs in under a tenth of a second.

There is an honest caveat, and it is the most interesting part. My gold labels are defined
by skill overlap, so a skill-structured retriever is structurally favoured by the metric. The
real question is whether better retrieval produces better proposals. That is why the project also
measures unsupported claims per proposal and simulated client reply rates end to end, not just
retrieval metrics. Retrieval gains do not translate one-for-one: the writer only cites two or
three projects, so going from "the right project is in the top 10" to "in the top 5" moves the
proposal much less than the jump from 0.001 to 0.58 did.

## What I would tell someone building their first RAG system

1. **Look at what your retriever returns before you tune it.** Ten minutes reading top-10 lists
   found a bug that no metric would have explained.
2. **Separate evidence from everything that merely resembles it.** Past outputs, drafts, FAQs and
   templates are near neighbours of your queries, and they are rarely ground truth.
3. **Measure every component you add, including the fashionable ones.** In this project the
   reranker and HyDE were negative results, and I am more confident in the system because I
   know that.
4. **If the question is structured, give the system the structure.** A forty-line skill graph
   beat every embedding trick I tried.
5. **Verify claims after generation anyway.** Even with near-perfect retrieval, a language model
   will occasionally say "I have five years of experience with Pinecone". GigBid splits every
   draft into claims, checks skills, numbers and industries against the cited item, and removes
   or rewrites what the portfolio cannot support, before a critic or a human ever sees it.

The code, evaluation scripts and results files are public: `<GitHub link>`. Every number in this
post is regenerated by one command.
