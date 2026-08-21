import asyncio, json
from pathlib import Path
from lhas.live_tools import ResumeReaderTool, WebFetchTool, WebSearchTool, SearchProvider
from lhas.tools.protocol import ToolRequest, ToolResult, ToolResultStatus
from lhas.job.live_pipeline import deduplicate_jobs, expiration_status, shortlist_record
from lhas import HARNESS_VERSION

def req(cap,args): return ToolRequest(tool_call_id="c",task_id="t",run_id="r",attempt_id="a",capability=cap,arguments=args)

def test_resume_reader_txt(tmp_path):
    p=tmp_path/"resume.md"; p.write_text("Alice\nAI Engineer",encoding="utf-8")
    result=asyncio.run(ResumeReaderTool().execute(req("document.resume.read",{"path":str(p)})))
    assert result.status == ToolResultStatus.SUCCESS and result.output["text"].startswith("Alice")

class Provider(SearchProvider):
    async def search(self,q,n): return [{"title":"x","url":"https://example.com/x","snippet":"s","source":"test"}]

def test_search_adapter_parsing():
    result=asyncio.run(WebSearchTool(Provider()).execute(req("web.search",{"query":"ai","max_results":5})))
    assert result.output["results"][0]["url"].startswith("https://")

def test_search_requires_provider_config(monkeypatch):
    monkeypatch.delenv("LHAS_SEARCH_ENDPOINT",raising=False); monkeypatch.delenv("LHAS_SEARCH_API_KEY",raising=False)
    result=asyncio.run(WebSearchTool().execute(req("web.search",{"query":"x"})))
    assert result.status == ToolResultStatus.FAILURE and "CONFIG" in result.error_type

def test_fetch_ssrf_guard():
    result=asyncio.run(WebFetchTool().execute(req("web.fetch",{"url":"http://127.0.0.1/"})))
    assert result.status == ToolResultStatus.FAILURE and result.error_type == "SSRF_BLOCKED"

def test_dedup_expiration_and_evidence():
    jobs=[{"company":"A","title":"X","source_url":"https://e.com/a/"},{"company":"A","title":"X","source_url":"https://e.com/a"}]
    rows,count=deduplicate_jobs(jobs); assert len(rows)==1 and count==1
    assert expiration_status({"status":"closed"}) == "expired"
    assert shortlist_record(rows[0])["evidence"][0]["source_url"]

def test_d2_harness_version():
    assert HARNESS_VERSION == "HV-0.5"
