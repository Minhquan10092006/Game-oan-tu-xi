"""Start the prepared classroom server: python run_classroom.py --address 192.168.1.10."""
import os
from pathlib import Path
import secrets
import sys


def main():
    # Dedicated persistent key: no secret needs to be copied by a teacher.
    folder = Path(__file__).resolve().parent / 'private-exports'
    folder.mkdir(exist_ok=True)
    keyfile = folder / 'classroom-secret.key'
    try:
        with keyfile.open('x', encoding='utf-8') as stream:
            stream.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    os.environ['DJANGO_SECRET_KEY'] = keyfile.read_text(encoding='utf-8').strip()
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.classroom_settings'
    from django.core.management import execute_from_command_line
    execute_from_command_line([sys.argv[0], 'classroom', *sys.argv[1:]])


if __name__ == '__main__':
    main()
