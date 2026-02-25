from django.contrib import admin
from .models import (Mentee, Mentor, Profile, Msg, Conversation, Reply, InternshipPBL, Project, SportsCulturalEvent,
                     OtherEvent, LongTermGoal, EducationalDetail, Meeting, MenteeAdmin, StudentInterest, SemesterResult,
                     MentorMenteeInteraction, ActivityLog, WeeklyAgenda)
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


@admin.register(InternshipPBL)
class InternshipPBLAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "company_name", "academic_year", "semester", "start_date", "end_date", "no_of_days", "uploaded_at")
    search_fields = ("title", "company_name", "user__username")  # 🔍 search filter
    list_filter = ("user", "academic_year", "semester", "type")  # ✅ dropdown filters
    ordering = ("-start_date",)  # ⬅️ latest internships first
    readonly_fields = ("no_of_days",)  # prevent editing


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "academic_year", "semester", "project_type", "guide_name", "uploaded_at")
    search_fields = ("title", "guide_name", "user__username", "project_type")
    list_filter = ("user", "academic_year", "semester", "project_type")
    ordering = ("-uploaded_at",)


@admin.register(SportsCulturalEvent)
class SportsCulturalEventAdmin(admin.ModelAdmin):
    list_display = ("user", "name_of_event", "academic_year", "semester", "type", "level", "prize_won", "uploaded_at")
    search_fields = ("name_of_event", "venue", "user__username")
    list_filter = ("user", "academic_year", "semester", "type", "level", "prize_won")
    ordering = ("-uploaded_at",)


@admin.register(OtherEvent)
class OtherEventAdmin(admin.ModelAdmin):
    list_display = ("user", "name_of_event", "academic_year", "semester", "level", "prize_won", "amount_won", "uploaded_at")
    search_fields = ("name_of_event", "details", "user__username")
    list_filter = ("user", "academic_year", "semester", "level", "prize_won")
    ordering = ("-uploaded_at",)


@admin.register(LongTermGoal)
class LongTermGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "reason", "created_at")


@admin.register(EducationalDetail)
class EducationalDetailAdmin(admin.ModelAdmin):
    list_display = ("user", "examination", "percentage", "university_board", "year_of_passing")


@admin.register(StudentInterest)
class StudentInterestAdmin(admin.ModelAdmin):
    list_display = ("student", "get_interests", "created_at")

    def get_interests(self, obj):
        return ", ".join(obj.interests)
    get_interests.short_description = "Interests"


@admin.register(SemesterResult)
class SemesterResultAdmin(admin.ModelAdmin):
    list_display = ("user", "academic_year", "semester", "pointer", "no_of_kt", "created_at")


class ConversationAdmin(admin.ModelAdmin):
    search_fields = ("conversation",)
    list_display = ("sender", "receipient", "sent_at", "conversation", "reply", "replied_at",)
    list_display_links = ("conversation",)
    list_per_page = 10


class MsgAdmin(admin.ModelAdmin):
    search_fields = ("msg_content",)
    list_filter = ("is_approved",)
    list_display = ("sender", "receipient", "sent_at", "msg_content", "comment", "comment_at", "is_approved", "chat_started", "date_approved")
    list_editable = ("is_approved",)
    list_display_links = ("msg_content",)
    list_per_page = 10


class MentorAdmin(admin.ModelAdmin):
    search_fields = ("interests",)


class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "is_mentor", "is_mentee",)
    list_display_links = ("username", "email",  "is_mentor", "is_mentee",)
    list_filter = ("username", "is_mentor", "is_mentee",)
    search_fields = ("username",)
    list_per_page = 10


admin.site.register(Reply)

admin.site.register(Mentee)

admin.site.register(Mentor, MentorAdmin)

#admin.site.register(User, UserAdmin)

admin.site.register(Profile)

admin.site.register(Msg, MsgAdmin)

admin.site.register(Conversation)

User = get_user_model()
class CustomUserCreationForm(UserCreationForm):

    class Meta:
        model = User
        fields =  '__all__'
        exclude =('password', )

class CustomUserAdmin(UserAdmin):
    form = CustomUserCreationForm

admin.site.register(User, CustomUserAdmin)

admin.site.unregister(Group)


#zaruuu
from .models import MentorAdmin
@admin.register(MentorAdmin)
class MentoAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'availability_start', 'availability_end']
    search_fields = ['user_username', 'user_first_name']
    list_filter = ['specialization']


@admin.register(MenteeAdmin)
class MenteeAdmin(admin.ModelAdmin):
    list_display = ['user']
    search_fields = ['user_username', 'user_first_name']


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = [
        'mentor_name', 'mentee_name',
        'appointment_date', 'time_slot',
        'duration_minutes', 'status', 'created_at'
    ]

    search_fields = [
        'mentor__user__username', 'mentee__user__username',
        'mentor__user__first_name', 'mentee__user__first_name',
        'mentor__user__last_name', 'mentee__user__last_name',
    ]

    list_filter = ['appointment_date', 'status', 'mentor__user__username', 'mentee__user__username']

    ordering = ['-appointment_date', '-time_slot']

    def mentor_name(self, obj):
        return obj.mentor.user.get_full_name() or obj.mentor.user.username
    mentor_name.short_description = 'Mentor'

    def mentee_name(self, obj):
        return obj.mentee.user.get_full_name() or obj.mentee.user.username
    mentee_name.short_description = 'Mentee'


@admin.register(MentorMenteeInteraction)
class MentorMenteeInteractionAdmin(admin.ModelAdmin):
    list_display = [
        'mentor',     # Shows mentor username automatically
        'mentee_list',
        'date',
        'semester',
        'class_year',
        'agenda',
        'created_at',
    ]

    search_fields = [
        'mentor__username',  # search by mentor username
        'mentor__first_name',
        'mentor__last_name',
        'mentees__username',  # search by mentee username
        'mentees__first_name',
        'mentees__last_name',
    ]

    # Optional: make admin faster by prefetching M2M
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("mentees")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "module", "timestamp", "ip_address")
    list_filter = ("action", "module", "timestamp")
    search_fields = ("user__username", "action", "details")


@admin.register(WeeklyAgenda)
class WeeklyAgendaAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'academic_year', 'week', 'year', 'sem', 'created_by', 'created_at', 'updated_at')
    list_filter = ('academic_year', 'week', 'year', 'sem', 'created_by')
    search_fields = ('academic_year', 'week', 'year', 'sem')