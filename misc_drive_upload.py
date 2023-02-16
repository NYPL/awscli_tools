import pathlib
import os
import subprocess
import argparse
import json


def _make_parser():

    def validate_dir(p):
        path = pathlib.Path(p)

        if not path.is_dir():
            raise argparse.ArgumentTypeError(
                f'Path does not exist: {path}'
            )

        return p

    parser = argparse.ArgumentParser()
    parser.description = 'transfer AMI drive to MPS-deeparchive, check includes/excludes if used for other purpose'
    parser.add_argument(
        '-d', '--drive',
        help='path to drive to transfer',
        type=validate_dir,
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
        default='MPS-deeparchive')
    parser.add_argument(
        '--metadata_only',
        help='only upload txt and json files',
        action='store_true')
    parser.add_argument(
        '--check_only',
        action='store_true')

    return parser



def transfer_files(
    source: os.PathLike,
    target_dest: str,
    metadata_only: bool
) -> None:

    sync_smallfiles(source, target_dest)

    if not metadata_only:
       sync_bigfiles(source, target_dest)


def sync_smallfiles(
    source: os.PathLike,
    target_dest: str
) -> None:

    sync_cmd = [
        'aws', 's3', 'sync',
        '--dryrun',
        '--storage-class', 'DEEP_ARCHIVE',
        '--include', '*.txt',
        '--include', '*.json',
        '--exclude', '.fsevents*',
        '--exclude', '.Spotlight*',
        '--exclude', '.Trashes/*',
        '--exclude', '$RECYCLE.BIN/*',
        '--exclude', '._.*',
        '--exclude', '*.DS_Store',
        '--exclude', '.com.apple.timemachine.donotpresent',
        str(source),
        target_dest
    ]

    subprocess.run(sync_cmd)

def sync_bigfiles(
    source: os.PathLike,
    target_dest: str
) -> None:

    sync_cmd = [
        'aws', 's3', 'sync',
        '--dryrun',
        '--storage-class', 'DEEP_ARCHIVE',
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
        '--include', '*.xlsx',
        '--exclude', '.fsevents*',
        '--exclude', '.Spotlight*',
        '--exclude', '.Trashes/*',
        '--exclude', '$RECYCLE.BIN/*',
        '--exclude', '._.*',
        '--exclude', '*.DS_Store',
        '--exclude', '.com.apple.timemachine.donotpresent',
        str(source),
        target_dest
    ]

    proc = subprocess.run(sync_cmd)


def check_transfer(
    drive_path: os.PathLike,
    target_bucket: str,
    target_prefix: str
) -> dict:
    
    source_set = get_files_on_source(drive_path)
    deeparchive_set = get_files_on_deeparchive(target_bucket, target_prefix)

    difference = compare_source_snowball(source_set, deeparchive_set)
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


def get_files_on_deeparchive(
    target_bucket: str,
    target_prefix: str
) -> set:
    
    def ls_call(contents = [], starting_token = None):
        ls_cmd = [
            'aws', 's3api', 'list-objects',
            '--bucket', target_bucket,
            '--prefix', target_prefix
        ]
        if starting_token:
            ls_cmd.extend([
                '--starting-token', starting_token
            ])
        output = subprocess.check_output(ls_cmd)

        if output:
            contents.extend(json.loads(output)['Contents'])
            #paginate until no additional returns
            ls_call(contents, contents[-1]['Key'])

        return contents

    contents = ls_call()

    files_on_deeparchive = {(x['Key'].replace(target_prefix, ''), x['Size']) for x in contents}
    return files_on_deeparchive


def compare_source_deeparchive(
    source_set: set,
    deeparchive_set: set,
) -> dict:

    if source_set == deeparchive_set:
        return None
    else:
        difference = {
            'source_diff': source_set - deeparchive_set,
            'snowball_diff': deeparchive_set - source_set
        }
        return difference

def main():

    parser = _make_parser()
    args = parser.parse_args()

    drive_path = pathlib.Path(args.drive)
    drive_name = drive_path.name
    target_dest = f's3://{args.bucket}/{args.prefix}/{drive_name}/'

    if not args.check_only:
        transfer_files(drive_path, target_dest, args.metadata_only)

    differences = check_transfer(drive_path, args.bucket, f'{args.prefix}/{drive_name}')
    if not differences:
        print('Drive transfer seems good')
    else:
        print([x[0] for x in differences['source_diff']])
        bytes_remaining = sum([x[1] for x in differences['source_diff']])
        files_remaining = len(differences['source_diff'])
        print(f'{bytes_remaining} bytes ({files_remaining} files) to be transferred from source drive')

if __name__ == '__main__':
    main()