import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
from sys import path


def _make_parser():

    def validate_dir(p):
        path = pathlib.Path(p)

        if not path.is_dir():
            raise argparse.ArgumentTypeError(
                f'Path does not exist: {path}'
            )

        return p

    def validate_profile_exists(p):
        profile_cmd = ['aws', 'configure', 'list-profiles']
        profiles = subprocess.check_output(profile_cmd).decode("utf-8").split('\n')
        if not p in profiles:
            raise argparse.ArgumentTypeError(
                f'Profile name must be available in `aws configure list-profiles`: {p}'
            )

        return p

    def validate_ip(ip):
        pattern = r'^([0-9]{1,3}\.){3}[0-9]{1,3}$'
        if not re.match(pattern, ip):
            raise argparse.ArgumentTypeError(
                f'IP address should be 4 groups of 1 to 3 numerals separated by periods: {ip}'
            )

        return ip

    parser = argparse.ArgumentParser()
    parser.description = 'transfer AMI drive to snowball, check includes/excludes if used for other purpose'
    parser.add_argument(
        '-d', '--drive',
        help='path to drive to transfer',
        type=validate_dir,
        required=True)
    parser.add_argument(
        '--profile',
        help='aws cli profile for current snowball',
        type=validate_profile_exists,
        required=True)
    parser.add_argument(
        '-i', '--ip',
        help='ip address of snowball',
        type=validate_ip,
        required=True)
    parser.add_argument(
        '-b', '--bucket',
        help='aws s3 destination bucket',
        type=str,
        default='pami-dance-storage')
    parser.add_argument(
        '-p', '--prefix',
        help='prefix to use within destination bucket',
        type=str,
        default='MPS-snowball')
    parser.add_argument(
        '--check_only',
        action='store_true'
    )
    parser.add_argument(
        '--eavie',
        action='store_true'
    )

    return parser


def transfer_files(
    source: os.PathLike,
    drive_name: str,
    awscli_profile: str,
    target_endpoint: str,
    target_dest: str,
    restart: bool=False
) -> None:

    if not restart:
        sync_smallfiles(source, drive_name, awscli_profile, target_endpoint, target_dest)

    sync_bigfiles(source, awscli_profile, target_endpoint, target_dest)


def sync_smallfiles(
    source: os.PathLike,
    drive_name: str,
    awscli_profile: str,
    target_endpoint: str,
    target_dest: str
) -> None:

    find_cmd = [
        'find', source,
        '-name', '*.txt',
        '-o',
        '-name', '*.json'
    ]
    tar_cmd = [
        'tar', '-c',
        '-f', '-',
        '-T', '-',
    ]
    sync_cmd = [
        'aws', 's3', 'cp',
        '--metadata', 'snowball-auto-extract=true',
        '--profile', awscli_profile,
        '--endpoint', target_endpoint,
        '-',
        f'{target_dest}/{drive_name}.tar'
    ]

    find_proc = subprocess.Popen(
        find_cmd, stdout=subprocess.PIPE
    )
    tar_proc = subprocess.Popen(
        tar_cmd, stdin=find_proc.stdout, stdout=subprocess.PIPE
    )
    subprocess.run(
        sync_cmd, stdin=tar_proc.stdout
    )



def sync_bigfiles(
    source: os.PathLike,
    awscli_profile: str,
    target_endpoint: str,
    target_dest: str
) -> None:

    sync_cmd = [
        'aws', 's3', 'sync',
        '--profile', awscli_profile,
        '--endpoint', target_endpoint,
        '--exclude', '*',
        '--include', '*.mkv',
        '--include', '*xml.gz',
        '--include', '*.mp4',
        '--include', '*.mov',
        '--include', '*.flac',
        '--include', '*.dv',
        '--include', '*.iso',
        '--include', '*.cue',
        '--include', '*.wav',
        '--include', '*.scc',
        '--include', '*.srt',
        '--include', '*Images*',
        '--exclude', '.fsevents*',
        '--exclude', '.Spotlight*',
        '--exclude', '.Trashes/*',
        '--exclude', '$RECYCLE.BIN/*',
        '--exclude', '._.*',
        '--exclude', '*.DS_Store',
        str(source),
        target_dest
    ]

    proc = subprocess.run(sync_cmd)


def check_transfer(
    drive_path: os.PathLike,
    awscli_profile: str,
    target_endpoint: str,
    target_bucket: str,
    target_prefix: str
) -> dict:
    source_set = get_files_on_source(drive_path)
    snowball_set = get_files_on_snowball(awscli_profile, target_endpoint, target_bucket, target_prefix)

    difference = compare_source_snowball(source_set, snowball_set)
    if not difference:
        return False
    else:
        return difference


def get_files_on_source(drive_path) -> set:
    drive_path = pathlib.Path(drive_path)
    root_files = drive_path.glob('*')
    audio_bag_files = drive_path.joinpath('Audio').glob('**/*')
    video_bag_files = drive_path.joinpath('Video').glob('**/*')
    film_bag_files = drive_path.joinpath('Film').glob('**/*')
    manifest = []

    for file_list in [root_files, audio_bag_files, video_bag_files, film_bag_files]:
        for path in file_list:
            if path.is_file() and path.suffix != '.txt' and path.suffix != '.json':
                manifest.append((str(path).replace(str(drive_path), ''), path.stat().st_size))

    return set(manifest)


def get_files_on_snowball(
    awscli_profile: str,
    target_endpoint: str,
    target_bucket: str,
    target_prefix: str
) -> set:

    ls_cmd = [
        'aws', 's3api', 'list-objects-v2',
        '--no-paginate',
        '--profile', awscli_profile,
        '--endpoint', target_endpoint,
        '--bucket', target_bucket,
        '--prefix', target_prefix
    ]
    output = subprocess.check_output(ls_cmd)

    files_on_snowball = {(x['Key'].replace(target_prefix, ''), x['Size']) for x in json.loads(output)['Contents']}
    return files_on_snowball


def compare_source_snowball(
    source_set: set,
    snowball_set: set,
) -> dict:

    if source_set == snowball_set:
        return None
    else:
        difference = {
            'source_diff': source_set - snowball_set,
            'snowball_diff': snowball_set - source_set
        }
        return difference


def transfer_eavie_files(
    source: os.PathLike,
    awscli_profile: str,
    target_endpoint: str,
    target_dest: str
) -> None:

    sync_cmd = [
        'aws', 's3', 'sync',
        '--profile', awscli_profile,
        '--endpoint', target_endpoint,
        '--exclude', '*',
        '--include', '*_em.*',
        '--include', '*_sc.*',
        '--exclude', '.fsevents*',
        '--exclude', '.Spotlight*',
        '--exclude', '.Trashes/*',
        '--exclude', '$RECYCLE.BIN/*',
        '--exclude', '._.*',
        '--exclude', '*.DS_Store',
        str(source),
        target_dest
    ]

    proc = subprocess.run(sync_cmd)


def main():
    parser = _make_parser()
    args = parser.parse_args()

    drive_path = pathlib.Path(args.drive)
    drive_name = drive_path.name
    target_endpoint = f'http://{args.ip}:8080'
    target_dest = f's3://{args.bucket}/{args.prefix}/{drive_name}/'

    if not args.eavie:
        if not args.check_only:
            transfer_files(drive_path, drive_name, args.profile, target_endpoint, target_dest, restart=True)

        differences = check_transfer(drive_path, args.profile, target_endpoint, args.bucket, f'{args.prefix}/{drive_name}')
        if not differences:
            print('Drive transfer seems good')
        else:
            print([x[0] for x in differences['source_diff']])
            bytes_remaining = sum([x[1] for x in differences['source_diff']])
            files_remaining = len(differences['source_diff'])
            print(f'{bytes_remaining} bytes ({files_remaining} files) to be transferred from source drive')
    else:
        transfer_eavie_files(drive_path, args.profile, target_endpoint, f's3://{args.bucket}/{drive_name}')


if __name__ == '__main__':
    main()
