"""Operator-only import: read originals, never execute/extract third-party code.

Keep output SQLite and detailed inventory private; they are not GitHub source.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from invest.chat.catalog import Catalog


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def inspect_zip(path, *, read_structured=False):
    """Bounded inspection only; CRC is checked for every selected readable member."""
    rows,texts=[],[]
    with zipfile.ZipFile(path) as z:
        if len(z.infolist())>100000: raise ValueError('archive entry count exceeds bound')
        total=0
        for entry in z.infolist():
            name=entry.filename
            posix=PurePosixPath(name)
            if posix.is_absolute() or '..' in posix.parts or '\\' in name:
                raise ValueError('unsafe archive member path')
            if entry.is_dir(): continue
            rows.append({'path':name,'bytes':entry.file_size,'crc32':f'{entry.CRC:08x}'})
            if not read_structured or posix.suffix.lower() not in {'.md','.txt','.json','.jsonl','.csv'}: continue
            if entry.file_size>16*1024*1024: continue
            if entry.file_size>max(1,entry.compress_size)*300: raise ValueError('archive expansion ratio exceeds bound')
            total+=entry.file_size
            if total>64*1024*1024: raise ValueError('selected uncompressed text exceeds bound')
            raw=z.read(entry)
            try: content=raw.decode('utf-8-sig')
            except UnicodeDecodeError: continue
            if re.search('(?i)(secret|credential|token|private.?key)',posix.name): continue
            texts.append((name,content,hashlib.sha256(raw).hexdigest()))
    return rows,texts


def build(repo: Path, drive_root: Path, output: Path, inventory: Path):
    if output.exists(): raise ValueError('use a fresh output DB; existing catalog must not be overwritten')
    catalog=Catalog(output)
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    counts={'github_documents':0,'drive_metadata':0,'structured_members':0}
    assets=[]
    tracked=subprocess.check_output(['git','-C',str(repo),'ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0')
    for rel in sorted(set(tracked)):
        if not rel or not (repo/rel).is_file() or rel.startswith(('legacy_','third_party/','docs/history/','governance/checkpoints/')): continue
        if (repo/rel).suffix.lower() not in {'.py','.md','.json','.toml'}: continue
        if (repo/rel).stat().st_size>2*1024*1024: continue
        if re.search('(?i)(secret|credential|token)',Path(rel).name): continue
        text=(repo/rel).read_text(encoding='utf-8-sig')
        # The working-tree label must never pretend new/uncommitted bytes equal HEAD.
        catalog.add(title=rel,content=text,source='github',
                    url=f'https://github.com/Jvust1/Invest/blob/{commit}/{rel}',
                    provenance={'base_commit':commit,'working_tree_snapshot':True,'file_sha256':sha256(repo/rel)},
                    license_note='project source; see repository/THIRD_PARTY.md')
        counts['github_documents']+=1
    roots=[(drive_root/'Invest','15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u'),
           (drive_root/'Github'/'03_Invest_量化投资','1oU0O8bQDy6yaIZoQdblf1goui8laOi1I')]
    for root,folder_id in roots:
        if not root.is_dir(): continue
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix=='.gdoc': continue
            row={'name':path.name,'size_bytes':path.stat().st_size,'sha256':sha256(path),
                 'source_folder_id':folder_id,'original_unchanged':True,'license_status':'UNVERIFIED'}
            if path.suffix=='.zip':
                members,_=inspect_zip(path)
                row.update(archive_members=len(members),text_or_csv_members=sum(PurePosixPath(r['path']).suffix in {'.csv','.json','.jsonl','.md'} for r in members),
                           member_listing_sha256=hashlib.sha256(json.dumps(members,sort_keys=True).encode()).hexdigest())
            assets.append(row)
            catalog.add(title=path.name,content=json.dumps(row,ensure_ascii=False),source='drive',
                        url='https://drive.google.com/drive/folders/'+folder_id,provenance=row,
                        license_note='metadata only; original package never executed or redistributed')
            counts['drive_metadata']+=1
    structured=drive_root/'Github'/'Structured_Books_20260928'
    for path in sorted(structured.glob('batch_*/*_structured.zip')):
        if not re.match(r'(09|13|15)_',path.name): continue
        expected_manifest=path.parent/'PACKAGE_HASHES.json'
        hashes=json.loads(expected_manifest.read_text(encoding='utf-8-sig'))
        files = hashes['files']
        if isinstance(files, dict):
            expected = files.get(path.name)
        else:
            expected = next((r for r in files if r['file']==path.name),None)
        actual=sha256(path)
        if not expected or actual!=expected['sha256']: raise ValueError('structured package hash mismatch: '+path.name)
        members,texts=inspect_zip(path,read_structured=True)
        row={'name':path.name,'sha256':actual,'size_bytes':path.stat().st_size,'declared_hash_matches':True,
             'archive_members':len(members),'readable_members':len(texts),'license_status':'PRIVATE_REFERENCE_ONLY'}
        assets.append(row)
        for member,content,member_sha in texts:
            # Private bibliographic index: no book bytes are put in the public repository.
            for index,start in enumerate(range(0,len(content),12000)):
                catalog.add(title=path.stem+' / '+member+f' / segment {index+1}',content=content[start:start+12000],source='drive',
                            url='https://drive.google.com/drive/folders/1czHF7ZHrDjmw53soJJUsLweh13FctgoW',
                            provenance={'package':path.name,'package_sha256':actual,'member':member,'member_sha256':member_sha,
                                        'segment_start':start,'license_status':'PRIVATE_REFERENCE_ONLY'},
                            license_note='private reference only; copyright/distribution rights not independently verified')
                counts['structured_members']+=1
    result={'schema':'invest-private-assets-v1','repository':'Jvust1/Invest','base_commit':commit,
            'counts':counts,'assets':assets,'limitations':['Metadata/hashes do not prove software or market-data rights.',
                'Selected book structures are research reference, not live prices, recommendation training labels or forecasts.',
                'No upstream source package was executed; original source files unchanged.']}
    inventory.parent.mkdir(parents=True,exist_ok=True)
    inventory.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'INDEX_BUILT','counts':counts,'assets':len(assets),'catalog_sha256':sha256(output)},ensure_ascii=False))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--drive-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True)
    a=p.parse_args();build(a.repo,a.drive_root,a.output,a.inventory)


if __name__=='__main__': main()
