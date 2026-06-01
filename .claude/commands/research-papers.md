Search PubMed for scientific literature relevant to this air quality / environmental health research query.

**Query:** $ARGUMENTS

Steps:

1. Construct a well-formed PubMed search query from the arguments. Include relevant MeSH terms where appropriate:
   - `"particulate matter"[MeSH]` for PM2.5/PM10 topics
   - `"air pollution"[MeSH]` for general pollution
   - `"mortality"[MeSH]` or `"cardiovascular diseases"[MeSH]` for health outcomes
   - Add geographic terms as free text (e.g. "India" OR "South Asia")
   - Limit to recent publications: add `AND ("2015"[PDAT] : "3000"[PDAT])`

2. Use `mcp__claude_ai_PubMed__search_articles` to run the query. Retrieve 10-15 results.

3. Use `mcp__claude_ai_PubMed__get_article_metadata` for each result to get title, authors, year, journal, and abstract snippet.

4. For the 3 most relevant papers, attempt `mcp__claude_ai_PubMed__get_full_text_article` to get the full abstract if available.

5. Return a structured table:

| PMID | Title | Authors | Year | Journal | Key Finding |
|------|-------|---------|------|---------|-------------|

Keep "Key Finding" to one sentence: the main quantitative result or conclusion.

6. After the table, write a 4-6 sentence synthesis:
   - What do these papers collectively say about the research question?
   - How do their findings relate to this project's datasets? (PM2.5 values in `openaq_daily.csv`, WHO exceedance flags in `openaq_monthly.csv`, country-level data)
   - Note any papers that used datasets directly comparable to this project (OpenAQ, IHME GBD, WHO GHO, World Bank) — these are methodological references for Phase 2.

Keep the response focused on actionable insights for an environmental health data analyst, not a comprehensive literature review.
