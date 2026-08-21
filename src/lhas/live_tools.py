"""D2 real-tool adapters. Network access is explicit and provider-neutral."""
from __future__ import annotations
import hashlib, html, ipaddress, json, os, re, socket, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from lhas.planning.models import CapabilitySpec
from lhas.tools.protocol import ToolRequest, ToolResult, ToolResultStatus

def _fail(kind: str, message: str) -> ToolResult:
    return ToolResult(status=ToolResultStatus.FAILURE, error_type=kind, error_message=message)

def find_step_record(context: dict[str, Any], capability: str) -> dict[str, Any] | None:
    for record in context.get("steps", {}).values():
        if isinstance(record, dict) and record.get("capability") == capability: return record
    return None

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
                try: from pypdf import PdfReader
                except ImportError: return _fail("PDF_DEPENDENCY_MISSING", "install with --extra live")
                text="\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
                if not text.strip(): return _fail("EMPTY_CONTENT", "PDF contains no extractable text")
                if len(text.strip()) < 8: return _fail("EMPTY_CONTENT", "PDF text quality too low")
            else: return _fail("UNSUPPORTED_CONTENT", suffix)
            return ToolResult(status=ToolResultStatus.SUCCESS, output={"source_file":str(path),"text":text,"metadata":{"suffix":suffix,"size":path.stat().st_size}})
        except Exception as exc: return _fail("READ_ERROR", str(exc))

class SearchProvider:
    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]: raise NotImplementedError

class TavilySearchProvider(SearchProvider):
    async def search(self, query, max_results):
        endpoint=os.getenv("LHAS_SEARCH_ENDPOINT", "https://api.tavily.com/search"); key=os.getenv("LHAS_SEARCH_API_KEY")
        if not key: raise RuntimeError("SEARCH_PROVIDER_NOT_CONFIGURED")
        body=json.dumps({"query":query,"max_results":max_results}).encode("utf-8")
        req=urllib.request.Request(endpoint,data=body,method="POST",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","Accept":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=15) as resp: payload=json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403): raise RuntimeError("AUTH_ERROR")
            if exc.code == 429: raise RuntimeError("RATE_LIMIT")
            if exc.code >= 500: raise RuntimeError("UPSTREAM_5XX")
            raise RuntimeError("NETWORK_ERROR")
        except TimeoutError: raise RuntimeError("TIMEOUT")
        except urllib.error.URLError: raise RuntimeError("NETWORK_ERROR")
        except json.JSONDecodeError: raise RuntimeError("INVALID_RESPONSE")
        if not isinstance(payload,dict) or not isinstance(payload.get("results"),list): raise RuntimeError("INVALID_RESPONSE")
        rows=payload["results"]
        return [{"title":str(x.get("title","")),"url":str(x.get("url","")),"snippet":str(x.get("content",x.get("snippet",""))),"source":"tavily","score":x.get("score")} for x in rows[:max_results] if isinstance(x,dict)]

class HttpSearchProvider(TavilySearchProvider):
    """Backward-compatible name for the default Tavily HTTP adapter."""

class WebSearchTool:
    capability=CapabilitySpec(name="web.search",description="Search web through configured provider",input_schema={"query":"string","max_results":"integer"},output_schema={"results":"array"})
    def __init__(self, provider: SearchProvider|None=None): self.provider=provider or HttpSearchProvider()
    async def execute(self, request):
        try:
            q=str(request.arguments.get("query", "")); n=min(int(request.arguments.get("max_results",10)),20)
            if not q: return _fail("INVALID_INPUT","query is required")
            rows=await self.provider.search(q,n)
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"results":rows},usage={"result_count":len(rows)})
        except Exception as exc:
            kind=str(exc).split(":",1)[0]
            if kind == "SEARCH_PROVIDER_NOT_CONFIGURED": return _fail(kind,kind)
            if kind in {"AUTH_ERROR","RATE_LIMIT","UPSTREAM_5XX","TIMEOUT","NETWORK_ERROR","INVALID_RESPONSE"}: return _fail(kind,kind)
            return _fail("NETWORK_ERROR","search provider failure")

def _safe_url(raw: str) -> str:
    p=urllib.parse.urlparse(raw)
    if p.scheme not in {"http","https"} or not p.hostname: raise ValueError("UNSUPPORTED_URL")
    host=p.hostname.lower()
    if host in {"localhost","metadata.google.internal"} or host.startswith("127.") or host.startswith("0.") or host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254.") or host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31: raise ValueError("SSRF_BLOCKED")
    def check(ip):
        addr=ipaddress.ip_address(ip)
        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified: raise ValueError("SSRF_BLOCKED")
    try:
        for info in socket.getaddrinfo(host,None): check(info[4][0])
    except socket.gaierror: pass
    return raw

class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class WebFetchTool:
    capability=CapabilitySpec(name="web.fetch",description="Fetch bounded HTTP content",input_schema={"url":"string"},output_schema={"url":"string","status_code":"integer","title":"string","text":"string"})
    def __init__(self,max_bytes=1_000_000,timeout=15): self.max_bytes,self.timeout=max_bytes,timeout
    async def execute(self, request):
        if not request.arguments.get("url"):
            search=(find_step_record(request.context,"web.search") or {}).get("output",{})
            results=search.get("results",[]) if isinstance(search,dict) else []
            if not results: return _fail("NO_SEARCH_RESULTS","web.search returned no results")
            urls=[x.get("url") for x in results if isinstance(x,dict) and x.get("url")][:10]
            if not urls: return _fail("NO_FETCHABLE_URLS","search results contained no valid URLs")
            fetched=[]
            failures=[]
            for url in urls:
                one=await self.execute(ToolRequest(**request.model_dump(exclude={"arguments"}),arguments={"url":url}))
                meta=next((x for x in results if x.get("url")==url),{})
                if one.status == ToolResultStatus.SUCCESS:
                    fetched.append({**one.output,"search_title":meta.get("title",""),"search_snippet":meta.get("snippet",""),"search_score":meta.get("score")})
                else: failures.append({"url":url,"error_type":one.error_type,"error_message":one.error_message})
            if not fetched: return _fail("FETCH_ALL_FAILED",json.dumps({"failures":failures}))
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"results":fetched,"failures":failures},usage={"fetched_count":len(fetched),"failed_count":len(failures)})
        try: url=_safe_url(str(request.arguments.get("url","")))
        except ValueError as exc: return _fail(str(exc),str(exc))
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"LHAS-D2/0.1","Accept":"text/html,text/plain,application/pdf"})
            opener=urllib.request.build_opener(_SafeRedirect)
            with opener.open(req,timeout=self.timeout) as resp:
                _safe_url(resp.geturl() if hasattr(resp,"geturl") else url)
                code=resp.status; ctype=resp.headers.get("Content-Type","")
                if not any(x in ctype.lower() for x in ("text/", "json", "html", "xml", "pdf")): return _fail("UNSUPPORTED_CONTENT",ctype)
                body=resp.read(self.max_bytes+1)
                if len(body)>self.max_bytes: body=body[:self.max_bytes]
            text=html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>"," ",body.decode("utf-8","replace"),flags=re.I|re.S)).strip()
            if not text: return _fail("EMPTY_CONTENT",url)
            return ToolResult(status=ToolResultStatus.SUCCESS,output={"url":url,"status_code":code,"title":text[:200].splitlines()[0],"text":text,"captured_at":datetime.now(timezone.utc).isoformat(),"content_hash":hashlib.sha256(body).hexdigest()})
        except ValueError as exc: return _fail("SSRF_BLOCKED",str(exc))
        except urllib.error.HTTPError as exc: return _fail("HTTP_4XX" if exc.code<500 else "HTTP_5XX",str(exc))
        except (TimeoutError, socket.timeout): return _fail("TIMEOUT",url)
        except urllib.error.URLError as exc: return _fail("NETWORK_ERROR",str(exc))
        except Exception as exc: return _fail("NETWORK_ERROR",str(exc))

class JobParseTool:
    capability=CapabilitySpec(name="job.parse",description="Parse fetched job content")
    async def execute(self,request):
        data=request.arguments.get("content") or (find_step_record(request.context,"web.fetch") or {}).get("output",{})
        rows=data.get("results",[]) if isinstance(data,dict) else []
        jobs=[]
        for item in rows:
            text=item.get("text",""); lines=[x.strip() for x in text.splitlines() if x.strip()]
            title=item.get("search_title") or item.get("title") or (lines[0] if lines else "unknown")
            host=urllib.parse.urlparse(item.get("url","")).hostname or "unknown"
            jobs.append({"job_id":hashlib.sha1(item.get("url",host).encode()).hexdigest()[:12],"company":host,"title":title,"location":"unknown","source_url":item.get("url",""),"jd_text":text,"content_hash":item.get("content_hash",""),"status":"unknown","requirements":[],"responsibilities":[],"search_snippet":item.get("search_snippet",""),"page_title":item.get("title","")})
        from lhas.job.live_pipeline import deduplicate_jobs, expiration_status
        jobs, duplicate_count=deduplicate_jobs(jobs)
        for job in jobs: job["status"]=expiration_status(job)
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"jobs":jobs,"duplicate_count":duplicate_count,"active_count":sum(j["status"]=="active" for j in jobs),"expired_count":sum(j["status"]=="expired" for j in jobs),"unknown_expiration_count":sum(j["status"]=="unknown" for j in jobs)})

class JobMatchTool:
    capability=CapabilitySpec(name="job.match",description="Match parsed job to resume")
    async def execute(self,request):
        resume=(find_step_record(request.context,"document.resume.read") or {}).get("output",{}); resume_text=str(resume.get("text","")).lower()
        parsed=(find_step_record(request.context,"job.parse") or {}).get("output",{}); jobs=parsed.get("jobs",[]) if isinstance(parsed,dict) else []
        tokens={x for x in re.findall(r"[a-zA-Z][a-zA-Z+#.-]{2,}",resume_text)}; matched=[]
        for job in jobs:
            words={x for x in re.findall(r"[a-zA-Z][a-zA-Z+#.-]{2,}",job.get("jd_text","").lower())}; overlap=sorted(tokens & words); score=round(100*len(overlap)/max(1,len(words)),2)
            matched.append({**job,"match_score":score,"classification":"strong" if score>=20 else "weak","fit_reasons":[f"shared skill/text: {x}" for x in overlap[:5]],"risks":[] if overlap else ["no lexical evidence"],"evidence":overlap[:10],"resume_evidence":overlap[:10],"job_evidence":overlap[:10]})
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"jobs":matched})

class JobRankTool:
    capability=CapabilitySpec(name="job.rank",description="Rank job candidates")
    async def execute(self,request):
        matched=(find_step_record(request.context,"job.match") or {}).get("output",{}); jobs=matched.get("jobs",[]) if isinstance(matched,dict) else []; active=[j for j in jobs if j.get("status")!="expired"]
        active.sort(key=lambda x:x.get("match_score",0),reverse=True)
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"shortlist":active[:10],"total_candidates":len(jobs),"duplicate_count":(find_step_record(request.context,"job.parse") or {}).get("output",{}).get("duplicate_count",0),"expired_filtered":len(jobs)-len(active)})

class ShortlistArtifactTool:
    capability=CapabilitySpec(name="artifact.write",description="Write shortlist artifacts")
    async def execute(self,request):
        goal_id=request.context.get("runtime",{}).get("goal_id",request.task_id); root=Path(str(request.arguments.get("output_dir","artifacts")))/goal_id; root.mkdir(parents=True,exist_ok=True)
        data=(find_step_record(request.context,"job.rank") or {}).get("output",{}); (root/"shortlist.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8");
        lines=["# Shortlist",""]
        for j in data.get("shortlist",[]): lines += [f"## {j.get('company','unknown')} — {j.get('title','unknown')}",f"- Location: {j.get('location','unknown')}",f"- Status: {j.get('status','unknown')}",f"- Match Score: {j.get('match_score',0)}",f"- Classification: {j.get('classification','unknown')}",f"- Source URL: {j.get('source_url','')}",f"- Fit Reasons: {', '.join(j.get('fit_reasons',[]))}",f"- Risks: {', '.join(j.get('risks',[]))}",f"- Evidence: {', '.join(j.get('evidence',[]))}",""]
        (root/"shortlist.md").write_text("\n".join(lines),encoding="utf-8")
        return ToolResult(status=ToolResultStatus.SUCCESS,output={"artifact_path":str(root)})

def build_live_registry():
    from lhas.tools.registry import ToolRegistry
    r=ToolRegistry()
    for tool in (ResumeReaderTool(),WebSearchTool(),WebFetchTool(),JobParseTool(),JobMatchTool(),JobRankTool(),ShortlistArtifactTool()): r.register(tool)
    return r
