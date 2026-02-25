import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from ..forms import (MenteeRegisterForm, ProfileUpdateForm, InternshipPBLForm, ProjectForm, SportsCulturalForm,
                     OtherEventForm, CertificationCourseForm, PaperPublicationForm, SelfAssessmentForm,
                     LongTermGoalForm, SubjectOfInterestForm, EducationalDetailForm, SemesterResultForm, MeetingForm,
                     QueryForm, SendForm,ReplyForm, ChatReplyForm, StudentProfileOverviewForm)
from ..models import (Profile, Msg, Conversation, Reply, InternshipPBL, Project, SportsCulturalEvent, OtherEvent,
                      CertificationCourse, PaperPublication, SelfAssessment, LongTermGoal, SubjectOfInterest,
                      EducationalDetail, SemesterResult, Meeting, Mentor, Mentee, StudentInterest, Query,
                      MentorMenteeInteraction, StudentProfileOverview, Notification)
from ..utils import compute_profile_completeness, mentee_required
from django.contrib.auth import get_user_model
import logging
logger = logging.getLogger(__name__)
User = get_user_model()
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.urls import reverse
import traceback
from django.views.generic import (View, TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView)
from django.core.mail import send_mail
from django.urls import reverse_lazy
from .. import models
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Count, Q
from ..render import Render
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseForbidden
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import zipfile
from collections import defaultdict
import calendar
from PIL import Image
import pypandoc
from django.core.mail import EmailMultiAlternatives
import uuid
from django.template.loader import render_to_string
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.forms.models import model_to_dict


class MenteeOnlyView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return hasattr(self.request.user, "mentee") and self.request.user.is_mentee

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return redirect("home")
        return super().handle_no_permission()


def home(request):
    """Home landing page"""
    return render(request, 'home.html')

#-------------------Mentor-Mentee interaction page logic starts-----------------------
@method_decorator(login_required, name="dispatch")
class AccountList(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        # Only mentees can access this view
        return self.request.user.is_mentee

    def get(self, request, *args, **kwargs):
        try:
            mentee = request.user.mentee
        except Mentee.DoesNotExist:
            return render(request, "menti/account.html", {"user_meeting_data": [], "is_mentor_view": False})

            # Get the one assigned mentor
        mapping = getattr(mentee, "assigned_mentor", None)
        if not mapping:
            return render(request, "menti/account.html", {"user_meeting_data": [], "is_mentor_view": False})

        mentor = mapping.mentor if mapping else None
        now = timezone.localtime(timezone.now())
        meetings = Meeting.objects.filter(mentee=mentee, mentor=mentor)

        meeting = meetings.first()
        can_join = can_feedback = feedback_exists = False
        if meeting:
            start = meeting.meeting_datetime
            end = meeting.meeting_end_datetime
            can_join = start <= now <= end
            feedback_exists = hasattr(meeting, "feedback_obj")
            can_feedback = now > end and not feedback_exists

        user_meeting_data = [{
            "user": mentor.user,
            "meeting": meeting,
            "can_join": can_join,
            "can_feedback": can_feedback,
            "feedback_exists": feedback_exists,
        }]

        # ✅ ✅ ✅ INTERACTIONS WHERE THIS MENTEE WAS PRESENT
        present_interactions_qs = MentorMenteeInteraction.objects.filter(
            mentees=request.user
        ).select_related("mentor").order_by("-date")
        paginator = Paginator(present_interactions_qs, 5)
        page_number = request.GET.get("page")
        present_interactions = paginator.get_page(page_number)

        # ✅ Total interactions under this mentor (for % calculation)
        total_interactions = MentorMenteeInteraction.objects.filter(
            mentor=mentor.user
        ).count()

        interaction_rows = []
        start_index = present_interactions.start_index()

        for idx, interaction in enumerate(present_interactions, start=start_index):

            # ✅ Mentor Name (from Mentor model)
            if hasattr(interaction.mentor, "mentor") and interaction.mentor.mentor.name:
                mentor_name = interaction.mentor.mentor.name
            else:
                mentor_name = interaction.mentor.username

            # ✅ Attendance %
            percent = round((idx / total_interactions) * 100, 2) if total_interactions else 0

            interaction_rows.append({
                "sr_no": idx,
                "date": interaction.date.strftime("%d-%m-%Y"),
                "semester": interaction.semester,
                "moodle_id": request.user.profile.moodle_id,
                "student_name": request.user.profile.student_name,
                "agenda": interaction.agenda,
                "mentor_name": mentor_name,
                "attendance_percent": percent,
            })

        # ✅ Overall attendance % for this mentee
        present_count = present_interactions.paginator.count
        overall_percent = round((present_count / total_interactions) * 100, 2) if total_interactions else 0

        # ✅ Graph data (date vs attendance point)
        attendance_graph_labels = []
        attendance_graph_values = []

        for i in present_interactions_qs.order_by("date"):
            attendance_graph_labels.append(i.date.strftime("%d-%m-%y"))
            attendance_graph_values.append(100)  # Present = 100%

        # ✅ MONTHLY ATTENDANCE BREAKDOWN
        monthly_present = defaultdict(int)
        monthly_total = defaultdict(int)

        all_interactions = MentorMenteeInteraction.objects.filter(
            mentor=mentor.user
        )

        for i in all_interactions:
            key = i.date.strftime("%Y-%m")
            monthly_total[key] += 1

        for i in present_interactions_qs:
            key = i.date.strftime("%Y-%m")
            monthly_present[key] += 1

        monthly_attendance = []
        for key in sorted(monthly_total.keys()):
            year, month = key.split("-")
            month_name = calendar.month_name[int(month)]
            present = monthly_present.get(key, 0)
            total = monthly_total.get(key, 0)
            percent = round((present / total) * 100, 2) if total else 0

            monthly_attendance.append({
                "month": f"{month_name} {year}",
                "present": present,
                "total": total,
                "percent": percent
            })
        # ✅ FUTURE ATTENDANCE PREDICTION (MOVING AVERAGE + TREND)

        prediction_percent = 0
        risk_level = "Safe"

        if monthly_attendance:
            # ✅ Take last 3 months (or fewer if not available)
            recent_months = monthly_attendance[-3:]

            values = [m["percent"] for m in recent_months]

            # ✅ Moving Average Prediction
            prediction_percent = round(sum(values) / len(values), 2)

            # ✅ Trend adjustment
            if len(values) >= 2:
                trend = values[-1] - values[0]
                prediction_percent = round(prediction_percent + (trend / 3), 2)

            # ✅ Boundaries
            prediction_percent = max(0, min(100, prediction_percent))

            # ✅ Risk Label
            if prediction_percent >= 85:
                risk_level = "Excellent"
            elif 75 <= prediction_percent < 85:
                risk_level = "Stable"
            elif 60 <= prediction_percent < 75:
                risk_level = "Warning"
            else:
                risk_level = "Critical"

        # ✅ PERFORMANCE INSIGHTS (RULE-BASED SMART LOGIC)
        if overall_percent >= 85:
            ai_insight = "✅ Excellent consistency! You are highly engaged with mentor interactions."
        elif 75 <= overall_percent < 85:
            ai_insight = "⚠ Good participation, but you can improve slightly for better academic tracking."
        elif 60 <= overall_percent < 75:
            ai_insight = "⚠ Attendance is moderate. Regular interactions will boost your performance."
        else:
            ai_insight = "❌ Critical attendance level. Immediate improvement is strongly recommended."

        # ✅ ADD THESE TO CONTEXT
        context = {
            "user_meeting_data": user_meeting_data,
            "interaction_rows": interaction_rows,
            "page_obj": present_interactions,
            "overall_percent": overall_percent,
            "attendance_graph_labels": attendance_graph_labels,
            "attendance_graph_values": attendance_graph_values,
            "monthly_attendance": monthly_attendance,  # ✅ NEW
            "ai_insight": ai_insight,  # ✅ NEW
            "prediction_percent": prediction_percent,     # ✅ FUTURE PREDICTION
            "risk_level": risk_level,
            "now": now,
            "is_mentor_view": False,
        }

        return render(request, "menti/account.html", context)
#-------------------Mentor-Mentee interaction page logic ends-----------------------

def register(request):
    """Controls the register module"""

    registered = False

    if request.method == 'POST':

        form1 = MenteeRegisterForm(request.POST)

        if form1.is_valid():
            user = form1.save()
            user.is_mentee = True
            user.save()

            registered = True
            messages.success(request, f'Your account has been created! You will now be able to log in')
            return redirect('login')
    else:
        form1 = MenteeRegisterForm()

    return render(request, 'menti/register.html', {'form1': form1})


def user_login(request):
    if request.user.is_authenticated:
        # optional: redirect already logged-in user
        return redirect("mentee-home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.warning(request, "Invalid login details")
            return redirect("login")

        # role check: mentee portal only
        if not (user.is_mentee and hasattr(user, "mentee")):
            messages.error(request, "This login is for mentees only. Please use the mentor login page.")
            return redirect("login")  # or redirect("login1") if you want to send them to mentor login

        if not user.is_active:
            messages.error(request, "Your account is inactive.")
            return redirect("login")

        login(request, user)
        return HttpResponseRedirect(reverse("mentee-home"))

    return render(request, "menti/login.html")


def custom_logout(request):
    logout(request)
    return redirect('login')


#-----------------forget password logic starts---------------------
def send_forget_password_email(email, token):
    try:
        subject = 'Reset Your Password'
        reset_link = f'http://127.0.0.1:8000/change-password/{token}/'
        message = f"""
        Hi,

        You requested a password reset. Click the link below to reset your password:

        {reset_link}

        If you did not request this, please ignore this email.

        Regards,
        APSIT
        """
        email_from = settings.EMAIL_HOST_USER
        recipient_list = [email]

        send_mail(subject, message.strip(), email_from, recipient_list)
        print("✅ Reset email sent successfully.")
        return True

    except Exception as e:
        print(f"❌ Email send failed: {e}")
        return False


def ForgetPassword(request):
    try:
        if request.method == 'POST':
            moodle_id = request.POST.get('username')  # still from the same form field
            print(f"Submitted moodle_id: {moodle_id}")

            # Find the profile by moodle_id
            profile_obj = Profile.objects.filter(moodle_id=moodle_id).first()
            if not profile_obj:
                messages.error(request, 'No user found with this Moodle ID.')
                return render(request, 'menti/forget-password.html', {"is_mentor_view": False})

            user_obj = profile_obj.user  # Get the related User

            # Create token and save
            token = str(uuid.uuid4())
            profile_obj.forget_password_token = token
            profile_obj.save()

            # Send email
            send_forget_password_email(user_obj.email, token)

            messages.success(request, 'Password reset link has been sent to your email.')
            return render(request, 'menti/forget-password.html', {"is_mentor_view": False})

    except Exception as e:
        print("Error in ForgetPassword:")
        traceback.print_exc()
        messages.error(request, 'Something went wrong. Please try again.')

    return render(request, 'menti/forget-password.html', {"is_mentor_view": False})


def ChangePassword(request, token):
    try:
        profile_obj = Profile.objects.filter(forget_password_token=token).first()

        if not profile_obj:
            messages.error(request, "Invalid or expired token.")
            return redirect('login')

        context = {
            'user_id': profile_obj.user.id,
            'token': token,
            "is_mentor_view": False
        }

        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('reconfirm_password')
            user_id = request.POST.get('user_id')

            if not user_id:
                messages.error(request, 'User ID is missing.')
                return render(request, 'menti/change-password.html', context)

            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return render(request, 'menti/change-password.html', context)

            user = User.objects.get(id=user_id)
            user.set_password(new_password)
            user.save()

            # Clear token after reset
            profile_obj.forget_password_token = None
            profile_obj.save()

            messages.success(request, 'Password updated successfully.')
            return redirect('login')

        # GET request
        return render(request, 'menti/change-password.html', context)

    except Exception as e:
        print("Error in ChangePassword:", e)
        messages.error(request, "Something went wrong. Try again.")
        return redirect('forget_password')
#-----------------forget password logic ends---------------------

RECENT_DAYS = 30 # configurable
today = timezone.now()
recent_from = today - timedelta(days=RECENT_DAYS)

def current_academic_year():
    year = timezone.now().year
    month = timezone.now().month
    return f"{year}-{year+1}" if month >= 7 else f"{year-1}-{year}"


@login_required
@mentee_required
def mentee_home(request):
    profile = Profile.objects.get(user=request.user)
    notifications = Notification.objects.filter(user=request.user, is_read=False).order_by("-created_at")[:10]
    recent_from = timezone.now() - timedelta(days=30)
    academic_year = current_academic_year()

    document_summary = {
        "Internships": InternshipPBL.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),

        "Projects": Project.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),

        "Sports & Cultural": SportsCulturalEvent.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),

        "Other Events": OtherEvent.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),

        "Certifications": CertificationCourse.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),

        "Publications": PaperPublication.objects.filter(
            user=request.user,
            uploaded_at__gte=recent_from,
        ).count(),
    }

    profile_incomplete = not profile.is_complete()

    return render(request, "menti/mentee_home.html", {
        "profile": profile,
        "notifications": notifications,
        "document_summary": document_summary,
        "academic_year": academic_year,
        "profile_incomplete": profile_incomplete,
        "is_mentor_view": False,
    })


@login_required
def mark_notification_read(request, notification_id):
    note = get_object_or_404(Notification, pk=notification_id, user=request.user)
    note.is_read = True
    note.save()
    return redirect("mentee-home")

#-----------------profile page logic starts--------------------
@login_required
@mentee_required
def profile(request):
    profile = request.user.profile
    user = request.user

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            # 🔑 Update User.email explicitly
            user.email = form.cleaned_data['email']
            user.save()
            profile.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=profile, initial={'email': user.email})


    return render(request, 'menti/profile.html', {'form': form, "is_mentor_view": False,})
#---------------------Profile page logic ends--------------------


@method_decorator(login_required, name="dispatch")
class MessageCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Creates new message"""

    fields = ('receipient', 'msg_content')
    model = Msg
    template_name = 'menti/messagecreate.html'

    def test_func(self):
        return self.request.user.is_mentee

    def form_valid(self, form):
        form.instance.sender = self.request.user

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 👇 Add flag here
        context['is_mentor_view'] = False

        return context

#--------------------Internship page logic starts------------------------
@login_required
@mentee_required
def internship_pbl_list(request, pk=None):
    internships = InternshipPBL.objects.filter(user=request.user).order_by("-start_date")
    internship = None
    editing = False

    if pk:  # Editing case
        internship = get_object_or_404(InternshipPBL, pk=pk, user=request.user)
        editing = True

    if request.method == "POST":
        form = InternshipPBLForm(request.POST, request.FILES, instance=internship)
        if form.is_valid():
            internship = form.save(commit=False)
            internship.user = request.user

            if internship.start_date and internship.end_date:
                internship.no_of_days = (internship.end_date - internship.start_date).days + 1

            internship.save()

            if editing:
                messages.success(request, "Internship record updated successfully.")
            else:
                messages.success(request, "Internship record added successfully.")

            return redirect("internship-pbl-list")
        else:
            print(form.errors)
    else:
        form = InternshipPBLForm(instance=internship)

    return render(request, "menti/internship_pbl_list.html", {
        "internships": internships,
        "form": form,
        "editing": editing,
        "edit_id": internship.pk if internship else None,
        "is_mentor_view": False,
    })


#download internship certificate
@login_required
@mentee_required
def download_certificate(request, pk):
    try:
        internship = InternshipPBL.objects.get(pk=pk)
        if not internship.certificate:
            raise Http404("No certificate found")

        file_path = internship.certificate.path
        file_ext = os.path.splitext(file_path)[1].lower()

        # Case 1: Already PDF
        if file_ext == ".pdf":
            file_name = f"certificate_{internship.user.username}.pdf"
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response['Content-Disposition'] = f'attachment; filename="certificate_{file_name}_{internship.user.username}"'
                return response

        # Case 2: Image (jpg/png) → Convert to PDF
        elif file_ext in [".jpg", ".jpeg", ".png"]:
            image = Image.open(file_path)
            pdf_path = os.path.join(settings.MEDIA_ROOT, f"temp_{internship.pk}.pdf")
            image.convert('RGB').save(pdf_path)

            with open(pdf_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response['Content-Disposition'] = f'attachment; filename="certificate_{internship.user.username}.pdf"'
            os.remove(pdf_path)
            return response

        # Case 3: DOCX/TXT → Convert to PDF using pypandoc
        elif file_ext in [".docx", ".txt"]:
            pdf_path = os.path.join(settings.MEDIA_ROOT, f"temp_{internship.pk}.pdf")
            pypandoc.convert_file(file_path, 'pdf', outputfile=pdf_path)

            with open(pdf_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response['Content-Disposition'] = f'attachment; filename="certificate_{internship.user.username}.pdf"'
            os.remove(pdf_path)
            return response

        else:
            raise Http404("Unsupported file type for conversion")

    except InternshipPBL.DoesNotExist:
        raise Http404("Record not found")


@login_required
@mentee_required
def download_all_certificates(request):
    internships = InternshipPBL.objects.filter(user=request.user, certificate__isnull=False)

    if not internships.exists():
        return HttpResponse("No certificates available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_internship_certificates.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in internships:
            if item.certificate:
                file_path = item.certificate.path
                file_name = os.path.basename(file_path)
                zipf.write(file_path, file_name)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def delete_internship(request, pk):
    internship = get_object_or_404(InternshipPBL, pk=pk, user=request.user)

    # Delete certificate file from storage
    if internship.certificate:
        file_path = internship.certificate.path
        if os.path.exists(file_path):
            os.remove(file_path)

    # Delete record from DB
    internship.delete()
    messages.success(request, "Record deleted successfully.")
    return redirect("internship-pbl-list")
#--------------------------Internship logic ends---------------------------

#-------------------------Projects page logic starts------------------------
@login_required
@mentee_required
def projects_view(request):
    projects = Project.objects.filter(user=request.user).order_by("-uploaded_at")

    # If editing (project_id passed in query params)
    project_id = request.GET.get("edit")
    project_to_edit = None
    if project_id:
        project_to_edit = get_object_or_404(Project, id=project_id, user=request.user)

    if request.method == "POST":
        if "delete" in request.POST:  # delete project
            project = get_object_or_404(Project, id=request.POST.get("delete"), user=request.user)
            project.delete()
            return redirect("projects-list")

        elif project_id:  # update project
            form = ProjectForm(request.POST, request.FILES, instance=project_to_edit)
            if form.is_valid():
                form.save()
                return redirect("projects-list")
        else:  # add new project
            form = ProjectForm(request.POST, request.FILES)
            if form.is_valid():
                project = form.save(commit=False)
                project.user = request.user
                project.save()
                return redirect("projects-list")
    else:
        if project_to_edit:
            form = ProjectForm(instance=project_to_edit)  # prefill form for editing
        else:
            form = ProjectForm()

    return render(
        request,
        "menti/projects_list.html",
        {
            "projects": projects,
            "form": form,
            "editing": bool(project_to_edit),
            "project_id": project_to_edit.id if project_to_edit else None,
            "is_mentor_view": False,
        },
    )
#---------------------Projects page logic ends----------------------------

#---------------------Sports page logic starts----------------------------
@login_required
@mentee_required
def sports_cultural_list(request):
    events = SportsCulturalEvent.objects.filter(user=request.user).order_by("-uploaded_at")

    editing = False
    edit_id = None

    if request.method == "POST":
        form = SportsCulturalForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.user = request.user
            event.save()
            messages.success(request, "Event added successfully.")
            return redirect("sports-and-cultural")
    else:
        form = SportsCulturalForm()

    return render(request, "menti/sports_and_cultural.html", {
        "events": events,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def download_all_sports_cultural(request):
    events = SportsCulturalEvent.objects.filter(user=request.user, certificate__isnull=False)

    if not events.exists():
        return HttpResponse("No sports & cultural certificates available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_sports_cultural_certificates.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in events:
            if item.certificate:
                file_path = item.certificate.path
                file_name = os.path.basename(file_path)
                zipf.write(file_path, file_name)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def edit_sports_cultural(request, pk):
    event = get_object_or_404(SportsCulturalEvent, pk=pk, user=request.user)
    editing = True
    edit_id = pk

    if request.method == "POST":
        form = SportsCulturalForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated successfully.")
            return redirect("sports-and-cultural")
    else:
        form = SportsCulturalForm(instance=event)

    events = SportsCulturalEvent.objects.filter(user=request.user).order_by("-uploaded_at")

    return render(request, "menti/sports_and_cultural.html", {
        "events": events,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def delete_sports_cultural(request, pk):
    event = get_object_or_404(SportsCulturalEvent, pk=pk, user=request.user)

    if event.certificate:
        event.certificate.delete(save=False)
    event.delete()
    messages.success(request, "Event deleted successfully.")
    return redirect("sports-and-cultural")
#---------------------Sports page logic ends----------------------------

#---------------------Other events page logic starts--------------------
@login_required
@mentee_required
def other_event_list(request, pk=None):
    events = OtherEvent.objects.filter(user=request.user).order_by("-uploaded_at")
    editing = False
    edit_id = None

    if pk:  # Editing mode
        event = get_object_or_404(OtherEvent, pk=pk, user=request.user)
        form = OtherEventForm(instance=event)
        editing = True
        edit_id = pk
    else:
        form = OtherEventForm()

    if request.method == "POST":
        if pk:  # Update existing record
            form = OtherEventForm(request.POST, request.FILES, instance=event)
        else:   # Add new record
            form = OtherEventForm(request.POST, request.FILES)

        if form.is_valid():
            new_event = form.save(commit=False)
            new_event.user = request.user
            new_event.save()
            return redirect("other-events")
        else:
            print(form.errors)

    return render(request, "menti/other_events.html", {
        "events": events,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def download_all_other_events(request):
    events = OtherEvent.objects.filter(user=request.user, certificate__isnull=False)

    if not events.exists():
        return HttpResponse("No other event certificates available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_other-events_certificates.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in events:
            if item.certificate:
                file_path = item.certificate.path
                file_name = os.path.basename(file_path)
                zipf.write(file_path, file_name)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def delete_other_event(request, pk):
    event = get_object_or_404(OtherEvent, pk=pk, user=request.user)

    if event.certificate:
        file_path = event.certificate.path
        if os.path.exists(file_path):
            os.remove(file_path)

    event.delete()
    messages.success(request, "Event deleted successfully.")
    return redirect("other-events")
#---------------------Other events page logic ends--------------------

#------------------Certifications page logic starts-------------------
@login_required
@mentee_required
def certification_list(request, pk=None):
    certifications = CertificationCourse.objects.filter(user=request.user).order_by("-uploaded_at")
    editing = False
    edit_id = None

    if pk:
        cert = get_object_or_404(CertificationCourse, pk=pk, user=request.user)
        form = CertificationCourseForm(instance=cert)
        editing = True
        edit_id = pk
    else:
        form = CertificationCourseForm()

    if request.method == "POST":
        if pk:
            form = CertificationCourseForm(request.POST, request.FILES, instance=cert)
        else:
            form = CertificationCourseForm(request.POST, request.FILES)

        if form.is_valid():
            new_cert = form.save(commit=False)
            new_cert.user = request.user
            new_cert.save()
            return redirect("certifications")

    return render(request, "menti/certifications.html", {
        "certifications": certifications,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def download_all_certifications(request):
    certifications = CertificationCourse.objects.filter(user=request.user, certificate__isnull=False)

    if not certifications.exists():
        return HttpResponse("No certification certificates available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_certification-courses_certificates.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in certifications:
            if item.certificate:
                file_path = item.certificate.path
                file_name = os.path.basename(file_path)
                zipf.write(file_path, file_name)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def delete_certification(request, pk):
    cert = get_object_or_404(CertificationCourse, pk=pk, user=request.user)

    if cert.certificate:
        file_path = cert.certificate.path
        if os.path.exists(file_path):
            os.remove(file_path)
    cert.delete()
    messages.success(request, "Certification deleted successfully.")
    return redirect("certifications")
#------------------Certifications page logic ends-------------------

#------------------Publications page logic starts-------------------
@login_required
@mentee_required
def publications_list(request, pk=None):
    publications = PaperPublication.objects.filter(user=request.user).order_by("-uploaded_at")
    editing = False
    edit_id = None

    if pk:
        pub = get_object_or_404(PaperPublication, pk=pk, user=request.user)
        form = PaperPublicationForm(instance=pub)
        editing = True
        edit_id = pk
    else:
        form = PaperPublicationForm()

    if request.method == "POST":
        if pk:
            form = PaperPublicationForm(request.POST, request.FILES, instance=pub)
        else:
            form = PaperPublicationForm(request.POST, request.FILES)

        if form.is_valid():
            new_pub = form.save(commit=False)
            new_pub.user = request.user
            new_pub.save()
            return redirect("publications")

    return render(request, "menti/publications.html", {
        "publications": publications,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def download_all_publications(request):
    publications = PaperPublication.objects.filter(user=request.user, certificate__isnull=False)

    if not publications.exists():
        return HttpResponse("No publication certificates available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_publications_certificates.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in publications:
            if item.certificate:
                file_path = item.certificate.path
                file_name = os.path.basename(file_path)
                zipf.write(file_path, file_name)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def delete_publication(request, pk):
    pub = get_object_or_404(PaperPublication, pk=pk, user=request.user)
    pub.delete()
    return redirect("publications")
#------------------Publications page logic ends-------------------

#------------------Self assessment page logic starts-------------------
@login_required
@mentee_required
def self_assessment(request, pk=None):
    assessments = SelfAssessment.objects.filter(user=request.user).order_by("-created_at")
    editing = False
    edit_id = None

    if pk:
        assessment = get_object_or_404(SelfAssessment, pk=pk, user=request.user)
        form = SelfAssessmentForm(instance=assessment)
        editing = True
        edit_id = pk
    else:
        form = SelfAssessmentForm()

    if request.method == "POST":
        if pk:
            form = SelfAssessmentForm(request.POST, instance=assessment)
        else:
            form = SelfAssessmentForm(request.POST)

        if form.is_valid():
            new_assessment = form.save(commit=False)
            new_assessment.user = request.user
            new_assessment.save()
            return redirect("self_assessment")

    return render(request, "menti/self_assessment.html", {
        "assessments": assessments,
        "form": form,
        "editing": editing,
        "edit_id": edit_id,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def delete_assessment(request, pk):
    assessment = get_object_or_404(SelfAssessment, pk=pk, user=request.user)
    assessment.delete()
    return redirect("self_assessment")
#------------------Self assessment page logic ends-------------------

#-----------------Long term goals and subject of interest page logic starts------------------
@login_required
@mentee_required
def long_term_goals(request, goal_edit_id=None, subject_edit_id=None):
    goals = LongTermGoal.objects.filter(user=request.user)
    subjects = SubjectOfInterest.objects.filter(user=request.user)

    # ===============================
    # LONG TERM GOAL (Add/Edit)
    # ===============================
    goal_instance = None
    if goal_edit_id:
        goal_instance = get_object_or_404(
            LongTermGoal, pk=goal_edit_id, user=request.user
        )

    if request.method == "POST" and "save_goal" in request.POST:
        goal_form = LongTermGoalForm(request.POST, instance=goal_instance)
        if goal_form.is_valid():
            goal = goal_form.save(commit=False)
            goal.user = request.user

            if goal.plan != "Other":
                goal.custom_plan = None

            goal.save()
            return redirect("long_term_goals")
    else:
        goal_form = LongTermGoalForm(instance=goal_instance)

    # DELETE GOAL
    if request.method == "POST" and "delete_goal" in request.POST:
        goal = get_object_or_404(
            LongTermGoal,
            id=request.POST.get("goal_id"),
            user=request.user
        )
        goal.delete()
        return redirect("long_term_goals")

    # ===============================
    # SUBJECT (Add/Edit)
    # ===============================
    subject_instance = None
    if subject_edit_id:
        subject_instance = get_object_or_404(
            SubjectOfInterest, pk=subject_edit_id, user=request.user
        )

    if request.method == "POST" and "save_subject" in request.POST:
        subject_form = SubjectOfInterestForm(
            request.POST, instance=subject_instance
        )
        if subject_form.is_valid():
            subject = subject_form.save(commit=False)
            subject.user = request.user
            subject.save()
            return redirect("long_term_goals")
    else:
        subject_form = SubjectOfInterestForm(instance=subject_instance)

    return render(request, "menti/long_term_goals.html", {
        "goal_form": goal_form,
        "goals": goals,
        "subjects": subjects,
        "subject_form": subject_form,
        "goal_edit_id": goal_edit_id,
        "subject_edit_id": subject_edit_id,
        "is_mentor_view": False,
    })



@login_required
@mentee_required
def delete_subject(request, pk):
    subject = get_object_or_404(SubjectOfInterest, pk=pk, user=request.user)
    subject.delete()
    return redirect("long_term_goals")
#-----------------Long term goals and subject of interest page logic ends------------------

#-----------------Educational details page logic starts------------------
@login_required
@mentee_required
def educational_details(request):
    details = EducationalDetail.objects.filter(user=request.user)

    editing = None
    if "edit" in request.GET:
        editing = get_object_or_404(EducationalDetail, id=request.GET.get("edit"), user=request.user)

    if request.method == "POST":
        # Delete action
        if "delete" in request.POST:
            detail = get_object_or_404(EducationalDetail, id=request.POST.get("delete"), user=request.user)
            detail.delete()
            messages.success(request, "Educational detail deleted successfully.")
            return redirect("educational-details")

        # Add / Update form
        form = EducationalDetailForm(request.POST, instance=editing)
        if form.is_valid():
            edu = form.save(commit=False)
            edu.user = request.user   # ✅ ensure user is attached
            edu.save()
            messages.success(request, "Educational detail saved successfully.")
            return redirect("educational-details")
        else:
            print("Form errors:", form.errors)  # ✅ Debug line
    else:
        form = EducationalDetailForm(instance=editing)

    context = {
        "details": details,
        "form": form,
        "editing": editing,
        "is_mentor_view": False,
    }
    return render(request, "menti/educational_details.html", context)
#-----------------Educational details page logic ends------------------

#-----------------Semester results page logic starts------------------
@login_required
@mentee_required
def semester_results(request):
    semesters = SemesterResult.objects.filter(user=request.user)

    # Normal add
    if request.method == "POST" and "edit_id" not in request.POST:
        form = SemesterResultForm(request.POST, request.FILES)
        if form.is_valid():
            sem = form.save(commit=False)
            sem.user = request.user
            sem.save()
            return redirect("semester_results")
    else:
        form = SemesterResultForm()

    return render(request, "menti/semester_results.html", {
        "form": form,
        "semesters": semesters,
        "editing": False,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def download_all_semester_marksheets(request):
    semesters = SemesterResult.objects.filter(user=request.user, marksheet__isnull=False)

    if not semesters.exists():
        return HttpResponse("No marksheets available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_semester_marksheets.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in semesters:
            if item.marksheet:
                file_path = item.marksheet.path
                # Optional: make filename more meaningful
                filename_in_zip = f"{request.user.username}_Sem-{item.semester}_marksheet{os.path.splitext(file_path)[1]}"
                zipf.write(file_path, filename_in_zip)

    with open(zip_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response


@login_required
@mentee_required
def edit_semester(request, pk):
    semester = get_object_or_404(SemesterResult, pk=pk, user=request.user)

    if request.method == "POST":
        form = SemesterResultForm(request.POST, request.FILES, instance=semester)
        if form.is_valid():
            form.save()
            return redirect("semester_results")
    else:
        form = SemesterResultForm(instance=semester)

    semesters = SemesterResult.objects.filter(user=request.user)
    return render(request, "menti/semester_results.html", {
        "form": form,
        "semesters": semesters,
        "editing": True,
        "edit_id": semester.pk,
        "is_mentor_view": False,
    })


@login_required
@mentee_required
def delete_semester(request, pk):
    semester = get_object_or_404(SemesterResult, pk=pk, user=request.user)
    semester.delete()
    return redirect("semester_results")
#-----------------Semester results page logic ends------------------

#-----------------Student's interest page logic starts------------------
@login_required
@mentee_required
def student_interests(request):
    obj, created = StudentInterest.objects.get_or_create(student=request.user)
    if request.method == "POST":
        selected = request.POST.getlist("interests")
        obj.interests = selected
        obj.save()

        messages.success(request, "Your interests have been saved!")
        return redirect("student_interests")

    saved_interests = []
    try:
        saved_interests = StudentInterest.objects.get(student=request.user).interests
    except StudentInterest.DoesNotExist:
        pass

    return render(request, "menti/student_interests.html", {
        "saved_interests": saved_interests,
        "is_mentor_view": False,
    })
#-----------------Student's interest page logic ends------------------

#-----------------Uploaded documents page logic starts------------------
@login_required
@mentee_required
def uploaded_documents(request):
    documents = []

    # Collect user’s uploaded files from each model
    internships = InternshipPBL.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    marksheets = SemesterResult.objects.filter(user=request.user, marksheet__isnull=False).exclude(marksheet="")
    publications = PaperPublication.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    other_events = OtherEvent.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    sports = SportsCulturalEvent.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    courses = CertificationCourse.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")

    # Normalize them into one list
    for doc in internships:
        documents.append({"category": "Internship/PBL", "name": doc.title or doc.company_name or "Internship Certificate", "file": doc.certificate})
    for doc in marksheets:
        documents.append({"category": "Marksheet", "name": f"Semester - {doc.semester} Marksheet" or "Marksheet", "file": doc.marksheet})
    for doc in publications:
        documents.append({"category": "Publication", "name": doc.title or "Publication Certificate", "file": doc.certificate})
    for doc in other_events:
        documents.append({"category": "Other Event", "name": doc.name_of_event or "Other Event Certificate", "file": doc.certificate})
    for doc in sports:
        documents.append({"category": "Sports & Cultural", "name": doc.name_of_event or "Sports Certificate", "file": doc.certificate})
    for doc in courses:
        documents.append({"category": "Certification Course", "name": doc.title or "Certification", "file": doc.certificate})

    return render(request, "menti/uploaded_documents.html", {"documents": documents, "is_mentor_view": False})


@login_required
@mentee_required
def download_all_uploaded_documents_aggregated(request):
    documents = []

    internships = InternshipPBL.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    marksheets = SemesterResult.objects.filter(user=request.user, marksheet__isnull=False).exclude(marksheet="")
    publications = PaperPublication.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    other_events = OtherEvent.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    sports = SportsCulturalEvent.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")
    courses = CertificationCourse.objects.filter(user=request.user, certificate__isnull=False).exclude(certificate="")

    for doc in internships:
        documents.append(("Internship", doc.certificate.path))
    for doc in marksheets:
        documents.append((f"Semester_{doc.semester}", doc.marksheet.path))
    for doc in publications:
        documents.append(("Publication", doc.certificate.path))
    for doc in other_events:
        documents.append(("Other_Event", doc.certificate.path))
    for doc in sports:
        documents.append(("Sports", doc.certificate.path))
    for doc in courses:
        documents.append(("Certification", doc.certificate.path))

    if not documents:
        return HttpResponse("No documents available.")

    zip_filename = f"{request.user.username}_{request.user.profile.student_name}_ALL_UPLOADED_DOCUMENTS.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for category, file_path in documents:
            if os.path.exists(file_path):
                filename = f"{category}_{os.path.basename(file_path)}".replace(" ", "_")
                zipf.write(file_path, filename)

    with open(zip_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'

    os.remove(zip_path)
    return response
#-----------------Uploaded documents page logic ends------------------


@login_required
@mentee_required
def credits_view(request):
    return render(request, 'menti/credits.html', {"is_mentor_view": False,})


#--------------------Messages page logic starts------------------------
#--------------------Inbox requests and chatting logic-----------------------
@method_decorator(login_required, name="dispatch")
class MessageListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Views lists of messages you have sent to other users"""

    model = Conversation
    template_name = 'menti/listmessages.html'
    context_object_name = 'conversation1'
    paginate_by = 10

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(sender=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class SentDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """details the message sent"""

    model = Msg
    context_object_name = 'messo'
    template_name = 'menti/sent.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(sender=self.request.user)


@method_decorator(login_required, name="dispatch")
class InboxView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Views lists of inbox messages received"""

    model = Msg
    context_object_name = 'inbox'
    template_name = 'menti/inbox.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class InboxDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Inbox Detailed view"""

    model = Msg
    context_object_name = 'messo'
    template_name = 'menti/inboxview.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class MessageView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """controls messege view"""

    template_name = 'menti/messages-module.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['count'] = Msg.objects.filter(receipient=self.request.user).filter(is_approved=False).count()
        context['count1'] = Msg.objects.filter(sender=self.request.user).filter(is_approved=True).count()
        context['count3'] = Conversation.objects.filter(receipient=self.request.user).count()
        context['count4'] = Conversation.objects.filter(sender=self.request.user).count()
        context['is_mentor_view'] = False
        return context

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)


def messege_view(request):
    """Views the Message Module"""

    if not request.user.is_mentee:
        return redirect('home')

    return render(request, 'menti/messages-module.html', {"is_mentor_view": False,})


@method_decorator(login_required, name="dispatch")
class SentMessageDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Deletes Sent Messages"""

    model = models.Msg
    success_url = reverse_lazy("list")
    template_name = 'menti/sentmessage_delete.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class Approved(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """view list of approved messages from mentors"""

    def test_func(self):
        return self.request.user.is_mentee

    model = Msg.objects.filter(is_approved=True).order_by('-date_approved')

    template_name = 'menti/approved.html'

    context_object_name = 'messo'

    paginate_by = 10

    def get_queryset(self):
        return self.model.filter(sender=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class CreateMessageView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    """create new message for a specific user from the profile"""
    fields = ('msg_content',)
    model = Msg
    template_name = 'menti/sendindividual.html'
    success_message = 'Your Request has been Sent! Wait for Approval from your Mentor.'

    def test_func(self):
        return self.request.user.is_mentee

    def form_valid(self, form):
        form.instance.sender = self.request.user
        form.instance.receipient = User.objects.get(pk=self.kwargs['pk'])

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('conv')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class ProfileDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """view details of a user in the profile"""
    model = User
    context_object_name = 'user'
    template_name = 'menti/profile_detail.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class ConversationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all chat conversation by a user"""
    model = Conversation
    template_name = 'menti/list-converations.html'
    context_object_name = 'conversation'
    paginate_by = 10

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_mentor_view'] = False
        return context


@method_decorator(login_required, name="dispatch")
class ConversationDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """List Conversations"""
    model = Conversation
    template_name = 'menti/conversation1.html'
    context_object_name = 'conv'

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


@method_decorator(login_required, name="dispatch")
class ConversationList1View(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """List Conversation"""
    model = Conversation
    template_name = 'menti/conversation2.html'
    context_object_name = 'conversation'

    def test_func(self):
        return self.request.user.is_mentee

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


@login_required
def con(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)

    if request.method == 'POST':
        form = ChatReplyForm(request.POST, request.FILES)

        if form.is_valid():

            # prevent empty message
            if not form.cleaned_data.get("reply") and not form.cleaned_data.get("file"):
                messages.error(request, "Cannot send an empty message")
                return redirect("con", pk=pk)

            reply_obj = form.save(commit=False)
            reply_obj.sender = request.user
            reply_obj.conversation = conv
            reply_obj.save()
            print("DEBUG FILES:", request.FILES)

            return redirect('conv2-reply', pk=conv.pk)
    else:
        form = ChatReplyForm()

    return render(request, 'menti/conversation1.html', {
        'conv': conv,
        'form': form,
        'is_mentor_view': False,
    })


@require_POST
@login_required
def upload_reply(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    conv = get_object_or_404(Conversation, pk=pk)

    text = request.POST.get("reply", "")
    uploaded_file = request.FILES.get("file")

    reply = Reply.objects.create(
        conversation=conv,
        sender=request.user,
        reply=text or "",
        file=uploaded_file if uploaded_file else None,
        replied_at=timezone.now()
    )

    # Prepare broadcast payload
    payload = {
        "id": reply.id,
        "sender_id": reply.sender.id,
        "text": reply.reply,
        "file_url": reply.file.url if reply.file else None,
        "replied_at": reply.replied_at.isoformat(),
        "seen_count": reply.seen_by.count(),
    }

    # Broadcast to WebSocket group
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"conversation_{pk}",
        {
            "type": "new_message",
            "message": payload
        }
    )

    # Return HTTP response (so AJAX doesn't show alert)
    return JsonResponse({
        "status": "ok",
        "reply_id": reply.id,
        "text": reply.reply,
        "file_url": reply.file.url if reply.file else None
    })


@login_required
def edit_reply(request, pk):
    """
    Edit an existing reply; only sender may edit.
    Broadcasts edited_message.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST only"}, status=405)

    r = get_object_or_404(Reply, pk=pk)
    if r.sender != request.user:
        return HttpResponseForbidden("Not allowed")

    new_text = request.POST.get("reply", "")
    r.reply = new_text
    r.edited = True  # mark as edited
    r.edited_at = timezone.now()  # store edit timestamp
    r.replied_at = timezone.now()  # update shown timestamp
    r.save()

    payload = {
        "id": r.id,
        "sender_id": r.sender.id,
        "sender_username": getattr(r.sender, "username", ""),
        "text": r.reply,
        "file_url": r.file.url if getattr(r, "file", None) else None,
        "replied_at": r.replied_at.isoformat() if r.replied_at else None,
        "edited": r.edited,
        "edited_at": r.edited_at.isoformat(),
    }

    # broadcast edited_message
    channel_layer = get_channel_layer()
    group_name = f"conversation_{r.conversation.pk}"

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "edited_message",
            "message": payload
        }
    )

    return JsonResponse({"status": "ok", "text": payload["text"], "replied_at": payload["replied_at"], "edited": True})


@login_required
def delete_reply(request, pk):
    """
    Delete an existing reply; only sender or conversation owner may delete.
    Broadcasts deleted_message.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST only"}, status=405)

    r = get_object_or_404(Reply, pk=pk)
    # permission check: allow sender or conversation owner (adjust if needed)
    if r.sender != request.user:
        return HttpResponseForbidden("Not allowed")

    payload = {"id": r.id}
    conv_pk = r.conversation.pk
    # soft-delete or delete; here we delete
    r.delete()

    # broadcast deleted_message
    channel_layer = get_channel_layer()
    group_name = f"conversation_{conv_pk}"
    async_to_sync(channel_layer.group_send)(group_name, {
        "type": "deleted_message",
        "message": payload
    })

    return JsonResponse({"status": "ok"})


@method_decorator(login_required, name="dispatch")
class ReplyCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Replies by a user"""
    fields = ('reply',)
    model = Reply
    template_name = 'menti/conversation.html'

    def test_func(self):
        return self.request.user.is_mentee

    def form_valid(self, form):
        form.instance.sender = self.request.user
        form.instance.conversation = Conversation.objects.get(pk=self.kwargs['pk'])
        return super().form_valid(form)

    def get_success_url(self):
        conversation = self.object.conversation
        return reverse_lazy('conv1-reply', kwargs={'pk': self.object.conversation_id})

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


@method_decorator(login_required, name="dispatch")
class ConversationDeleteView(DeleteView):
    """delete view Chat"""
    model = Reply
    template_name = 'menti/chat-confirm-delete.html'

    # success_url = reverse_lazy('conv1')

    def get_success_url(self):
        conversation = self.object.conversation
        return reverse_lazy('conv1-reply', kwargs={'pk': self.object.conversation_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


def search(request):
    """Search For Users"""

    if not request.user.is_mentee:
        return redirect('home')

    queryset = User.objects.all()

    query = request.GET.get('q')

    if query:
        queryset = queryset.filter(

            Q(username__icontains=query) |
            Q(first_name__icontains=query)

        ).distinct()

    context = {
        'is_mentor_view': False,
        'queryset': queryset
    }

    return render(request, 'menti/search_results.html', context)


@method_decorator(login_required, name="dispatch")
class CreateIndividualMessageView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    """create new message for a specific user from search query"""
    fields = ('conversation',)
    model = Conversation
    template_name = 'menti/messagecreate2.html'
    success_message = 'Your Conversation Has been Created!'

    def test_func(self):
        return self.request.user.is_mentee

    def form_valid(self, form):
        form.instance.sender = self.request.user
        form.instance.receipient = User.objects.get(pk=self.kwargs['pk'])

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('list')


@method_decorator(login_required, name="dispatch")
class Profile2DetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """view details of a user search in the profile"""
    model = User
    context_object_name = 'user'
    template_name = 'menti/profile_detail1.html'

    def test_func(self):
        return self.request.user.is_mentee

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


@method_decorator(login_required, name="dispatch")
class Reply1CreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Replies by a user"""
    fields = ('reply',)
    model = Reply
    template_name = 'menti/conversation3.html'

    def test_func(self):
        return self.request.user.is_mentee

    def form_valid(self, form):
        form.instance.sender = self.request.user
        form.instance.conversation = Conversation.objects.get(pk=self.kwargs['pk'])
        return super().form_valid(form)

    def get_success_url(self):
        conversation = self.object.conversation
        return reverse_lazy('conv3-reply', kwargs={'pk': self.object.conversation_id})

    def get_queryset(self):
        return self.model.objects.filter(receipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_mentor_view"] = False
        return context


def con1(request, pk):
    """View individual conversation"""

    conv = get_object_or_404(Conversation, pk=pk)

    context = {
        'is_mentor_view': False,
        'conv': conv,
    }

    return render(request, 'menti/conversation4.html', context)
#--------------------Messages page logic ends----------------------


#--------------------Meeting scheduling logic starts-----------------------
@login_required
def schedule_meeting_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    mentor = get_object_or_404(Mentor, user=user)
    mentee = get_object_or_404(Mentee, user=request.user)

    # Check if meeting already exists between this mentee and mentor
    existing_meeting = Meeting.objects.filter(
        mentor=mentor,
        mentee=mentee,
        status='scheduled'
    ).order_by('-appointment_date', '-time_slot').first()

    if request.method == 'POST':
        form = MeetingForm(request.POST, instance=existing_meeting)  # reuse existing meeting if any
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.mentor = mentor
            meeting.mentee = mentee
            meeting.duration_minutes = 60
            meeting.status = 'scheduled'

            today = timezone.localdate()
            # 🔒 Prevent past-date rescheduling
            if meeting.appointment_date < today:
                meeting.appointment_date = today

            if not meeting.video_room_name:
                meeting.video_room_name = str(uuid.uuid4())

            meeting.save()


            # Generate meeting room link
            jitsi_link = f"https://meet.jit.si/{meeting.video_room_name}"


            # Email context
            context = {
                'mentor_name': mentor.user.first_name or mentor.user.username,
                'mentee_name': mentee.user.first_name or mentee.user.username,
                'mentee_email': mentee.user.email,
                'meeting_date': meeting.appointment_date.strftime('%Y-%m-%d'),
                'meeting_time': meeting.time_slot.strftime('%H:%M'),
                'jitsi_link': jitsi_link,
            }

            subject = f"New Meeting Scheduled with {context['mentee_name']}"
            from_email = settings.EMAIL_HOST_USER
            to_email = [mentor.user.email]

            html_content = render_to_string('menti/meeting_invite.html', context)

            email = EmailMultiAlternatives(subject, '', from_email, to_email)
            email.attach_alternative(html_content, "text/html")
            email.extra_headers = {'Reply-To': mentee.user.email}

            email.send()

            messages.success(request, "Meeting scheduled and email sent to the mentor.")
            return redirect('account')
    else:
        form = MeetingForm(instance=existing_meeting)

    return render(request, 'menti/schedule_meeting.html', {'mentor': mentor, 'form': form, 'is_mentor_view': False})


@login_required
def meetings_calendar_api(request):
    user = request.user
    now = timezone.localtime(timezone.now())

    if hasattr(user, "mentor"):
        meetings = Meeting.objects.filter(mentor__user=user)
    else:
        meetings = Meeting.objects.filter(mentee__user=user)

    events = []
    for m in meetings:
        events.append({
            "id": m.id,
            "title": f"Meeting with ...",
            "start": m.meeting_datetime.isoformat(),
            "end": m.meeting_end_datetime.isoformat(),
            "color": "#198754" if m.status == "completed" else "#0d6efd",
            "extendedProps": {
                "mentor": (
                    m.mentor.name
                    if hasattr(user, "mentee")
                    else m.mentee.user.username
                )
            }
        })

    return JsonResponse(events, safe=False)


@login_required
def meeting_room_view(request, room_name):
    meeting = get_object_or_404(Meeting, video_room_name=room_name)

    if request.user not in [meeting.mentor.user, meeting.mentee.user]:
        return HttpResponseForbidden("Not authorized")

    now = timezone.localtime(timezone.now())

    # ❌ prevent joining expired meetings
    if now > meeting.meeting_end_datetime:
        if meeting.status != 'completed':
            meeting.status = 'completed'
            meeting.save(update_fields=['status'])
        return redirect('account')

    return render(request, 'menti/meeting_room.html', {
        'meeting': meeting,
        'jitsi_link': f"https://meet.jit.si/{meeting.video_room_name}",
    })


@login_required
@login_required
def meetings_view(request):
    mentee = get_object_or_404(Mentee, user=request.user)


    meetings = Meeting.objects.filter(
    mentee=mentee
    ).order_by('-appointment_date', '-time_slot')


    now = timezone.localtime(timezone.now())


    # Auto-complete expired meetings
    for meeting in meetings:
        if meeting.status == 'scheduled' and now > meeting.meeting_end_datetime:
            meeting.status = 'completed'
            meeting.save(update_fields=['status'])


        # expose datetimes for template
        meeting._meeting_datetime = meeting.meeting_datetime
        meeting._meeting_end_datetime = meeting.meeting_end_datetime


    context = {
    'meetings': meetings,
    'now': now,
    'is_mentor_view': False,
    }
    return render(request, 'menti/meetings.html', context)
#--------------------Meeting scheduling logic ends-----------------------

#--------------------Mentee Query submission logic starts-----------------------
@login_required
def query_suggestion(request, pk):
    """
    pk: optional, for preselecting a mentor if needed
    """
    # Get logged-in mentee
    user = get_object_or_404(User, pk=pk)
    mentor = get_object_or_404(Mentor, user=user)
    mentee = get_object_or_404(Mentee, user=request.user)

    # Select mentor
    if pk:  # if specific mentor pk passed in URL
        mentor_user = get_object_or_404(User, pk=pk)
        mentor = get_object_or_404(Mentor, user=mentor_user)
    else:
        # pick first mentor as default
        mentor = Mentor.objects.first()

    if request.method == "POST":
        form = QueryForm(request.POST)
        if form.is_valid():
            query = form.save(commit=False)
            query.mentee = mentee
            query.mentor = mentor
            query.save()

            messages.success(request, "Query sent to the mentor.")
            return redirect('account')
    else:
        form = QueryForm()

    return render(request, "menti/query_suggestion.html", {"form": form, "mentor": mentor, 'is_mentor_view': False})


@login_required
def mentee_queries(request):
    try:
        mentee = Mentee.objects.get(user=request.user)
    except Mentee.DoesNotExist:
        return redirect("mentor_queries")

    queries_qs = Query.objects.filter(
        mentee=mentee
    ).order_by("-created_at")

    paginator = Paginator(queries_qs, 10)  # 🔹 10 queries per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "queries": page_obj,
        "page_obj": page_obj,
        "is_mentor_view": False,
    }

    return render(request, "menti/mentee_queries.html", context)
#--------------------Mentee Query logic ends-----------------------

#--------------------Profile Overview logic starts-----------------------
@login_required
@mentee_required
def student_profile_overview(request):
    user = request.user

    profile = get_object_or_404(Profile, user=user)
    overview, _ = StudentProfileOverview.objects.get_or_create(user=user)

    # Pull related data
    semester_results = SemesterResult.objects.filter(user=user).order_by("semester")
    education = EducationalDetail.objects.filter(user=user).order_by("year_of_passing")
    internships = InternshipPBL.objects.filter(user=user)
    projects = Project.objects.filter(user=user)
    certifications = CertificationCourse.objects.filter(user=user)
    publications = PaperPublication.objects.filter(user=user)
    sports = SportsCulturalEvent.objects.filter(user=user)
    other_events = OtherEvent.objects.filter(user=user)
    interests = StudentInterest.objects.filter(student=user).first()
    subjects = SubjectOfInterest.objects.filter(user=user)
    long_term_goal = LongTermGoal.objects.filter(user=user).first()

    # Completeness
    completeness_score, completeness_items = compute_profile_completeness(user)

    if request.method == "POST":
        form = StudentProfileOverviewForm(request.POST, instance=overview)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile overview updated successfully.")
            return redirect("student_profile_overview")
    else:
        form = StudentProfileOverviewForm(instance=overview)

    context = {
        "profile": profile,
        "overview": overview,
        "form": form,
        "semester_results": semester_results,
        "education": education,
        "internships": internships,
        "projects": projects,
        "certifications": certifications,
        "publications": publications,
        "sports": sports,
        "other_events": other_events,
        "interests": interests,
        "subjects": subjects,
        "long_term_goal": long_term_goal,
        "completeness_score": completeness_score,
        "completeness_items": completeness_items,
        "is_mentor_view": False,
    }

    return render(request, "menti/student_profile_overview.html", context)


@login_required
@mentee_required
def export_resume_pdf(request):
    user = request.user
    profile = get_object_or_404(Profile, user=user)
    overview, _ = StudentProfileOverview.objects.get_or_create(user=user)

    semester_results = SemesterResult.objects.filter(user=user).order_by("semester")
    education = EducationalDetail.objects.filter(user=user).order_by("year_of_passing")
    internships = InternshipPBL.objects.filter(user=user)
    projects = Project.objects.filter(user=user)
    certifications = CertificationCourse.objects.filter(user=user)
    publications = PaperPublication.objects.filter(user=user)
    sports = SportsCulturalEvent.objects.filter(user=user)
    other_events = OtherEvent.objects.filter(user=user)

    context = {
        "user": user,
        "profile": profile,
        "overview": overview,
        "semester_results": semester_results,
        "education": education,
        "internships": internships,
        "projects": projects,
        "certifications": certifications,
        "publications": publications,
        "sports": sports,
        "other_events": other_events,
    }

    template = get_template("menti/resume_pdf.html")
    html = template.render(context)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{user.username}_{user.profile.student_name}_profile.pdf"'

    def link_callback(uri, rel):
        """
        Converts Django media/static URIs to absolute system paths
        """
        # MEDIA files
        if uri.startswith(settings.MEDIA_URL):
            path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        # STATIC files (optional)
        elif uri.startswith(settings.STATIC_URL):
            path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        else:
            return uri

        if not os.path.isfile(path):
            raise Exception(f"Media URI must start with {settings.MEDIA_URL} or {settings.STATIC_URL}")

        return path

    pisa_status = pisa.CreatePDF(
        src=html,
        dest=response,
        link_callback=link_callback   #✅✅✅ THIS IS THE FIX
    )

    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response

def public_portfolio_view(request, slug):
    overview = get_object_or_404(StudentProfileOverview, public_slug=slug, is_public=True)
    user = overview.user

    profile = get_object_or_404(Profile, user=user)

    semester_results = SemesterResult.objects.filter(user=user).order_by("semester")
    education = EducationalDetail.objects.filter(user=user).order_by("year_of_passing")
    internships = InternshipPBL.objects.filter(user=user)
    projects = Project.objects.filter(user=user)
    certifications = CertificationCourse.objects.filter(user=user)
    publications = PaperPublication.objects.filter(user=user)
    sports = SportsCulturalEvent.objects.filter(user=user)
    other_events = OtherEvent.objects.filter(user=user)
    interests = StudentInterest.objects.filter(student=user).first()
    subjects = SubjectOfInterest.objects.filter(user=user)
    long_term_goal = LongTermGoal.objects.filter(user=user).first()

    context = {
        "profile": profile,
        "overview": overview,
        "semester_results": semester_results,
        "education": education,
        "internships": internships,
        "projects": projects,
        "certifications": certifications,
        "publications": publications,
        "sports": sports,
        "other_events": other_events,
        "interests": interests,
        "subjects": subjects,
        "long_term_goal": long_term_goal,
        "is_public_view": True,
        "is_mentor_view": True,  # reuse display styling
    }
    return render(request, "menti/student_profile_public.html", context)
#--------------------Profile Overview logic ends-----------------------
