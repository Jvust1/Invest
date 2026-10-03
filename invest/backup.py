"""Explicit complete local backup. Recovery creates a new directory, never overwrites."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile

# Ledger first: its immutable dataset references are included by the following state snapshot.
DATABASES = ('paper.sqlite','state.sqlite')
LIMIT = 100 * 1024 * 1024


def export_backup(root):
    root=Path(root)
    out=io.BytesIO(); manifest={'schema':'invest-private-backup-v1','files':{}}
    total_bytes=0
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in DATABASES:
            path=root/name
            if not path.exists(): continue
            target=Path(tmp)/name
            with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('数据库完整性检查失败')
            if target.stat().st_size>LIMIT: raise ValueError('备份数据库超过100MB限制')
            raw=target.read_bytes()
            total_bytes+=len(raw)
            if total_bytes>LIMIT: raise ValueError('备份数据库总量超过限制')
            z.writestr(name,raw)
            manifest['files'][name]=hashlib.sha256(raw).hexdigest()
        manifest_raw=json.dumps(manifest).encode('utf-8')
        if total_bytes+len(manifest_raw)>LIMIT: raise ValueError('备份含清单总量超过限制')
        z.writestr('manifest.json',manifest_raw)
    if not manifest['files']: raise ValueError('没有可备份的数据')
    return out.getvalue()


def restore_backup(raw, destination):
    destination=Path(destination)
    if destination.exists(): raise ValueError('恢复目录必须不存在，不覆盖已有数据')
    if len(raw)>LIMIT: raise ValueError('备份过大')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=z.infolist()
        if len(members)>3 or sum(x.file_size for x in members)>LIMIT: raise ValueError('备份超过限制')
        names=[x.filename for x in members]
        if len(set(names))!=len(names) or any(x not in DATABASES+('manifest.json',) for x in names): raise ValueError('备份内容不合法')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('schema')!='invest-private-backup-v1': raise ValueError('不是Invest备份')
        blobs={name:z.read(name) for name in DATABASES if name in names}
        if set(manifest.get('files',{}))!=set(blobs) or not blobs: raise ValueError('备份清单不完整')
        for name,blob in blobs.items():
            if hashlib.sha256(blob).hexdigest()!=manifest['files'][name]: raise ValueError('备份哈希不匹配')
        with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
            for name,blob in blobs.items():
                p=Path(temp)/name;p.write_bytes(blob)
                with closing(sqlite3.connect(p)) as conn:
                    conn.execute('PRAGMA trusted_schema=OFF')
                    if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('数据库已损坏')
            destination.mkdir(exist_ok=False)
            for name in blobs: (Path(temp)/name).replace(destination/name)
    return destination
