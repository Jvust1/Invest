"""Local-only interactive acquisition CLI. Never pass a credential as an argument."""
from __future__ import annotations
import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.market_evidence.acquisition import AcquisitionError, collect, now, plan, preflight


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown arguments (including accidental credentials).
        self.exit(2, 'ARGUMENT_ERROR: use --help; credentials are not CLI arguments.\n')


def wizard() -> int:
    print('Invest 本机行情采集：只存本地，不下单。请勿向聊天、截图或日志提供 Token。')
    print('需要你已有 Tushare 四接口权限和适用的数据使用凭据。程序不代购、不授予许可。')
    symbol = input('沪深主板代码（例如600000.SH；仅格式示例）：').strip()
    end_default = (now().date()-timedelta(days=1)).isoformat()
    start_default = (now().date()-timedelta(days=31)).isoformat()
    start = input(f'开始日期 [{start_default}]：').strip() or start_default
    end = input(f'结束日期 [{end_default}]：').strip() or end_default
    evidence = Path(input('本机适用许可/权限凭据文件路径（正文不复制到输出）：').strip().strip('"'))
    default_output = Path.home()/f'Invest-Capture-{now():%Y%m%d-%H%M%S}'
    output = Path(input(f'新建结果目录 [{default_output}]：').strip().strip('"') or str(default_output))
    spec = plan(symbol, start, end)
    print(json.dumps(spec, ensure_ascii=False, indent=2))
    print('将向 api.tushare.pro 发送最多4次HTTPS请求；不用代理环境变量，无明文回退。')
    answer = input('确认你有权获取并在本机研究这些数据、允许此次网络请求？输入 YES：')
    if answer != 'YES':
        print('CANCELLED; 未读取凭据、未请求、未创建目录。')
        return 1
    return _run(spec, output, evidence, True, True)


def _run(spec, output, evidence, access, network):
    result = collect(spec, output, evidence, access_declared=access, network_allowed=network)
    print(json.dumps({k: result.get(k) for k in
                     ('status','integrity','review_state','error_code','execution_authorized')}, ensure_ascii=False))
    print('结果仅保存在你指定的新目录。成功采集不等于可回测；查看 review/index.html 和 collection.json。')
    return 0 if result['status']=='CAPTURED_MAPPING_CHECKED' else 2


def main(argv=None):
    parser = SafeParser(description='Invest authorized local acquisition; default is offline planning')
    parser.add_argument('command', choices=['plan','collect','wizard'])
    parser.add_argument('--symbol')
    parser.add_argument('--start-date')
    parser.add_argument('--end-date')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--confirm-access', action='store_true')
    parser.add_argument('--allow-network', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'wizard':
            return wizard()
        spec = plan(args.symbol, args.start_date, args.end_date)
        if args.command == 'plan':
            print(json.dumps(spec, ensure_ascii=False, indent=2))
            return 0
        if args.output is None or args.evidence is None:
            raise AcquisitionError('OUTPUT_AND_EVIDENCE_REQUIRED')
        return _run(spec,args.output,args.evidence,args.confirm_access,args.allow_network)
    except (Exception, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc,AcquisitionError) else ('INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'LOCAL_INPUT_OR_IO_ERROR')
        print('COLLECTION_ERROR: '+code,file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
