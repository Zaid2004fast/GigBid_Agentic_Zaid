# My RAG pipeline kept quoting my sales pitches back to me

### What building a freelancer copilot taught me about retrieval, measurement and trusting AI judges

I spent the last two weeks building GigBid, a multi-agent copilot for freelancers. It reads job posts, decides which ones are worth bidding on, and drafts proposals in which every claim has to be backed by something real in the freelancer's portfolio. A human approves everything before it is sent.

The part I expected to be routine was retrieval: find the case study that proves you have done "Celery background workers" or "dbt models". Embed the portfolio, embed the job, take the nearest neighbours. That baseline is the first thing every tutorial builds.

It scored **0.001 Recall@5**. Not 0.1. Zero point zero zero one.

This post is about why, and about three less obvious things I learned while fixing it: structure beats similarity, better retrieval does not automatically mean better outcomes, and an AI judge can be confidently wrong.

## The setup

The portfolios in this project are deliberately messy, like real ones. The same project is described three ways: a narrative case study, a terse CV bullet, and a GitHub repo whose README sometimes says nothing more than "internal tooling for an ops team" while the code imports Celery and Redis. Skills are often implied rather than named ("background workers that process uploads"). And each freelancer has about 150 past proposals, labelled won, replied or ignored.

The test set has 600 job posts across three freelancer types (an ML engineer, a web developer and a data analyst), with labels saying which portfolio items prove each job's requirements. I measured every retrieval design on every job. All results are in the public repo: [rag_retrieval.json](https://github.com/Zaid2004fast/GigBid_Agentic_Zaid/blob/main/evals/results/rag_retrieval.json).

## Finding 1: naive RAG retrieves what you *said*, not what you *did*

When I looked at what the baseline returned, the answer was obvious. Its top ten results were almost entirely **past proposals**.

It makes sense once you see it. A job post and a proposal for a similar job are the most similar documents in the corpus: same vocabulary, same structure, often the same phrases copied back. A case study, written months later about what was actually built, sits much further away.

The problem is that a past proposal is not evidence. It is a sales pitch, and pitches inflate. Half of the past proposals in this corpus contain a vague "I have extensive experience with X and Y" line ([proposal_audit.json](https://github.com/Zaid2004fast/GigBid_Agentic_Zaid/blob/main/evals/results/proposal_audit.json)). A writer grounded on retrieved proposals happily recycles those claims. The system meant to stop fabrication becomes a laundering machine for it. End to end, drafts built on naive retrieval averaged almost **two unsupported claims each** before verification.

The control experiment was cheap: the same naive retriever with past proposals removed from the evidence index. Recall@5 jumped from **0.001 to 0.579**. Almost the whole failure was contamination of the index, not the chunking, the embedding model or the query.

The rule I took from it: **outcome data and evidence are different things and belong in different indexes.** GigBid still uses past proposals, but only as a signal of what worked, never as proof.

## Finding 2: the fashionable upgrades were small, and some were negative

With a clean index, I tried the standard "advanced RAG" toolbox. Recall@5 for each:

- Basic meaning-based search, clean index: **0.579**
- One search per requirement: **0.636**
- Keyword (BM25) + meaning search combined: **0.714**
- The same plus a cross-encoder re-ranker: **0.712**
- Boosting projects that won before: **0.716**
- Treating a project's README, code and summary as one item: **0.743**
- Adding a context line to every chunk: **0.684**
- Searching with an imagined ideal proposal (HyDE-style): **0.602**

Combining keyword and meaning search was the one big, reliable step. Library names like "dbt", "Celery" and "Pinecone" are exactly what keyword search is good at and what embeddings blur.

But the re-ranker, the component every advanced-RAG diagram includes, did **nothing** for recall and cost about five seconds per job on a CPU. Context lines and the HyDE-style query made things *worse*. And when I stacked every fashionable technique together, the way I would have built it without measuring, it scored **0.781**: far below what I eventually shipped, and about 280 times slower.

None of these are universal truths. A bigger re-ranker or smarter fusion might change the picture. But they are a useful corrective to adding components because a diagram says so.

## Finding 3: structure beats similarity

The question a freelancer asks of their portfolio is not "what text is similar to this job post?". It is "which of my projects proves I can do X, ideally for a client like this one?". That is a structured question about skills, projects and industries.

So I built the boring thing: a small graph of skills, projects, client industries and outcomes. A project-to-skill link gets stronger with every independent source that confirms it: the case study mentions it, the CV lists it, the code imports it. A job's requirements map to skills, and projects are ranked by how well they cover them.

The skill graph alone reached **0.926 Recall@5**. Then came a surprise. When I removed components one at a time, taking *out* the meaning-based search **improved** the result. The embeddings were already doing their semantic work inside the skill extractor that feeds the graph, and a separate similarity ranking only added noise. The shipped design (keywords, skill graph, project-level items and a small boost for past wins) scores **0.949 Recall@5** and answers in about 20 milliseconds.

I kept keyword search even though removing it scored a hair higher. **27% of real requirements** ("make the app faster") name no skill at all, and a graph-only retriever returns nothing for them. The metric could not see that; reading the requirements could.

That points at the honest caveat. My correct answers are defined by skills, so a skill-based retriever is naturally favoured by the metric. Which leads to the most important lesson.

## Finding 4: better retrieval did not mean more replies

GigBid runs against a marketplace simulator whose clients reply more often to proposals that are specific, cover their must-have skills and are fairly priced. So I could measure the outcome that actually matters.

Bad retrieval clearly hurt: the naive version earned a **51%** reply rate. But from plain keyword-plus-meaning search upwards, the reply rate was flat: **72%** for that version, **71%** for the shipped one, even though Recall@5 rose from 0.71 to 0.95.

The reason is simple once you look at a proposal. The writer cites only two or three projects, and the simpler search already finds good ones. Ranking the very best project first changes *which* proof is cited, not *whether* there is proof. I still ship the graph, because it gives the freelancer a more accurate evidence list, but I no longer pretend it wins more work.

## Finding 5: my AI judge was confidently wrong

To score proposal quality, I built an AI judge that grades proposals from 1 to 5. Before trusting it, I scored 30 proposals by hand.

The judge did not agree with me at all. Its agreement was at chance level (Cohen's kappa of −0.03), and a much larger model as judge did no better. Both were far more generous: my average was **2.8**, the small judge's **4.0**, the large judge's **4.7**. The judges rewarded proposals for ticking the rubric's boxes (evidence cited, honest about a gap, ends with a question), while I marked down the awkward, template-like wording they ignored.

So no result in the project relies on the AI judge. Quality is measured by unsupported claims, simulated client replies, and a blind panel where three classmates preferred GigBid's proposals over a careless baseline in **90%** of 63 votes.

## What I would tell someone building their first RAG system

1. **Look at what your retriever returns before tuning it.** Ten minutes reading top-10 lists found a problem no metric would have explained.
2. **Separate evidence from everything that merely resembles it.** Past outputs, drafts and templates are near neighbours of your queries, and they are rarely ground truth.
3. **Measure every component, including the fashionable ones.** My re-ranker and HyDE were negative results, and the "everything stacked" design was the worst of the good ones.
4. **If the question is structured, give the system the structure.** A small skill graph beat every embedding trick I tried.
5. **Measure the outcome, not just the proxy.** Retrieval went from 0.71 to 0.95 and replies did not move.
6. **Check your AI judge against a human before trusting it.** Mine looked authoritative and was no better than a coin.

The code, evaluation scripts and every results file are public: [github.com/Zaid2004fast/GigBid_Agentic_Zaid](https://github.com/Zaid2004fast/GigBid_Agentic_Zaid). Every number in this post can be regenerated with one command.
