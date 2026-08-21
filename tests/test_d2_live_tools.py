import asyncio, json
from pathlib import Path
from lhas.live_tools import ResumeReaderTool, WebFetchTool, WebSearchTool, SearchProvider, TavilySearchProvider
import lhas.live_tools as live_tools
import urllib.error
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

def test_tavily_post_headers_body(monkeypatch):
    captured={}
    class Resp:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return b'{"results":[{"title":"T","url":"https://e","content":"evidence","score":0.9}]}'
    def fake(req,timeout):
        captured.update(method=req.method,headers=dict(req.header_items()),body=json.loads(req.data.decode()))
        return Resp()
    monkeypatch.setenv("LHAS_SEARCH_API_KEY","secret-value"); monkeypatch.setattr(live_tools.urllib.request,"urlopen",fake)
    result=asyncio.run(WebSearchTool(TavilySearchProvider()).execute(req("web.search",{"query":"q","max_results":3})))
    assert captured["method"] == "POST" and captured["body"] == {"query":"q","max_results":3}
    assert captured["headers"]["Authorization"] == "Bearer secret-value" and captured["headers"]["Content-type"] == "application/json"
    assert result.output["results"][0]["snippet"] == "evidence" and result.output["results"][0]["score"] == 0.9

def test_tavily_error_classification(monkeypatch):
    class E:
        def __init__(self,code): self.code=code
    for code,expected in ((401,"AUTH_ERROR"),(429,"RATE_LIMIT"),(500,"UPSTREAM_5XX")):
        def fake(req,timeout,code=code): raise urllib.error.HTTPError("https://e",code,"x",{},None)
        monkeypatch.setenv("LHAS_SEARCH_API_KEY","x"); monkeypatch.setattr(live_tools.urllib.request,"urlopen",fake)
        result=asyncio.run(WebSearchTool(TavilySearchProvider()).execute(req("web.search",{"query":"q"})))
        assert result.error_type == expected

def test_tavily_invalid_json(monkeypatch):
    class Resp:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return b"not-json"
    monkeypatch.setenv("LHAS_SEARCH_API_KEY","x"); monkeypatch.setattr(live_tools.urllib.request,"urlopen",lambda *a,**k: Resp())
    result=asyncio.run(WebSearchTool(TavilySearchProvider()).execute(req("web.search",{"query":"q"})))
    assert result.error_type == "INVALID_RESPONSE"

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
