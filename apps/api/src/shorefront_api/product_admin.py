"""Installation-operator recovery. Requires trusted shell/database access, never HTTP."""
import argparse
from datetime import timedelta
from getpass import getpass

from sqlalchemy import delete, select, update

from .config import setting
from .product_auth import password_hash
from .product_models import now, stamp
from .product_store import ProductStore, installation, sessions, users
from .storage import default_database_url


def reset_password(store, email: str, password: str, reason: str):
    if not 15 <= len(password) <= 128 or not reason.strip():
        raise ValueError('Use a 15–128 character password and record the verification reason')
    with store.transaction() as connection:
        user = connection.execute(select(users).where(users.c.email == email.strip().casefold(), users.c.active == 1)).mappings().first()
        if not user:
            raise ValueError('Active account not found; recovery does not reactivate revoked access')
        connection.execute(update(users).where(users.c.id == user['id']).values(password=password_hash(password)))
        connection.execute(delete(sessions).where(sessions.c.user_id == user['id']))
        store.add_audit(connection, 'installation-operator', 'account.recovered', {'user_id': user['id'], 'reason': reason.strip()})


def reopen_setup(store, reason: str):
    if not reason.strip():
        raise ValueError('Record the verification reason before reopening setup')
    with store.transaction() as connection:
        if connection.execute(select(users.c.id).limit(1)).first():
            raise ValueError('Installation already initialized; recover an existing account instead')
        expires_at = stamp(now() + timedelta(hours=24))
        connection.execute(update(installation).where(installation.c.id == 1).values(bootstrap_expires_at=expires_at))
        store.add_audit(connection, 'installation-operator', 'installation.setup_reopened',
                        {'reason': reason.strip(), 'bootstrap_expires_at': expires_at})


def main():
    parser = argparse.ArgumentParser(description='Recover a verified Shorefront account or reopen initial setup using trusted local access.')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--email', help='Account to recover; all its sessions will be revoked')
    action.add_argument('--reopen-setup', action='store_true', help='Renew initial setup for 24 hours, only before the first account exists')
    parser.add_argument('--reason', required=True, help='How the account owner was verified out of band')
    args = parser.parse_args()
    owner = setting('INSTALLATION_ID', '')
    if not owner:
        parser.error('Set SHOREFRONT_INSTALLATION_ID and the exact customer DATABASE_URL first')
    store = ProductStore(default_database_url(), owner)
    try:
        store.initialize(migrate=False)
        if args.reopen_setup:
            reopen_setup(store, args.reason)
        else:
            password = getpass('New passphrase (not echoed): ')
            if password != getpass('Repeat passphrase: '):
                parser.error('Passphrases do not match')
            reset_password(store, args.email, password, args.reason)
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        store.engine.dispose()
    if args.reopen_setup:
        print('Initial setup reopened for 24 hours. The configured bootstrap secret is still required.')
    else:
        print('Account recovered; all previous sessions revoked. No password was printed or emailed.')


if __name__ == '__main__':
    main()
