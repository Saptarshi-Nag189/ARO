"""
Web Search Tools
================
Real web search + content extraction for the Research Agent.

Sources (all free, no API keys):
  - DuckDuckGo — general web search
  - Wikipedia — factual summaries
  - Semantic Scholar — academic papers
  - arXiv — preprints
  - OpenAlex — open scholarly metadata
  - trafilatura — clean text extraction from URLs
"""

import logging
import time
import re
import ipaddress
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

logger = logging.getLogger("aro.web_search")

# ── Timeouts & Limits ────────────────────────────────────────────────────────

SEARCH_TIMEOUT = 12          # seconds per search call
FETCH_TIMEOUT = 10           # seconds per page fetch
MAX_CONTENT_CHARS = 3000     # max chars per page extract
MAX_RESULTS_PER_SOURCE = 3   # results per search engine per query
MAX_TOTAL_CONTEXT = 15000    # total chars injected into prompt

# SEC-005: SSRF protection — block requests to internal/private IPs
BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}


def _is_safe_url(url: str) -> bool:
    """Validate URL is not targeting internal/private networks (SSRF protection)."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return False
    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass  # it is a hostname, not an IP address
    return True


# ── DuckDuckGo ───────────────────────────────────────────────────────────────

def search_ddg(query: str, max_results: int = MAX_RESULTS_PER_SOURCE) -> List[Dict]:
    """Search DuckDuckGo and return results with titles, URLs, snippets."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results, safesearch="off"))
        results = []
        for r in raw:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", ""),
                "source_type": "web",
            })
        logger.info("DDG: %d results for '%s'", len(results), query[:60])
        return results
    except Exception as e:
        logger.warning("DDG search failed for '%s': %s", query[:60], e)
        return []


# ── Wikipedia ────────────────────────────────────────────────────────────────

def search_wikipedia(query: str, sentences: int = 4) -> List[Dict]:
    """Get Wikipedia summary for a query."""
    try:
        import wikipedia
        wikipedia.set_lang("en")
        results = []
        try:
            page = wikipedia.page(query, auto_suggest=True)
            summary = wikipedia.summary(query, sentences=sentences, auto_suggest=True)
            results.append({
                "title": f"Wikipedia: {page.title}",
                "url": page.url,
                "snippet": summary,
                "source_type": "encyclopedia",
            })
        except wikipedia.DisambiguationError as e:
            # Try first suggestion
            if e.options:
                try:
                    summary = wikipedia.summary(e.options[0], sentences=sentences)
                    results.append({
                        "title": f"Wikipedia: {e.options[0]}",
                        "url": f"https://en.wikipedia.org/wiki/{e.options[0].replace(' ', '_')}",
                        "snippet": summary,
                        "source_type": "encyclopedia",
                    })
                except Exception:
                    pass
        except wikipedia.PageError:
            pass
        logger.info("Wikipedia: %d results for '%s'", len(results), query[:60])
        return results
    except Exception as e:
        logger.warning("Wikipedia search failed: %s", e)
        return []


# ── Semantic Scholar ─────────────────────────────────────────────────────────

def search_semantic_scholar(query: str, max_results: int = MAX_RESULTS_PER_SOURCE) -> List[Dict]:
    """Search Semantic Scholar for academic papers (free, no API key)."""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,abstract,url,year,citationCount,authors",
        }
        resp = requests.get(url, params=params, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for paper in data.get("data", []):
            abstract = paper.get("abstract") or ""
            authors_list = paper.get("authors", [])
            author_names = ", ".join(a.get("name", "") for a in authors_list[:3])
            if len(authors_list) > 3:
                author_names += " et al."

            results.append({
                "title": f"[Paper] {paper.get('title', 'Untitled')}",
                "url": paper.get("url", ""),
                "snippet": (
                    f"Authors: {author_names}. "
                    f"Year: {paper.get('year', 'N/A')}. "
                    f"Citations: {paper.get('citationCount', 0)}. "
                    f"Abstract: {abstract[:500]}"
                ),
                "source_type": "academic_paper",
            })
        logger.info("Semantic Scholar: %d results for '%s'", len(results), query[:60])
        return results
    except Exception as e:
        logger.warning("Semantic Scholar search failed: %s", e)
        return []


# ── arXiv ────────────────────────────────────────────────────────────────────

def search_arxiv(query: str, max_results: int = MAX_RESULTS_PER_SOURCE) -> List[Dict]:
    """Search arXiv for preprints (free, no API key)."""
    try:
        # arXiv uses Atom/XML API
        search_query = re.sub(r'[^\w\s]', '', query)  # clean special chars
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{search_query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        resp = requests.get(url, params=params, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()

        # Parse XML (simple regex-based to avoid heavy XML dependency)
        entries = re.findall(r'<entry>(.*?)</entry>', resp.text, re.DOTALL)
        results = []
        for entry in entries:
            title_m = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
            summary_m = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
            link_m = re.search(r'<id>(.*?)</id>', entry)
            authors = re.findall(r'<name>(.*?)</name>', entry)
            published_m = re.search(r'<published>(.*?)</published>', entry)

            title = title_m.group(1).strip().replace('\n', ' ') if title_m else "Untitled"
            summary = summary_m.group(1).strip().replace('\n', ' ') if summary_m else ""
            link = link_m.group(1).strip() if link_m else ""
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            year = published_m.group(1)[:4] if published_m else "N/A"

            results.append({
                "title": f"[arXiv] {title}",
                "url": link,
                "snippet": (
                    f"Authors: {author_str}. Year: {year}. "
                    f"Abstract: {summary[:500]}"
                ),
                "source_type": "preprint",
            })
        logger.info("arXiv: %d results for '%s'", len(results), query[:60])
        return results
    except Exception as e:
        logger.warning("arXiv search failed: %s", e)
        return []


# ── OpenAlex ─────────────────────────────────────────────────────────────────

def search_openalex(query: str, max_results: int = MAX_RESULTS_PER_SOURCE) -> List[Dict]:
    """Search OpenAlex for scholarly works (free, no API key)."""
    try:
        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per_page": max_results,
            "select": "id,title,doi,publication_year,cited_by_count,authorships,abstract_inverted_index",
        }
        headers = {"User-Agent": "mailto:aro-research@example.com"}  # polite pool
        resp = requests.get(url, params=params, headers=headers, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for work in data.get("results", []):
            # Reconstruct abstract from inverted index
            abstract = ""
            aii = work.get("abstract_inverted_index")
            if aii and isinstance(aii, dict):
                positions = {}
                for word, indices in aii.items():
                    for idx in indices:
                        positions[idx] = word
                abstract = " ".join(positions[k] for k in sorted(positions.keys()))
                abstract = abstract[:500]

            authorships = work.get("authorships", [])
            author_names = ", ".join(
                a.get("author", {}).get("display_name", "") for a in authorships[:3]
            )
            if len(authorships) > 3:
                author_names += " et al."

            doi = work.get("doi") or ""
            work_url = doi if doi.startswith("http") else f"https://doi.org/{doi}" if doi else work.get("id", "")

            results.append({
                "title": f"[OpenAlex] {work.get('title', 'Untitled')}",
                "url": work_url,
                "snippet": (
                    f"Authors: {author_names}. "
                    f"Year: {work.get('publication_year', 'N/A')}. "
                    f"Citations: {work.get('cited_by_count', 0)}. "
                    f"Abstract: {abstract}"
                ),
                "source_type": "academic",
            })
        logger.info("OpenAlex: %d results for '%s'", len(results), query[:60])
        return results
    except Exception as e:
        logger.warning("OpenAlex search failed: %s", e)
        return []


# ── Content Extraction ───────────────────────────────────────────────────────

def fetch_page_content(url: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Fetch and extract clean text from a URL using trafilatura."""
    # SEC-005: Block SSRF to private/internal networks
    if not _is_safe_url(url):
        return ""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
        if text:
            return text[:max_chars]
        return ""
    except Exception as e:
        logger.debug("trafilatura failed for %s: %s", url, e)
        return ""


# ── Orchestration ────────────────────────────────────────────────────────────

def _search_single_query(query: str) -> List[Dict]:
    """Run all search engines for a single query in parallel."""
    all_results = []
    searchers = [
        ("ddg", lambda: search_ddg(query)),
        ("semantic_scholar", lambda: search_semantic_scholar(query)),
        ("arxiv", lambda: search_arxiv(query)),
        ("openalex", lambda: search_openalex(query)),
        ("wikipedia", lambda: search_wikipedia(query)),
    ]

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn): name for name, fn in searchers}
        for future in as_completed(futures, timeout=SEARCH_TIMEOUT + 5):
            name = futures[future]
            try:
                results = future.result(timeout=2)
                all_results.extend(results)
            except Exception as e:
                logger.debug("Search source '%s' timed out or failed: %s", name, e)

    return all_results


def _deduplicate_results(results: List[Dict]) -> List[Dict]:
    """Remove duplicate results based on URL."""
    seen_urls = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        unique.append(r)
    return unique


def run_web_research(sub_questions: list, objective: str = "") -> str:
    """
    Run web research for all sub-questions from the planner.
    Returns formatted text to inject into the research prompt.

    Args:
        sub_questions: List of sub-question objects from PlannerOutput
        objective: The main research objective for Wikipedia lookup
    """
    start = time.time()
    all_results = []

    # Build search queries from sub-questions
    queries = []
    for sq in sub_questions[:5]:  # limit to top 5 sub-questions
        q = sq.question if hasattr(sq, 'question') else str(sq)
        queries.append(q)

    # Also search the main objective
    if objective:
        queries.insert(0, objective)

    # Deduplicate queries
    seen = set()
    unique_queries = []
    for q in queries:
        q_lower = q.lower().strip()
        if q_lower not in seen:
            seen.add(q_lower)
            unique_queries.append(q)

    logger.info("Web research: %d queries", len(unique_queries))

    # Run searches in parallel across queries
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_search_single_query, q): q for q in unique_queries}
        for future in as_completed(futures, timeout=30):
            query = futures[future]
            try:
                results = future.result(timeout=5)
                for r in results:
                    r["query"] = query
                all_results.extend(results)
            except Exception as e:
                logger.debug("Query failed: %s — %s", query[:40], e)

    # Deduplicate
    all_results = _deduplicate_results(all_results)

    # Fetch full content for top web results (not academic — those have abstracts)
    web_results = [r for r in all_results if r.get("source_type") == "web"][:4]
    if web_results:
        with ThreadPoolExecutor(max_workers=4) as pool:
            fetch_futures = {pool.submit(fetch_page_content, r["url"]): r for r in web_results}
            for future in as_completed(fetch_futures, timeout=15):
                result = fetch_futures[future]
                try:
                    content = future.result(timeout=3)
                    if content and len(content) > 100:
                        result["full_content"] = content
                except Exception:
                    pass

    elapsed = time.time() - start
    logger.info("Web research completed: %d results in %.1fs", len(all_results), elapsed)

    # Format results for the LLM
    return _format_results(all_results)


def _format_results(results: List[Dict]) -> str:
    """Format search results as structured text for injection into the research prompt."""
    if not results:
        return "\n[No web search results found — rely on your training knowledge.]\n"

    sections = []
    sections.append("=" * 60)
    sections.append("REAL-TIME WEB RESEARCH RESULTS")
    sections.append("The following are REAL search results from the internet.")
    sections.append("Use these as primary sources. Do NOT hallucinate sources.")
    sections.append("=" * 60)

    total_chars = 0
    for i, r in enumerate(results):
        if total_chars >= MAX_TOTAL_CONTEXT:
            sections.append(f"\n[... {len(results) - i} more results truncated for brevity]")
            break

        entry = []
        entry.append(f"\n--- Source {i+1} [{r.get('source_type', 'web').upper()}] ---")
        entry.append(f"Title: {r.get('title', 'N/A')}")
        entry.append(f"URL: {r.get('url', 'N/A')}")
        if r.get("query"):
            entry.append(f"Query: {r['query'][:80]}")

        # Use full content if available, otherwise snippet
        content = r.get("full_content") or r.get("snippet", "")
        if content:
            entry.append(f"Content:\n{content[:MAX_CONTENT_CHARS]}")

        block = "\n".join(entry)
        total_chars += len(block)
        sections.append(block)

    sections.append("\n" + "=" * 60)
    sections.append(f"Total sources found: {len(results)}")
    sections.append("=" * 60)

    return "\n".join(sections)
