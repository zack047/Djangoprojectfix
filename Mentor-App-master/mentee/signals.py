from django.contrib.auth import get_user_model
User = get_user_model()
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import (Profile, Mentor, Mentee, MentorMentee, InternshipPBL, StudentProfileOverview, PaperPublication,
                     SemesterResult, SportsCulturalEvent, CertificationCourse, OtherEvent, MentorMenteeInteraction,
                     Notification, ReminderLog, ActivityLog)
from .ai_utils import generate_ai_summary
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_save, pre_delete, pre_save
from .request_local import get_current_request
import json
from django.forms.models import model_to_dict
from django.db.models.fields.files import FieldFile


@receiver(post_save, sender=User)
def create_profile(sender, instance, **kwargs):
    Profile.objects.get_or_create(
        user=instance,
        defaults={
            "moodle_id": instance.username,
        }
    )

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

@receiver(post_save, sender=User)
def create_student_profile_overview(sender, instance, created, **kwargs):
    if created:
        StudentProfileOverview.objects.create(user=instance)

# @receiver(post_save, sender=MentorMenteeInteraction)
# def generate_summary(sender, instance, created, **kwargs):
#     if instance.agenda and not instance.ai_summary:
#         instance.ai_summary = generate_ai_summary(instance.agenda)
#         instance.save(update_fields=["ai_summary"])


def notify_mentors_on_upload(user):
    """
    If there was a reminder in last 30 days, notify mentor that mentee has uploaded something.
    """
    try:
        mentee = Mentee.objects.get(user=user)
    except Mentee.DoesNotExist:
        return

    now = timezone.now()
    cutoff = now - timedelta(days=30)

    # Check if any reminder exists recently
    recent_reminders = ReminderLog.objects.filter(mentee=mentee, last_sent_at__gte=cutoff)

    if not recent_reminders.exists():
        return

    # For all mentors mapped to this mentee, notify
    mappings = MentorMentee.objects.filter(mentee=mentee).select_related("mentor__user")

    for mapping in mappings:
        mentor_user = mapping.mentor.user

        # In-app notification
        Notification.objects.create(
            user=mentor_user,
            message=f"✅ {user.username} - {user.profile.student_name} has uploaded/updated a document after your reminder."
        )

        # Email (optional)
        if mentor_user.email:
            send_mail(
                subject="Mentee Document Update",
                message=(
                    f"Dear {mentor_user.username},\n\n"
                    f"Your mentee {user.username} - {user.profile.student_name} has uploaded/updated a document after your reminder.\n\n"
                    f"Regards,\nMentorConnect Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentor_user.email],
                fail_silently=True,
            )


@receiver(post_save, sender=InternshipPBL)
def internship_uploaded(sender, instance, created, **kwargs):
    if instance.certificate:
        notify_mentors_on_upload(instance.user)


@receiver(post_save, sender=SemesterResult)
def marksheet_uploaded(sender, instance, created, **kwargs):
    if instance.marksheet:
        notify_mentors_on_upload(instance.user)


@receiver(post_save, sender=CertificationCourse)
def certcourse_uploaded(sender, instance, created, **kwargs):
    if instance.certificate:
        notify_mentors_on_upload(instance.user)


@receiver(post_save, sender=PaperPublication)
def publication_uploaded(sender, instance, created, **kwargs):
    if instance.certificate:
        notify_mentors_on_upload(instance.user)


@receiver(post_save, sender=SportsCulturalEvent)
def sports_uploaded(sender, instance, created, **kwargs):
    if instance.certificate:
        notify_mentors_on_upload(instance.user)


@receiver(post_save, sender=OtherEvent)
def other_uploaded(sender, instance, created, **kwargs):
    if instance.certificate:
        notify_mentors_on_upload(instance.user)


# small cache to store old instance snapshots before save
_old_instance_cache = {}

def _in_mentee_app(sender):
    # only log models defined in the mentee app (avoid recursion)
    return sender.__module__.startswith("mentee.")

def _get_request_info():
    req = get_current_request()
    if not req:
        return {"ip": None, "ua": None, "path": None, "user": None}
    ip = req.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or req.META.get("REMOTE_ADDR")
    ua = req.META.get("HTTP_USER_AGENT", "")[:255]
    path = getattr(req, "path", None)
    return {"ip": ip, "ua": ua, "path": path, "user": getattr(req, "user", None)}


def safe_dict(instance):
    """Convert model_to_dict output into JSON-safe values."""
    data = model_to_dict(instance)

    for field, value in data.items():

        # FILE or IMAGE
        if isinstance(value, FieldFile):
            if value and value.name:  # File exists
                try:
                    data[field] = value.url  # Safe access
                except ValueError:
                    data[field] = value.name
            else:
                data[field] = None  # No file uploaded
            continue

        else:
            # Check JSON serializability
            try:
                json.dumps(value)
            except Exception:
                data[field] = str(value)

    return data


def get_diff(old, new):
    """Return dict of only changed fields with before → after values."""
    if not old or not new:
        return None

    diff = {}
    for key in new.keys():
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            diff[key] = {"old": old_val, "new": new_val}

    return diff or None


def _create_log(user, action, module, instance, details=None, old_data=None, new_data=None, ip=None, ua=None, path=None):
    # avoid logging ActivityLog itself
    if instance.__class__.__name__ == "ActivityLog":
        return
    ActivityLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        module=module,
        details=details or str(instance),
        old_data=old_data,
        new_data=new_data,
        ip_address=ip,
        browser=ua,
        request_path=path,
        timestamp=timezone.now(),
    )

# ---------- cache old instance before saving so we can diff on post_save ----------
@receiver(pre_save)
def cache_old_instance(sender, instance, **kwargs):
    if not _in_mentee_app(sender):
        return
    if not getattr(instance, "pk", None):
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        _old_instance_cache[(sender.__name__, instance.pk)] = safe_dict(old)
    except sender.DoesNotExist:
        pass

# ---------- post_save: created or updated ----------
@receiver(post_save)
def log_post_save(sender, instance, created, **kwargs):
    if not _in_mentee_app(sender):
        return

    req_info = _get_request_info()
    user = req_info.get("user") or getattr(instance, "user", None) or getattr(instance, "mentor", None)
    module_name = sender.__name__

    if created:
        _create_log(
            user=user,
            action="Created",
            module=module_name,
            instance=instance,
            new_data=safe_dict(instance),
            ip=req_info.get("ip"),
            ua=req_info.get("ua"),
            path=req_info.get("path"),
        )
    else:
        old_data = _old_instance_cache.pop((sender.__name__, instance.pk), None)
        new_data = safe_dict(instance)
        changes = get_diff(old_data, new_data)

        # Special-case: Msg approval detection
        if sender.__name__ == "Msg":
            # attempt to detect approval flip
            if old_data and old_data.get("is_approved") is False and new_data.get("is_approved") is True:
                approver = user
                _create_log(
                    user=approver,
                    action="Approved Message",
                    module="Chat",
                    instance=instance,
                    old_data=old_data,
                    new_data=new_data,
                    details=f"Message ID {instance.pk} approved",
                    ip=req_info.get("ip"),
                    ua=req_info.get("ua"),
                    path=req_info.get("path"),
                )

        _create_log(
            user=user,
            action="Updated",
            module=module_name,
            instance=instance,
            old_data=old_data,
            new_data=new_data,
            details=f"Changed fields: {', '.join(changes.keys())}" if changes else "Updated",
            ip=req_info.get("ip"),
            ua=req_info.get("ua"),
            path=req_info.get("path"),
        )

# ---------- pre_delete: log delete ----------
@receiver(pre_delete)
def log_pre_delete(sender, instance, **kwargs):
    if not _in_mentee_app(sender):
        return

    req_info = _get_request_info()
    user = req_info.get("user") or getattr(instance, "user", None) or getattr(instance, "mentor", None)
    module_name = sender.__name__
    _create_log(
        user=user,
        action="Deleted",
        module=module_name,
        instance=instance,
        old_data=safe_dict(instance),
        new_data=None,
        ip=req_info.get("ip"),
        ua=req_info.get("ua"),
        path=req_info.get("path"),
    )

# ---------- login / logout ----------
@receiver(user_logged_in)
def log_user_login(sender, user, request, **kwargs):
    ActivityLog.objects.create(
        user=user,
        action="User Logged In",
        module="Authentication",
        details=f"User {user.get_username()} logged in",
        old_data=None,
        new_data=None,
        ip_address=(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")),
        browser=request.META.get("HTTP_USER_AGENT", "")[:255],
        request_path=getattr(request, "path", None),
        timestamp=timezone.now()
    )

@receiver(user_logged_out)
def log_user_logout(sender, user, request, **kwargs):
    ActivityLog.objects.create(
        user=user,
        action="User Logged Out",
        module="Authentication",
        details=f"User {user.get_username()} logged out",
        old_data=None,
        new_data=None,
        ip_address=(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")),
        browser=request.META.get("HTTP_USER_AGENT", "")[:255],
        request_path=getattr(request, "path", None),
        timestamp=timezone.now()
    )
