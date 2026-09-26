"""Receive this candidate's source capsule without committing transport URLs.

Only the repository owner's matching, bounded PR #4 source receipt is used.
Source contents must match a precommitted SHA256 before anything is executed.
"""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
EXPECTED='9daaab315a2f870d4b6f4eb2e57a452cef128100869cb1c490954253a0ca8c1a'

def main():
    if os.environ.get('GITHUB_REPOSITORY')!='Jvust2/Invest' or os.environ.get('GITHUB_REF')!='refs/heads/feat/g1-g5-workbench-20260926':
        raise SystemExit('Unexpected repository or branch')
    target=ROOT/'.growth_upgrade/source-capsule.json.gz'
    if target.exists():
        return
    request=urllib.request.Request('https://api.github.com/repos/Jvust2/Invest/issues/4/comments?per_page=100',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            payload=response.read(1000001)
        if len(payload)>1000000:
            raise ValueError('Oversized receipt response')
        comments=json.loads(payload)
        choices=[]
        for comment in comments:
            body=comment.get('body','')
            if comment.get('user',{}).get('id')!=322531942 or not body.startswith('INVEST_SOURCE_CAPSULE_V1\n') or len(body)>4000:
                continue
            item=json.loads(body.split('\n',1)[1])
            if item.get('sha256')==EXPECTED:
                choices.append(item)
        if not choices:
            raise ValueError('No matching owner receipt')
        url=choices[-1]['url']
        print('::add-mask::'+url)
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.oaiusercontent.com') or parsed.username or parsed.password:
            raise ValueError('Unexpected transport host')
        with urllib.request.urlopen(url,timeout=60) as response:
            compressed=response.read(100001)
        if len(compressed)>100000:
            raise ValueError('Oversized source capsule')
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw=stream.read(300001)
        if len(raw)>300000 or hashlib.sha256(raw).hexdigest()!=EXPECTED:
            raise ValueError('Source identity mismatch')
        target.write_bytes(compressed)
    except Exception:
        raise SystemExit('Source receipt unavailable, expired or invalid; no application source was changed') from None
    print('Verified source capsule received; transport URL is not committed.')

if __name__=='__main__':
    main()
