"""Offline raw-evidence CLI. No tokens accepted, no provider requests performed."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.market_evidence.intake import audit_bundle, IntakeError, assemble_exports
from integrations.market_evidence.fixtures import fixture
from integrations.market_evidence.report import write_report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Invest ENG-04A local raw-evidence auditor')
    commands=parser.add_subparsers(dest='command',required=True)
    f=commands.add_parser('fixture',help='Create an explicitly synthetic four-response example')
    f.add_argument('--output',required=True,type=Path)
    f.add_argument('--complete',action='store_true',help='Include fake evidence, marked synthetic and never an actual license')
    b=commands.add_parser('assemble',help='Bind existing local response files; does not fetch data or grant a license')
    b.add_argument('--input',required=True,type=Path)
    b.add_argument('--output',required=True,type=Path)
    b.add_argument('--symbol',required=True)
    b.add_argument('--start-date',required=True)
    b.add_argument('--end-date',required=True)
    b.add_argument('--captured-at',required=True)
    a=commands.add_parser('audit',help='Read a local bundle and create a new HTML/JSON report directory')
    a.add_argument('--input',required=True,type=Path)
    a.add_argument('--output',required=True,type=Path)
    a.add_argument('--as-of',help='Explicit replay time with timezone; omitted means current clock')
    args=parser.parse_args(argv)
    try:
        if args.command=='fixture':
            fixture(args.output,complete=args.complete,candidate=True)
            print('SYNTHETIC_FIXTURE_CREATED; no real provider data or license')
            return 0
        if args.command=='assemble':
            assemble_exports(args.input,args.output,symbol=args.symbol,start_date=args.start_date,
                             end_date=args.end_date,captured_at=args.captured_at)
            print('LOCAL_EXPORTS_BOUND; provenance unverified, license and market evidence missing')
            return 0
        result=audit_bundle(args.input,as_of=args.as_of)
        write_report(result,args.output,input_root=args.input)
        report=result['report']
        print(json.dumps({'integrity':report['integrity'],'review_state':report.get('review_state','EVIDENCE_INCOMPLETE'),
                          'report_id':report['report_id'],'execution_authorized':False},ensure_ascii=False))
        # 0 means mapping structurally checked, NOT licensed/real/ready to trade.
        return 0 if report['integrity']=='RAW_MAPPING_CHECKED' else 2
    except (IntakeError,OSError,ValueError) as exc:
        print('INTAKE_CLI_ERROR: '+(exc.code if isinstance(exc,IntakeError) else 'FILE_OR_ARGUMENT_ERROR'),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
