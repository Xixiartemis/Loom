"""Deterministic, evidence-preserving helpers for the D2 smoke pipeline."""
from __future__ import annotations
import hashlib, re
from urllib.parse import urlsplit, urlunsplit

def canonical_url(url: str) -> str:
    p=urlsplit(url.strip()); return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),p.query,""))

def deduplicate_jobs(jobs: list[dict]) -> tuple[list[dict], int]:
    seen_urls=set(); seen_hashes=set(); seen_names=set(); out=[]; duplicates=0
    for job in jobs:
        url=canonical_url(job.get("source_url","")) if job.get("source_url") else ""
        digest=job.get("content_hash",""); name=(str(job.get("company","")).strip().lower(),str(job.get("title","")).strip().lower())
        duplicate=(bool(url) and url in seen_urls) or (bool(digest) and digest in seen_hashes) or (all(name) and name in seen_names)
        if duplicate: duplicates+=1; continue
        if url: seen_urls.add(url)
        if digest: seen_hashes.add(digest)
        if all(name): seen_names.add(name)
        out.append(job)
    return out, duplicates

def expiration_status(job: dict) -> str:
    value=" ".join(str(job.get(k,"")) for k in ("status","deadline","text","jd_text","search_snippet")).lower()
    if any(x in value for x in ("closed","expired","no longer accepting")): return "expired"
    if job.get("deadline") or any(x in value for x in ("apply now","open position","accepting applications")): return "active"
    return "unknown"

def shortlist_record(job: dict, *, score=0, fit_reasons=None, risks=None) -> dict:
    return {"company":job.get("company","unknown"),"title":job.get("title","unknown"),"location":job.get("location","unknown"),"source_url":job.get("source_url",""),"status":expiration_status(job),"match_score":score,"classification":"unknown","fit_reasons":fit_reasons or [],"risks":risks or [],"evidence":[{"source_url":job.get("source_url",""),"content_hash":job.get("content_hash","")}]}
