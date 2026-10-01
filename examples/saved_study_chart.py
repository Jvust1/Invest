"""Render one explicit synthetic saved-study example, with no market/provider call."""
from pathlib import Path
import sys
import tempfile

from invest.data import demo_dataset
from invest.experiments import run_study
from invest.study_charts import render_study_png
from invest.workspace import Workspace


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: python examples/saved_study_chart.py OUTPUT.png')
    destination = Path(sys.argv[1])
    if destination.exists():
        raise SystemExit('output already exists; choose a new file')
    with tempfile.TemporaryDirectory() as directory:
        workspace = Workspace(Path(directory) / 'state.sqlite')
        record = workspace.put('study', run_study(demo_dataset(), {
            'symbol': '600000.SH', 'cost_model_acknowledged': True}))
        destination.write_bytes(render_study_png(record, 0))
        print('Synthetic study:', record['id'])
        print('PNG:', destination)
        print('Exploratory demonstration, not market validation or investment advice')


if __name__ == '__main__':
    main()
