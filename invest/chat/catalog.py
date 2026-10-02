"""Private, operator-built resource index; no user-supplied filesystem paths."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlparse


class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connection(self, *, writable=False):
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path))
        else:
            db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            db.row_factory = sqlite3.Row
            yield db
            if writable:
                db.commit()
        finally:
            db.close()

    def add(self, *, title: str, content: str, source: str, url: str,
            provenance: dict | None = None, license_note='UNVERIFIED') -> str:
        if source not in {'github', 'drive'}:
            raise ValueError('source must be github or drive')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'drive.google.com', 'docs.google.com'}:
            raise ValueError('catalog requires a provider citation URL')
        if not title or len(title) > 500 or not isinstance(content, str) or len(content.encode()) > 2*1024*1024:
            raise ValueError('catalog document exceeds its size limit')
        sha = hashlib.sha256(content.encode()).hexdigest()
        key = 'local:' + hashlib.sha256((source + url + title + sha).encode()).hexdigest()
        provenance = dict(provenance or {}, content_sha256=sha)
        with self.connection(writable=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY,title TEXT,content TEXT,source TEXT,url TEXT,sha256 TEXT,provenance TEXT,license_note TEXT)')
            db.execute('INSERT OR REPLACE INTO resources VALUES(?,?,?,?,?,?,?,?)',
                       (key, title, content, source, url, sha, json.dumps(provenance, ensure_ascii=False), license_note))
        return key

    def search(self, query: str, *, source='all', limit=10) -> list[dict]:
        if source not in {'all', 'github', 'drive'} or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('invalid search bounds')
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError('query must contain 1-200 characters')
        if not self.path.is_file():
            return []
        tokens = query.strip().split()[:8]
        where, args = [], []
        for token in tokens:
            pattern = '%' + token.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
            where.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            args.extend([pattern, pattern])
        if source != 'all':
            where.append('source=?')
            args.append(source)
        args.append(limit)
        with self.connection() as db:
            rows = db.execute('SELECT * FROM resources WHERE ' + ' AND '.join(where) + ' ORDER BY title,id LIMIT ?', args).fetchall()
        output = []
        for row in rows:
            position = max(0, row['content'].casefold().find(tokens[0].casefold()) - 70)
            item = {k:row[k] for k in ('id','title','source','url','sha256','license_note')}
            item.update(excerpt=row['content'][position:position+400], untrusted_source_material=True)
            output.append(item)
        return output

    def fetch(self, key: str, *, offset=0, max_chars=1000) -> dict:
        if not isinstance(key, str) or not key.startswith('local:') or type(offset) is not int or offset < 0:
            raise ValueError('invalid resource ID or offset')
        if type(max_chars) is not int or not 1 <= max_chars <= 2000:
            raise ValueError('fetch is limited to 2000 characters')
        with self.connection() as db:
            row = db.execute('SELECT * FROM resources WHERE id=?', (key,)).fetchone()
        if row is None:
            raise LookupError('resource not indexed')
        if hashlib.sha256(row['content'].encode()).hexdigest() != row['sha256']:
            raise ValueError('catalog content hash mismatch')
        if offset > len(row['content']):
            raise ValueError('offset is beyond the document')
        item = {k:row[k] for k in ('id','title','source','url','sha256','license_note')}
        item.update(text=row['content'][offset:offset+max_chars], offset=offset,
                    next_offset=offset+max_chars if offset+max_chars < len(row['content']) else None,
                    provenance=json.loads(row['provenance']), untrusted_source_material=True,
                    data_scope='REFERENCE_ONLY', truth_and_license_independently_verified=False)
        return item
