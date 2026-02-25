from .models import (Profile, InternshipPBL, Project, CertificationCourse, PaperPublication, SportsCulturalEvent,
    OtherEvent, SemesterResult, EducationalDetail, StudentInterest, StudentProfileOverview)
from django.utils import timezone
from zoneinfo import ZoneInfo
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def compute_profile_completeness(user):
    """
    Returns (score_percentage, items_list)
    items_list = [{"label": "...", "done": True/False}]
    """

    items = []

    # 1. Basic profile
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        profile = None

    def filled(val):
        return bool(val)

    # Basic fields
    items.append({"label": "Name", "done": profile and filled(profile.student_name)})
    items.append({"label": "Branch/Year/Semester", "done": profile and filled(profile.branch) and filled(profile.year) and filled(profile.semester)})
    items.append({"label": "Contact & Email", "done": profile and filled(profile.contact_number) and filled(user.email)})
    items.append({"label": "Career Domain", "done": profile and filled(profile.career_domain)})
    items.append({"label": "About Me", "done": profile and filled(profile.about_me)})

    # 2. Education
    items.append({"label": "Pre-Engineering Education (SSC/HSC/Diploma)", "done": EducationalDetail.objects.filter(user=user).exists()})
    items.append({"label": "Semester Results", "done": SemesterResult.objects.filter(user=user).exists()})

    # 3. Experience / Projects / Certifications / Publications
    items.append({"label": "At least one Internship/PBL", "done": InternshipPBL.objects.filter(user=user).exists()})
    items.append({"label": "At least one Project", "done": Project.objects.filter(user=user).exists()})
    items.append({"label": "At least one Certification/Course", "done": CertificationCourse.objects.filter(user=user).exists()})
    items.append({"label": "At least one Paper/Publication", "done": PaperPublication.objects.filter(user=user).exists()})

    # 4. Achievements & Activities
    sports_or_other = SportsCulturalEvent.objects.filter(user=user).exists() or OtherEvent.objects.filter(user=user).exists()
    items.append({"label": "Sports/Cultural/Other Achievements", "done": sports_or_other})

    # 5. Interests & Goals
    items.append({"label": "Student Interests", "done": StudentInterest.objects.filter(student=user).exists()})
    items.append({"label": "Long Term Goal", "done": user.longtermgoal_set.exists()})

    # 6. Overview fields
    overview = StudentProfileOverview.objects.filter(user=user).first()
    items.append({"label": "Professional Summary", "done": overview and filled(overview.profile_summary)})
    items.append({"label": "Key Skills", "done": overview and filled(overview.key_skills)})

    total = len(items)
    done_count = sum(1 for i in items if i["done"])
    score = int((done_count / total) * 100) if total > 0 else 0

    # Optionally store score
    if overview:
        overview.completeness_score = score
        overview.save(update_fields=["completeness_score"])

    return score, items


def get_document_progress(user):
    """
    Returns (completed_count, total_required, has_pending)
    """

    has_internship = InternshipPBL.objects.filter(
        user=user, certificate__isnull=False
    ).exclude(certificate="").exists()

    has_marksheet = SemesterResult.objects.filter(
        user=user, marksheet__isnull=False
    ).exclude(marksheet="").exists()

    has_project = Project.objects.filter(user=user).exists()

    has_certification = CertificationCourse.objects.filter(
        user=user, certificate__isnull=False
    ).exclude(certificate="").exists()

    has_publication = PaperPublication.objects.filter(
        user=user, certificate__isnull=False
    ).exclude(certificate="").exists()

    has_sports = SportsCulturalEvent.objects.filter(
        user=user, certificate__isnull=False
    ).exclude(certificate="").exists()

    has_other = OtherEvent.objects.filter(
        user=user, certificate__isnull=False
    ).exclude(certificate="").exists()

    completed_count = sum([
        has_internship,
        has_marksheet,
        has_project,
        has_certification,
        has_publication,
        has_sports,
        has_other,
    ])

    total_required = 7
    has_pending = completed_count < total_required

    return completed_count, total_required, has_pending


IST = ZoneInfo("Asia/Kolkata")

def to_ist(dt):
    """Convert UTC datetime → IST, return formatted string."""
    if not dt:
        return ""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt.astimezone(IST).strftime("%d-%m-%Y %H:%M:%S")


def mentee_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # login_required will handle if you also use it; otherwise redirect yourself
            return redirect("login")  # change to your mentee login url name

        # strict mentee check (recommended)
        if not hasattr(request.user, "mentee") or not request.user.is_mentee:
            messages.error(request, "You are not authorized to access the mentee portal. Please use mentor login page.")
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return _wrapped


def mentor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login1")  # change to your mentor login url name

        if not hasattr(request.user, "mentor") or not request.user.is_mentor:
            messages.error(request, "You are not authorized to access the mentor portal. Please use mentee login page")
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return _wrapped


def mentor_or_staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login1")
        is_mentor = hasattr(request.user, "mentor") and getattr(request.user, "is_mentor", False)
        if not (request.user.is_staff or is_mentor):
            messages.error(request, "You are not authorized to access this page.")
            return redirect("account1")
        return view_func(request, *args, **kwargs)
    return _wrapped
