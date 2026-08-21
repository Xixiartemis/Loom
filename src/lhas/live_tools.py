"""D2 real-tool adapters. Network access is explicit and provider-neutral."""
from __future__ import annotations
import hashlib, html, json, os, re, socket, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from lhas.planning.models import CapabilitySpec
from lhas.tools.protocol import ToolRequest, ToolResult, ToolResultStatus

def _fail(kind: str, message: str) -> ToolResult:
    return ToolResult(status=ToolResultStatus.FAILURE, error_type=kind, error_message=message)

class ResumeReaderTool:
    capability=CapabilitySpec(name="document.resume.read", description="Read PDF, DOCX, TXT or Markdown resume", input_schema={"path":"string"}, output_schema={"source_file":"string","text":"string","metadata":"object"})
    async def execute(self, request: ToolRequest) -> ToolResult:
        path=Path(str(request.arguments.get("path", "")))
        if not path.is_file(): return _fail("FILE_NOT_FOUND", str(path))
        try:
            suffix=path.suffix.lower()
            if suffix in {".txt", ".md", ".markdown"}: text=path.read_text(encoding="utf-8")
            elif suffix == ".docx":
                with ZipFile(path) as z:
                    raw=z.read("word/document.xml").decode("utf-8")
                text=" ".join(re.sub(r"<[^>]+>", " ", raw).split())
            elif suffix == ".pdf":
                raw=path.read_bytes()
                text="\n".join(x.decode("latin1", "ignore") for x in re.findall(rb"\(([^()]*)\)", raw))
                if not text.strip(): return _fail("EMPTY_CONTENT", "PDF contains no extractable text")
            else: return _fail("UNSUPPORTED_CONTENT", suffix)
            return ToolResult(status=ToolResultStatus.SUCCESS, output={"source_file":str(path),"text":text,"metadata":{"suffix":suffix,"size":path.stat().st_size}})
        except Exception as exc: return _fail("READ_ERROR", str(exc))

class SearchProvider:
    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]: raise NotImplementedError

class HttpSearchProvider(SearchProvider):
    async def search(self, query, max_results):
        endpoint=os.getenv("LHAS_SEARCH_ENDPOINT"); key=os.getenv("LHAS_SEARCH_API_KEY")
        if not endpoint or not key: raise RuntimeError("SEARCH_PROVIDER_NOT_CONFIGURED: set LHAS_SEARCH_ENDPOINT and LHAS_SEARCH_API_KEY")
        url=endpoint+(("&" if "?" in endpoint else "?")+urllib.parse.urlencode({"q":query,"max_results":max_results}))
        req=urllib.request.Request(url,headers={"Authorization":f"Bearer {key}","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=15) as resp: payload=json.loads(resp.read().decode("utf-8"))
        rows=payload.get("results", payload if isinstance(payload,list) else [])
        return [{"title":str(x.get("title","")),"url":str(x.get("url",x.get("link",""))),"snippet":str(x.get("snippet","")),"source":str(x.get("source",endpoint))} for x in rows[:max_results]]

class WebSearchTool:
    capability=CapabilitySpec(name="web.search",description="Search web through configured provider",input_schema={"query":"string","max_results":"integer"},output_schema={"results":"array"})
    def __init__(self, provider: SearchProvider|None=None): self.provider=provider or HttpSearchProvider()
    async def execute(self, request):
        try:
            q=str(request.arguments.get("query", "")); n=min(int(request.arguments.get("max_results",10)),20)
            if not q: return _fail("INVALID_INPUT","query is required")
            rows=await self.provider.search(q,n)
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"results":rows},usage={"result_count":len(rows)})
        except Exception as exc: return _fail("SEARCH_CONFIG_ERROR" if "NOT_CONFIGURED" in str(exc) else "NETWORK_ERROR",str(exc))

def _safe_url(raw: str) -> str:
    p=urllib.parse.urlparse(raw)
    if p.scheme not in {"http","https"} or not p.hostname: raise ValueError("UNSUPPORTED_URL")
    host=p.hostname.lower()
    if host in {"localhost","metadata.google.internal"} or host.startswith("127.") or host.startswith("0.") or host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254.") or host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31: raise ValueError("SSRF_BLOCKED")
    try:
        ip=socket.gethostbyname(host)
        if ip.startswith(("127.","10.","192.168.","169.254.")): raise ValueError("SSRF_BLOCKED")
    except socket.gaierror: pass
    return raw

class WebFetchTool:
    capability=CapabilitySpec(name="web.fetch",description="Fetch bounded HTTP content",input_schema={"url":"string"},output_schema={"url":"string","status_code":"integer","title":"string","text":"string"})
    def __init__(self,max_bytes=1_000_000,timeout=15): self.max_bytes,self.timeout=max_bytes,timeout
    async def execute(self, request):
        if not request.arguments.get("url"):
            search=request.context.get("steps",{}).get("web.search",{}).get("output",{})
            urls=[x.get("url") for x in (search.get("results",[]) if isinstance(search,dict) else []) if x.get("url")][:10]
            fetched=[]
            for url in urls:
                one=await self.execute(ToolRequest(**request.model_dump(exclude={"arguments"}),arguments={"url":url}))
                if one.status == ToolResultStatus.SUCCESS: fetched.append(one.output)
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"results":fetched},usage={"fetched_count":len(fetched)})
        try: url=_safe_url(str(request.arguments.get("url","")))
        except ValueError as exc: return _fail(str(exc),str(exc))
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"LHAS-D2/0.1","Accept":"text/html,text/plain,application/pdf"})
            with urllib.request.urlopen(req,timeout=self.timeout) as resp:
                code=resp.status; ctype=resp.headers.get("Content-Type","")
                if not any(x in ctype.lower() for x in ("text/", "json", "html", "xml", "pdf")): return _fail("UNSUPPORTED_CONTENT",ctype)
                body=resp.read(self.max_bytes+1)
                if len(body)>self.max_bytes: body=body[:self.max_bytes]
            text=html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>"," ",body.decode("utf-8","replace"),flags=re.I|re.S)).strip()
            if not text: return _fail("EMPTY_CONTENT",url)
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"url":url,"status_code":code,"title":text[:200].splitlines()[0],"text":text,"captured_at":datetime.now(timezone.utc).isoformat(),"content_hash":hashlib.sha256(body).hexdigest()})
        except urllib.error.HTTPError as exc: return _fail("HTTP_4XX" if exc.code<500 else "HTTP_5XX",str(exc))
        except TimeoutError: return _fail("TIMEOUT",url)
        except urllib.error.URLError as exc: return _fail("NETWORK_ERROR",str(exc))
        except Exception as exc: return _fail("NETWORK_ERROR",str(exc))

class JobParseTool:
    capability=CapabilitySpec(name="job.parse",description="Parse fetched job content")
    async def execute(self,request):
        data=request.arguments.get("content", request.context.get("last_fetch",{}))
        if not data:
            step_values=list(request.context.get("steps",{}).values()); data=step_values[-1].get("output",{}) if step_values else {}
        if isinstance(data,dict) and "results" in data: data=(data["results"] or [{}])[0]
        text=data.get("text","") if isinstance(data,dict) else str(data)
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"company":"unknown","title":(text.splitlines()[0] if text else "unknown"),"description":text,"source_url":data.get("url","") if isinstance(data,dict) else ""})

class JobMatchTool:
    capability=CapabilitySpec(name="job.match",description="Match parsed job to resume")
    async def execute(self,request): return ToolResult(status=ToolResultStatus.SUCCESS,output={"classification":"unknown","match_score":0,"fit_reasons":[],"risks":[]})

class JobRankTool:
    capability=CapabilitySpec(name="job.rank",description="Rank job candidates")
    async def execute(self,request): return ToolResult(status=ToolResultStatus.SUCCESS,output=request.arguments.get("jobs",request.context.get("steps",{})))

class ShortlistArtifactTool:
    capability=CapabilitySpec(name="artifact.write",description="Write shortlist artifacts")
    async def execute(self,request):
        root=Path(str(request.arguments.get("output_dir","artifacts")))/request.task_id; root.mkdir(parents=True,exist_ok=True)
        data=request.arguments.get("shortlist",request.context.get("steps",{})); (root/"shortlist.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); (root/"shortlist.md").write_text("# Shortlist\n\n"+json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"artifact_path":str(root)})

def build_live_registry():
    from lhas.tools.registry import ToolRegistry
    r=ToolRegistry()
    for tool in (ResumeReaderTool(),WebSearchTool(),WebFetchTool(),JobParseTool(),JobMatchTool(),JobRankTool(),ShortlistArtifactTool()): r.register(tool)
    return r
