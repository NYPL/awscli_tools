import argparse
from configparser import ConfigParser
from datetime import datetime
import json
import os
import pathlib
import re
import subprocess
import time


def _make_parser():

    def validate_file(p):
        path = pathlib.Path(p)

        if not path.is_file():
            raise argparse.ArgumentTypeError(
                f'Manifest file path does not exist: {path}'
            )

        return p

    def validate_unlock(u):
        pattern = r'^([a-f0-9]{5}-){4}[a-f0-9]{5}$'
        if not re.match(pattern, u):
            raise argparse.ArgumentTypeError(
                f'Unlock code should be 4 groups of 5 hexadecimal characters separated by dashes: {u}'
            )

        return u

    def validate_ip(ip):
        pattern = r'^([0-9]{1,3}\.){3}[0-9]{1,3}$'
        if not re.match(pattern, ip):
            raise argparse.ArgumentTypeError(
                f'IP address should be 4 groups of 1 to 3 numerals separated by periods: {ip}'
            )

        return ip

    parser = argparse.ArgumentParser()
    parser.description = 'setup snowball for transfers, requires awscli and snowballedge tools'
    parser.add_argument(
        '-m', '--manifest',
        help='path to the manifest file for a snowball job',
        type=validate_file,
        required=True)
    parser.add_argument(
        '-u', '--unlock_code',
        help='unlock code for a snowball job',
        type=validate_unlock,
        required=True)
    parser.add_argument(
        '-i', '--ip',
        help='ip address of snowball',
        type=validate_ip,
        required=True)

    return parser


def get_snowball_profiles() -> list:

    snowball_config = pathlib.Path.home().joinpath('.aws/snowball/config/snowball-edge.config')
    with open(snowball_config, 'r') as f:
        cfg = json.load(f)

    return cfg['profiles'].keys()


def is_unlocked(
    manifest_path: os.PathLike,
    unlock_code: str,
    device_ip: str
) -> bool:

    describe_cmd = [
        'snowballEdge', 'describe-device',
        '--manifest-file', manifest_path,
        '--unlock-code', unlock_code,
        '--endpoint', f'https://{device_ip}'
    ]

    output = subprocess.check_output(describe_cmd)

    state = json.loads(output.decode('utf-8'))['UnlockStatus']['State']

    if state == 'UNLOCKED':
        return True
    else:
        return False


def get_snowballedge_profile(unlock_code: str) -> str:

    profile_path = pathlib.Path.home().joinpath('.aws/snowball/config/snowball-edge.config')

    if not profile_path.is_file:
        return None
    else:
        with open(profile_path) as file:
            profiles = json.load(file)

        for key, value in profiles['profiles'].items():
            if value['unlockCode'] == unlock_code:
                return key


def unlock_snowball(
    manifest_path: os.PathLike,
    unlock_code: str,
    device_ip: str
) -> str:

    profile = f'xfr-{datetime.now().strftime("%Y%m%d")}'

    pathlib.Path(manifest_path).resolve()

    unlock_cmd = [
        'snowballEdge', 'unlock-device',
        '--manifest-file', manifest_path,
        '--unlock-code', unlock_code,
        '--endpoint', f'https://{device_ip}',
        '--profile', profile
    ]

    print('Unlocking snowball, may take 3 minutes.')
    proc = subprocess.run(unlock_cmd, timeout=3)
    time.sleep(180)

    if not profile in get_snowball_profiles():
        raise Exception(f'Snowball was not unlocked successfully with following command:\n{" ".join(proc.args)}')

    return profile


def get_snowball_access_key(profile: str) -> tuple[str, str]:

    access_key_cmd = [
        'snowballEdge', 'list-access-keys',
        '--profile', profile
    ]

    output = subprocess.check_output(access_key_cmd)
    access_key = json.loads(output)['AccessKeyIds'][0]

    return access_key


def get_snowball_secret_key(profile: str, access_key: str) -> tuple[str, str]:
    
    secret_key_cmd = [
        'snowballEdge', 'get-secret-access-key',
        '--profile', profile,
        '--access-key-id', access_key
    ]

    proc = subprocess.run(secret_key_cmd, capture_output=True)
    cfg = ConfigParser()
    try:
        secret_key = cfg.read_string(proc.stdout.decode('utf-8'))
        secret_key = cfg['snowballEdge']['aws_secret_access_key']
    except:
        raise Exception(f'Snowball was not configured successfully with following command:\n{proc.args}')

    return secret_key


def setup_snowball(
    manifest_path: os.PathLike,
    unlock_code: str,
    device_ip: str
) -> tuple[str, str, str]:

    if is_unlocked(manifest_path, unlock_code, device_ip):
        profile = get_snowballedge_profile(unlock_code)
        if not profile:
            print('Snowball is already unlocked but not configured on this computer.' \
                'Please run `snowballEdge configure` command and follow its instructions')
    else:
        profile = unlock_snowball(manifest_path, unlock_code, device_ip)
    
    access_key = get_snowball_access_key(profile)
    secret_key = get_snowball_secret_key(profile, access_key)

    return profile, access_key, secret_key


def get_awscli_profile(
    access_key: str
) -> str:

    profile_path = pathlib.Path.home().joinpath('.aws/credentials')

    if not profile_path.is_file:
        return None
    else:
        with open(profile_path) as file:
            cfg = ConfigParser()
            cfg.read_file(file)

        for key in cfg:
            if 'aws_access_key_id' in cfg[key]:
                if cfg[key]['aws_access_key_id'] == access_key:
                    return key


def config_awscli(
    access_key: str,
    secret_key: str
) -> str:

    existing_profile = get_awscli_profile(access_key)

    if existing_profile:
        return existing_profile

    profile = f'cli-{datetime.now().strftime("%Y%m%d")}'

    config_base_cmd = [
        'aws', 'configure',
        '--profile', profile,
        'set'
    ]

    params = [
        ['aws_access_key_id', access_key],
        ['aws_secret_access_key', secret_key],
        ['region', 'snow']
    ]

    for param in params:
        subprocess.run(config_base_cmd + param)
    
    return profile


def check_snowball_access(profile, ip):

    s3ls_cmd = [
        'aws', 's3', 'ls',
        '--profile', profile,
        '--endpoint', f'http://{ip}:8080',
    ]

    try:
        subprocess.run(s3ls_cmd, capture_output=True, timeout=1)
    except subprocess.TimeoutExpired as e:
        print(f'Snowball is not responding. Check config and IP.\n{" ".join(e.args)}')
    else:
        return True


def main():
    parser = _make_parser()
    args = parser.parse_args()

    snowball_profile, access_key, secret_key = setup_snowball(args.manifest, args.unlock_code, args.ip)
    awscli_profile = config_awscli(access_key, secret_key)

    if check_snowball_access(awscli_profile, args.ip):
        print(f'SnowballEdge accessible via AWS CLI using:\nProfile: {awscli_profile}\nIP: http:\\\\{args.ip}:8080)')


if __name__ == '__main__':
    main()
