"""Render an existing native JSON export without a provider, search or new record.

Source checkout: python -m examples.saved_native_chart INPUT.json OUTPUT.png
The PNG contains original source/producer declarations. Review before sharing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from examples.native_research_record import read_native_json
from invest.native_charts import render_native_png
from invest.native_research import parse_native_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('png', type=Path)
    args = parser.parse_args(argv)
    if args.png.exists():
        parser.error('output already exists; choose a new PNG path')
    record = parse_native_json(read_native_json(args.record))
    png = render_native_png(record)
    # Exclusive creation also guards a file created during rendering.
    with args.png.open('xb') as output:
        output.write(png)
    print('Native record:', record['id'])
    print('Input role declaration:', record['payload']['input_role'])
    print('PNG:', args.png)
    print('Exploratory native units; not A-share cash execution or market validation')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
