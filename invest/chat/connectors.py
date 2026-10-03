"""Bounded, read-only GitHub and Drive clients. Credentials stay server-side."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import build_opener, HTTPRedirectHandler, Request

REPOSITORY = 'Jvust1/Invest'
REPOSITORY_ID = 1381007406
DEFAULT_FOLDERS = ('15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u', '1oU0O8bQDy6yaIZoQdblf1goui8laOi1I')
MAX_BYTES = 2*1024*1024
TEXT_EXTENSIONS = {'.py','.md','.json','.jsonl','.csv','.txt','.toml','.yaml','.yml','.html','.css','.js','.sh'}


class ConnectorError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_bytes(url: str, headers=None, *, data=None, method='GET', maximum=MAX_BYTES) -> bytes:
    # All URL construction is internal. Refuse redirects rather than forwarding credentials.
    request = Request(url, headers=dict(headers or {}, **{'User-Agent':'Invest-Chat-Research/1'}), data=data, method=method)
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(maximum+1)
    except HTTPError as exc:
        raise ConnectorError(f'provider HTTP {exc.code}; no provider response body or credentials logged') from None
    except (URLError, TimeoutError, OSError):
        raise ConnectorError('provider connection failed or timed out; no implicit fallback') from None
    if len(raw) > maximum:
        raise ConnectorError('provider response exceeds configured size limit')
    return raw


def json_get(url, headers=None):
    try:
        return json.loads(request_bytes(url, headers))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConnectorError('provider did not return valid JSON') from None


def safe_path(path: str) -> str:
    if not isinstance(path, str) or len(path)>500 or '\\' in path or '%' in path or ':' in path or not path:
        raise ValueError('invalid repository path')
    value = PurePosixPath(path)
    if value.is_absolute() or any(part in {'..','.'} or part.startswith('.') for part in path.split('/')):
        raise ValueError('hidden files and path traversal are not exposed')
    if value.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError('only bounded text/code resources are exposed')
    if re.search(r'(?i)(?:^|[/_.-])(secret|credentials?|tokens?|private[-_]?key)(?:$|[/_.-])', path):
        raise ValueError('credential-like resource names are not exposed')
    return path


class GitHubClient:
    def __init__(self, *, ref=None):
        self.ref = ref or os.environ.get('INVEST_GITHUB_REF','main')
        if not re.fullmatch(r'[A-Za-z0-9._/-]{1,150}', self.ref):
            raise ValueError('invalid configured GitHub ref')
        self.headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        token = os.environ.get('INVEST_GITHUB_TOKEN')
        if token:
            self.headers['Authorization'] = 'Bearer ' + token

    def resolve(self) -> str:
        metadata = json_get('https://api.github.com/repos/'+REPOSITORY, self.headers)
        if metadata.get('id') != REPOSITORY_ID or metadata.get('full_name','').casefold() != REPOSITORY.casefold():
            raise ConnectorError('repository identity changed; refresh configuration explicitly')
        result = json_get('https://api.github.com/repos/'+REPOSITORY+'/commits/'+quote(self.ref,safe=''), self.headers)
        sha = result.get('sha','')
        if not re.fullmatch(r'[a-f0-9]{40}',sha):
            raise ConnectorError('GitHub ref did not resolve to a commit')
        return sha

    def list_files(self, *, query='', limit=20) -> dict:
        if not isinstance(query,str) or len(query)>200 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('invalid GitHub listing bounds')
        sha = self.resolve()
        tree = json_get(f'https://api.github.com/repos/{REPOSITORY}/git/trees/{sha}?recursive=1', self.headers)
        if tree.get('truncated'):
            raise ConnectorError('GitHub tree is truncated; no complete-catalog claim')
        rows = []
        for item in tree.get('tree',[]):
            if item.get('type') != 'blob': continue
            path = item.get('path','')
            try: safe_path(path)
            except ValueError: continue
            if query and not all(term.casefold() in path.casefold() for term in query.split()): continue
            rows.append({'id':f'github:{sha}:{path}','title':path,'source':'github',
                         'url':f'https://github.com/{REPOSITORY}/blob/{sha}/{quote(path,safe="/")}',
                         'commit':sha,'git_blob_sha':item.get('sha'),'size_bytes':item.get('size')})
        return {'results':rows[:limit], 'total_matches':len(rows),'limited':len(rows)>limit,'commit':sha}

    def fetch(self, path: str, *, commit=None, offset=0, max_chars=2000) -> dict:
        path = safe_path(path)
        if type(offset) is not int or offset<0 or type(max_chars) is not int or not 1<=max_chars<=4000:
            raise ValueError('invalid GitHub excerpt bounds')
        sha = commit or self.resolve()
        if not re.fullmatch(r'[a-f0-9]{40}',sha): raise ValueError('commit must be a full SHA')
        result = json_get(f'https://api.github.com/repos/{REPOSITORY}/contents/{quote(path,safe="/")}?ref={sha}',self.headers)
        if not isinstance(result,dict) or result.get('encoding')!='base64' or result.get('size',MAX_BYTES+1)>MAX_BYTES:
            raise ConnectorError('GitHub resource is not a bounded UTF-8 file')
        try:
            raw = base64.b64decode(result['content'])
            text = raw.decode('utf-8-sig')
        except (ValueError,UnicodeDecodeError): raise ConnectorError('GitHub text decoding failed') from None
        if offset>len(text): raise ValueError('offset beyond file')
        return {'id':f'github:{sha}:{path}','title':path,'url':f'https://github.com/{REPOSITORY}/blob/{sha}/{quote(path,safe="/")}',
                'source':'github','commit':sha,'git_blob_sha':result['sha'],'sha256':hashlib.sha256(raw).hexdigest(),
                'text':text[offset:offset+max_chars],'offset':offset,'truncated':offset+max_chars<len(text),
                'untrusted_source_material':True,'data_scope':'REFERENCE_ONLY'}


class DriveClient:
    def __init__(self, *, folders=None):
        value = os.environ.get('INVEST_DRIVE_FOLDER_IDS')
        self.folders = tuple(folders or (value.split(',') if value else DEFAULT_FOLDERS))
        if not self.folders or len(self.folders)>10 or any(not re.fullmatch('[A-Za-z0-9_-]{10,100}',f) for f in self.folders):
            raise ValueError('invalid operator folder allowlist')

    @property
    def configured(self):
        return bool(os.environ.get('INVEST_GOOGLE_ACCESS_TOKEN') or all(os.environ.get(k) for k in
                    ('INVEST_GOOGLE_CLIENT_ID','INVEST_GOOGLE_CLIENT_SECRET','INVEST_GOOGLE_REFRESH_TOKEN')))

    def headers(self):
        token = os.environ.get('INVEST_GOOGLE_ACCESS_TOKEN')
        if not token:
            keys = ('INVEST_GOOGLE_CLIENT_ID','INVEST_GOOGLE_CLIENT_SECRET','INVEST_GOOGLE_REFRESH_TOKEN')
            if not all(os.environ.get(k) for k in keys):
                raise ConnectorError('Drive OAuth not configured; use authorized connector or build a private local index')
            data = urlencode(dict(client_id=os.environ[keys[0]],client_secret=os.environ[keys[1]],
                                 refresh_token=os.environ[keys[2]],grant_type='refresh_token')).encode()
            try: token = json.loads(request_bytes('https://oauth2.googleapis.com/token',
                                    {'Content-Type':'application/x-www-form-urlencoded'},data=data,method='POST')).get('access_token')
            except (ValueError,KeyError): raise ConnectorError('Drive OAuth token refresh failed') from None
            if not isinstance(token,str) or not token: raise ConnectorError('Drive OAuth token refresh failed')
        return {'Authorization':'Bearer '+token}

    def metadata(self, file_id):
        if not isinstance(file_id,str) or not re.fullmatch('[A-Za-z0-9_-]{10,100}',file_id):
            raise ValueError('invalid Drive file ID')
        url = 'https://www.googleapis.com/drive/v3/files/'+file_id+'?'+urlencode({
            'fields':'id,name,mimeType,size,parents,modifiedTime,webViewLink,trashed','supportsAllDrives':'true'})
        item = json_get(url,self.headers())
        if item.get('trashed'): raise ConnectorError('Drive resource is trashed')
        return item

    def assert_in_scope(self, item):
        # Verify ancestry; shortcuts and unrelated private files are not followed.
        frontier, seen = [item], set()
        for _ in range(10):
            next_ids = set()
            for current in frontier:
                if current['id'] in self.folders: return
                if current['id'] in seen: continue
                seen.add(current['id'])
                next_ids.update(current.get('parents',[]))
            if not next_ids: break
            if len(next_ids)>20: raise ConnectorError('Drive ancestry exceeds scope bound')
            frontier = [self.metadata(key) for key in sorted(next_ids-seen)]
        raise ConnectorError('Drive file is outside operator-allowed folders')

    def list_files(self, folder_id=None, *, limit=20, page_token=None) -> dict:
        folder_id = folder_id or self.folders[0]
        if type(limit) is not int or not 1<=limit<=100: raise ValueError('Drive listing limit must be 1-100')
        if page_token is not None and (not isinstance(page_token,str) or len(page_token)>2000): raise ValueError('invalid provider page token')
        self.assert_in_scope(self.metadata(folder_id))
        params = {'q':f"trashed = false and '{folder_id}' in parents",'pageSize':limit,'orderBy':'name',
                  'fields':'nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents)',
                  'supportsAllDrives':'true','includeItemsFromAllDrives':'true'}
        if page_token: params['pageToken']=page_token
        result = json_get('https://www.googleapis.com/drive/v3/files?'+urlencode(params),self.headers())
        return {'files':[{'id':'drive:'+r['id'],'title':r['name'],'mime_type':r['mimeType'],
                         'source':'drive','url':r.get('webViewLink','https://drive.google.com/file/d/'+r['id']+'/view'),
                         'modified_time':r.get('modifiedTime'),'size_bytes':r.get('size')} for r in result.get('files',[])],
                'next_page_token':result.get('nextPageToken'),'folder_id':folder_id}

    def fetch(self, file_id, *, offset=0, max_chars=1000) -> dict:
        if type(offset) is not int or offset<0 or type(max_chars) is not int or not 1<=max_chars<=2000:
            raise ValueError('invalid Drive excerpt bounds')
        item = self.metadata(file_id)
        self.assert_in_scope(item)
        mime = item['mimeType']
        title = item['name']
        if mime in {'application/vnd.google-apps.shortcut','application/vnd.google-apps.folder'}:
            raise ConnectorError('Drive folders/shortcuts are not readable text files')
        if title.startswith('.') or re.search('(?i)(secret|credential|token|private.?key)',title):
            raise ConnectorError('credential-like files are not exposed')
        if int(item.get('size',0))>MAX_BYTES: raise ConnectorError('Drive text exceeds bounded download limit; index it privately offline')
        if mime == 'application/vnd.google-apps.document':
            endpoint = 'export?'+urlencode({'mimeType':'text/plain'})
        elif mime == 'application/vnd.google-apps.spreadsheet':
            raise ConnectorError('Sheets require an explicit sheet/range export; use the connected Sheets tool, not an implicit first-sheet export')
        elif mime.startswith('text/') or mime in {'application/json','application/x-ndjson'} or PurePosixPath(title).suffix in {'.md','.json','.jsonl','.csv','.txt'}:
            endpoint = '?alt=media&supportsAllDrives=true'
        else:
            raise ConnectorError('binary/archive resource: use the audited offline catalog, never execute or unpack remotely')
        raw = request_bytes('https://www.googleapis.com/drive/v3/files/'+file_id+'/'+endpoint if endpoint.startswith('export') else
                            'https://www.googleapis.com/drive/v3/files/'+file_id+endpoint,self.headers())
        try: text = raw.decode('utf-8-sig')
        except UnicodeDecodeError: raise ConnectorError('Drive file is not UTF-8 text') from None
        if offset>len(text): raise ValueError('offset beyond file')
        return {'id':'drive:'+file_id,'title':title,'source':'drive','url':item.get('webViewLink','https://drive.google.com/file/d/'+file_id+'/view'),
                'modified_time':item.get('modifiedTime'),'sha256':hashlib.sha256(raw).hexdigest(),
                'text':text[offset:offset+max_chars],'offset':offset,'truncated':offset+max_chars<len(text),
                'untrusted_source_material':True,'data_scope':'REFERENCE_ONLY','license_independently_verified':False}
