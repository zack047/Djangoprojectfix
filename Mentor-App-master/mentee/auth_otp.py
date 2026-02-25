import secrets
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.crypto import constant_time_compare, salted_hmac

OTP_DIGITS = 6
OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30

REG_MENTEE_OTP_SESSION_KEY = "register_otp_mentee"
REG_MENTOR_OTP_SESSION_KEY = "register_otp_mentor"


def _generate_numeric_otp(length: int = OTP_DIGITS) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _otp_hash(scope: str, user_id: int, otp: str) -> str:
    return salted_hmac("mentorconnect-login-otp", f"{scope}:{user_id}:{otp}").hexdigest()


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        local_masked = local[0] + "*"
    else:
        local_masked = local[:2] + ("*" * (len(local) - 2))
    return f"{local_masked}@{domain}"


def create_login_otp_challenge(
    request,
    user,
    session_key: str,
    scope: str,
    verify_url: str = "",
    portal_label: str = "MentorConnect",
):
    now_ts = int(time.time())
    existing = request.session.get(session_key, {})
    if (
        existing
        and int(existing.get("user_id", 0)) == int(user.pk)
        and now_ts < int(existing.get("expires_at", 0))
    ):
        sent_at = int(existing.get("sent_at", 0))
        wait_seconds = OTP_RESEND_COOLDOWN_SECONDS - (now_ts - sent_at)
        if wait_seconds > 0:
            return mask_email(user.email), False, wait_seconds

    otp = _generate_numeric_otp()
    payload = {
        "user_id": user.pk,
        "otp_hash": _otp_hash(scope, user.pk, otp),
        "expires_at": now_ts + OTP_TTL_SECONDS,
        "attempts_left": OTP_MAX_ATTEMPTS,
        "sent_at": now_ts,
    }
    request.session[session_key] = payload
    request.session.modified = True

    subject = "Your MentorConnect Verification OTP"
    html_message = render_to_string(
        "emails/login_otp_email.html",
        {
            "username": user.username,
            "otp": otp,
            "expiry_minutes": OTP_TTL_SECONDS // 60,
            "verify_url": verify_url,
            "portal_label": portal_label,
        },
    )
    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        to=[user.email],
    )
    email.attach_alternative(html_message, "text/html")
    email.send(fail_silently=False)

    return mask_email(user.email), True, 0


def get_login_otp_state(request, session_key: str):
    return request.session.get(session_key)


def clear_login_otp_state(request, session_key: str):
    if session_key in request.session:
        del request.session[session_key]
        request.session.modified = True


def verify_login_otp(request, user_model, session_key: str, scope: str, otp_input: str):
    payload = get_login_otp_state(request, session_key)
    if not payload:
        return False, "missing", None

    if not otp_input or not otp_input.isdigit():
        return False, "invalid_format", None

    if int(time.time()) > int(payload.get("expires_at", 0)):
        clear_login_otp_state(request, session_key)
        return False, "expired", None

    attempts_left = int(payload.get("attempts_left", 0))
    if attempts_left <= 0:
        clear_login_otp_state(request, session_key)
        return False, "locked", None

    expected_hash = payload.get("otp_hash", "")
    actual_hash = _otp_hash(scope, int(payload["user_id"]), otp_input)

    if not constant_time_compare(expected_hash, actual_hash):
        payload["attempts_left"] = attempts_left - 1
        request.session[session_key] = payload
        request.session.modified = True
        if payload["attempts_left"] <= 0:
            clear_login_otp_state(request, session_key)
            return False, "locked", None
        return False, "invalid", None

    user = user_model.objects.filter(pk=payload["user_id"]).first()
    if not user:
        clear_login_otp_state(request, session_key)
        return False, "missing_user", None

    clear_login_otp_state(request, session_key)
    return True, "ok", user
