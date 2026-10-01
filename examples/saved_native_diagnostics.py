"""Export descriptive diagnostics from an existing saved native JSON report.

python -m examples.saved_native_diagnostics INPUT.json OUTPUT.json
No provider, optimizer, model fitting or new authoritative record is involved.
"""
import argparse
from pathlib import Path
from examples.native_research_record import read_native_json
from invest.native_research import parse_native_json
from invest.native_diagnostics import native_diagnostics
from invest.server import encode_json


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args(argv)
    if args.output.exists():parser.error('output already exists; choose a new path')
    record=parse_native_json(read_native_json(args.record))
    result=native_diagnostics(record)
    with args.output.open('xb') as output:output.write(encode_json(result))
    print('Status:',result['status'])
    print('Diagnostics:',result['diagnostics_id'])
    print('Exploratory asymptotic statistics; no strategy significance or profit claim')
    return 0


if __name__=='__main__':raise SystemExit(main())
