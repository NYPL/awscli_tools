import argparse
import pathlib
import subprocess
import os


def _make_parser():

    def validate_disk(n):

        if not int(n) > 1:
            raise argparse.ArgumentTypeError(
                'Disk number must be greater than 1 (Macintonsh HD)'
            )
        
        n = int(n)

        path = pathlib.Path(f'/dev/disk{n}s2')
        
        if not path.is_block_device():
            raise argparse.ArgumentTypeError(
                f'Device path does not exist: {path}'
            )

        return n

    parser = argparse.ArgumentParser()
    parser.description = 'remount drives as read-only'
    parser.add_argument(
        '-d', '--disk',
        help='disk number for drive device',
        type=validate_disk,
        required=True)

    parser.add_argument(
        '-m', '--maxdisk',
        help='optional, if provided mounts all drives in range from -d to -m',
        type=validate_disk)

    return parser


def unmount(drive_path: os.PathLike) -> None:
    
    unmount_cmd = [
        'diskutil', 'unmount', drive_path
    ]

    proc = subprocess.run(unmount_cmd)


def mount_readonly(drive_path: os.PathLike) -> None:

    mount_cmd = [ 
        'diskutil', 'mount', 'readOnly', drive_path
    ]

    proc = subprocess.run(mount_cmd)
    


def main():
    parser = _make_parser()
    args = parser.parse_args()

    if args.maxdisk:
        high = args.maxdisk
    else:
        high = args.disk

    for disk in range(args.disk, high + 1):
        disk_path = pathlib.Path(f'/dev/disk{disk}s2')
        unmount(disk_path)
        mount_readonly(disk_path)


if __name__ == '__main__':
    main()
