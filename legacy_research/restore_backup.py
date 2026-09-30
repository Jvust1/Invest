"""Restore an explicit private backup to a NEW directory; never overwrite."""
import argparse
from pathlib import Path
from invest.backup import LIMIT, restore_backup


def main():
    p = argparse.ArgumentParser(description='Invest 私人备份恢复（只创建新目录）')
    p.add_argument('backup',type=Path)
    p.add_argument('destination',type=Path)
    args = p.parse_args()
    if not args.backup.is_file() or args.backup.stat().st_size > LIMIT:
        p.error('备份不存在或超过100MiB限制')
    if not args.destination.parent.is_dir():
        p.error('目标父目录必须已经存在')
    try:
        target = restore_backup(args.backup.read_bytes(),args.destination)
    except (ValueError,OSError) as exc:
        p.error(str(exc))
    print('恢复完成：',target.resolve())
    print('使用 python -m invest --data-dir "'+str(target.resolve())+'" --open 启动')

if __name__ == '__main__':
    main()
