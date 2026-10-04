"""Opaque, revocable installation accounts; secrets never enter operational evidence."""
from datetime import timedelta
import hashlib
import hmac
import secrets
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, insert, select, update

from .product_models import now, stamp
from .product_store import attempts, digest, invitations, sessions, users

COOKIE = 'shorefront_session'
SESSION_SECONDS = 8 * 60 * 60


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1,
                           maxmem=256 * 1024 * 1024, dklen=32)
    return f'scrypt17${salt}${value.hex()}'


def password_valid(password: str, stored: str) -> bool:
    try:
        scheme, salt, _ = stored.split('$')
        return scheme == 'scrypt17' and hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def public_user(user):
    return {key: user[key] for key in ('id', 'email', 'name', 'role', 'active')}


def require_origin(request: Request, origin: str):
    if request.headers.get('origin') != origin:
        raise HTTPException(403, 'Request origin is not authorized')


def identify(connection, request: Request, *, mutation=False):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 256:
        raise HTTPException(401, 'Sign in to your Shorefront workspace')
    session = connection.execute(select(sessions).where(sessions.c.digest == digest(token), sessions.c.expires_at > stamp(now()))).mappings().first()
    user = connection.execute(select(users).where(users.c.id == session['user_id'], users.c.active == 1)).mappings().first() if session else None
    if not user:
        raise HTTPException(401, 'Session expired or access revoked; sign in again')
    if mutation and not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode(), session['csrf'].encode()):
        raise HTTPException(403, 'Session security token is missing or invalid')
    return dict(user), dict(session)


def require_admin(user):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator permission required')


def create_user(connection, signup, role):
    if connection.execute(select(users.c.id).where(users.c.email == signup.email)).first():
        raise HTTPException(409, 'An account already exists for this email')
    user = {'id': str(uuid4()), 'email': signup.email, 'name': signup.display_name,
            'password': password_hash(signup.password), 'role': role, 'active': 1, 'created_at': stamp(now())}
    connection.execute(insert(users).values(**user))
    return user


def start_session(connection, user, response: Response, secure: bool):
    connection.execute(delete(sessions).where(sessions.c.expires_at <= stamp(now())))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    connection.execute(insert(sessions).values(digest=digest(token), user_id=user['id'], csrf=csrf,
                                               expires_at=stamp(now() + timedelta(seconds=SESSION_SECONDS))))
    response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite='strict',
                        max_age=SESSION_SECONDS, path='/')
    return {'user': public_user(user), 'csrf_token': csrf}


def login_attempt(connection, email, password, client_ip):
    # Both per-account and per-client ceilings survive service restart. Prune only
    # expired windows, and commit unsuccessful attempts before returning HTTP 401.
    current = stamp(now())
    connection.execute(delete(attempts).where(attempts.c.expires_at <= current))
    keys = [(digest('email:' + email), 5), (digest('client:' + client_ip), 25)]
    entries = {}
    for key, limit in keys:
        row = connection.execute(select(attempts).where(attempts.c.key == key)).mappings().first()
        if row and row['count'] >= limit:
            return None, 429
        entries[key] = row
    user = connection.execute(select(users).where(users.c.email == email, users.c.active == 1)).mappings().first()
    stored = user['password'] if user else 'scrypt17$' + '00' * 16 + '$' + '00' * 32
    valid = password_valid(password, stored)
    for key, _ in keys:
        if valid:
            # Do not clear a client's abusive history merely by signing into one account.
            if key == keys[0][0]:
                connection.execute(delete(attempts).where(attempts.c.key == key))
        elif entries[key]:
            connection.execute(update(attempts).where(attempts.c.key == key).values(count=entries[key]['count'] + 1))
        else:
            connection.execute(insert(attempts).values(key=key, count=1, expires_at=stamp(now() + timedelta(minutes=5))))
    return (dict(user), 200) if valid and user else (None, 401)
