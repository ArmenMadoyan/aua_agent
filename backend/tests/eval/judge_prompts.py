"""Gemini judge prompt templates. Each prompt instructs Gemini to return strict JSON.

Score scale (all dimensions): 0 = worst, 5 = best.
"""

from __future__ import annotations

CITATION_ACCURACY_PROMPT = """You are an evaluator for an AUA policy RAG system.

User query:
{query}

Documents the RAG system retrieved (filenames it had access to):
{retrieved_sources}

Documents the answer is EXPECTED to cite (gold reference):
{expected_policies}

System answer:
{answer}

Task: Evaluate citation accuracy.
- Identify policy filenames cited inside the answer (look for filenames, "From: ...", bolded policy names, etc.).
- A citation is CORRECT if the cited filename appears in the expected list OR is clearly the right policy for the topic.
- A citation is INCORRECT if the file was not retrieved, or is irrelevant to what the answer says.
- Missing expected citations count against the score.

Score (0-5):
5 = all cited docs are correct and the answer cites most/all expected docs
4 = mostly correct citations, one missing or weak
3 = several correct, some missing or one incorrect
2 = few correct, many missing or several incorrect
1 = at most one correct, many missing
0 = no citations at all, or all citations are wrong

Return ONLY valid JSON of this shape (no markdown, no commentary):
{{"score": <int 0-5>, "cited_documents": [<filenames found in answer>], "correctly_cited": [<filenames>], "incorrectly_cited": [<filenames>], "missing_expected": [<filenames>], "explanation": "<one short sentence>"}}"""


TOP1_ACCURACY_PROMPT = """You are an evaluator for an AUA policy RAG system.

User query:
{query}

Top-1 retrieved chunk (the single highest-scoring chunk retrieved from the vector store):
Source: {top1_source}
Content:
{top1_content}

System answer:
{answer}

Task: Evaluate whether the answer correctly uses the top-1 retrieved chunk to address the query.
- If the top-1 chunk is highly relevant to the query and the answer faithfully reflects it: high score.
- If the top-1 chunk is relevant but the answer ignored it or misrepresented it: low score.
- If the top-1 chunk is irrelevant to the query (retrieval miss), but the answer still addresses the query well using other context: medium score (this is retrieval's fault, not the answer's).
- If the top-1 is irrelevant and the answer is also wrong: low score.

Score (0-5):
5 = top-1 was highly relevant AND answer faithfully uses it
4 = top-1 was relevant AND answer mostly reflects it
3 = top-1 weakly relevant, answer partially uses it
2 = top-1 relevant but answer ignored or contradicts it
1 = top-1 irrelevant; answer also poor
0 = top-1 irrelevant AND answer ignores it AND answer is wrong

Return ONLY valid JSON (no markdown):
{{"score": <int 0-5>, "top1_relevant_to_query": <true|false>, "answer_uses_top1_faithfully": <true|false>, "explanation": "<one short sentence>"}}"""


HALLUCINATION_PROMPT = """You are an evaluator for an AUA policy RAG system.

User query:
{query}

Retrieved chunks (all evidence the RAG system had access to):
{retrieved_chunks}

System answer:
{answer}

Task: Identify hallucinations — claims in the answer that are NOT supported by any retrieved chunk.
- Treat the retrieved chunks as the only allowed source of policy-specific facts.
- General knowledge statements ("AUA is a university in Yerevan") are NOT hallucinations.
- Specific factual claims about AUA policies, procedures, dollar amounts, deadlines, names of offices, etc. that are not in the retrieved chunks ARE hallucinations.
- Citing a policy filename that does NOT appear in the retrieved chunks is a hallucination.

Score (0-5) — higher means LESS hallucination:
5 = every specific claim is grounded in retrieved chunks
4 = one minor unsupported claim
3 = a few unsupported claims, but most are grounded
2 = many unsupported claims
1 = mostly unsupported
0 = answer is largely fabricated

Return ONLY valid JSON (no markdown):
{{"score": <int 0-5>, "hallucinated_claims": [<short string for each unsupported claim>], "explanation": "<one short sentence>"}}"""


COMPLETENESS_PROMPT = """You are an evaluator for an AUA policy RAG system.

User query (often multi-part):
{query}

Topics the answer is expected to address:
{expected_topics}

System answer:
{answer}

Task: Evaluate completeness — does the answer cover all expected topics?
- A topic is COVERED if the answer meaningfully addresses it (more than a passing mention).
- A topic is MISSED if absent or only mentioned without substance.

Score (0-5):
5 = all expected topics covered substantively
4 = almost all covered, one weakly addressed
3 = most covered, one or two missed
2 = half or fewer covered
1 = only one topic addressed
0 = no expected topics addressed

Return ONLY valid JSON (no markdown):
{{"score": <int 0-5>, "topics_covered": [<topics>], "topics_missed": [<topics>], "explanation": "<one short sentence>"}}"""


RELEVANCE_PROMPT = """You are an evaluator for an AUA policy RAG system.

User query:
{query}

System answer:
{answer}

Task: Evaluate whether the answer is directly relevant to the question asked. Ignore citation quality and factual accuracy — just relevance to the query intent.
- 5: answer is fully on-topic and directly addresses the question
- 4: on-topic but somewhat tangential in parts
- 3: partially relevant; significant off-topic content
- 2: mostly off-topic
- 1: barely related
- 0: completely irrelevant

Return ONLY valid JSON (no markdown):
{{"score": <int 0-5>, "explanation": "<one short sentence>"}}"""
