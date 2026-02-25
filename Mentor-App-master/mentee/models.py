from django.db import models
from django.utils import timezone
from PIL import Image
from datetime import datetime, timedelta
from django.utils.timezone import now
import uuid
from django.contrib.auth.models import AbstractUser
from datetime import date


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True)
    is_mentee = models.BooleanField(default=False)
    is_mentor = models.BooleanField(default=False)

    def __str__(self):
        return self.username or f"User {self.pk}"


class Mentee(models.Model):
    """Mentee models"""
    user = models.OneToOneField(User, primary_key=True, on_delete=models.CASCADE)
    mentor = models.ForeignKey("Mentor", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentees")

    def __str__(self):
        return self.user.username if self.user and self.user.username else f"Mentee {self.pk}"

DEPARTMENT_CHOICES = [
    ('CIVIL', 'CIVIL'),
    ('COMPS', 'COMPUTER SCIENCE'),
    ('EXTC', 'ELECTRONICS & TELECOMMUNICATION'),
    ('MECH', 'MECHANICAL'),
    ('IT', 'INFORMATION TECHNOLOGY'),
    ('CSE - AIML', 'ARTIFICIAL INTELLIGENCE & MACHINE LEARNING'),
    ('CSE - DS', 'DATA SCIENCE'),
]

WEEK_CHOICES = [
        ('Week-1', 'Week-1'),
        ('Week-2', 'Week-2'),
        ('Week-3', 'Week-3'),
        ('Week-4', 'Week-4'),
        ('Week-5', 'Week-5'),
        ('Week-6', 'Week-6'),
        ('Week-7', 'Week-7'),
        ('Week-8', 'Week-8'),
        ('Week-9', 'Week-9'),
        ('Week-10', 'Week-10'),
        ('Week-11', 'Week-11'),
        ('Week-12', 'Week-12'),
    ]

AY = [
        ('2017-18', '2017-18'),
        ('2018-19', '2018-19'),
        ('2019-20', '2019-20'),
        ('2020-21', '2020-21'),
        ('2021-22', '2021-22'),
        ('2022-23', '2022-23'),
        ('2023-24', '2023-24'),
        ('2024-25', '2024-25'),
        ('2025-26', '2025-26'),
        ('2026-27', '2026-27'),
    ]

SEM_CHOICES = [
        ('I', 'I'), ('II', 'II'), ('III', 'III'), ('IV', 'IV'),
        ('V', 'V'), ('VI', 'VI'), ('VII', 'VII'), ('VIII', 'VIII'),
    ]

YEAR_CHOICES = [
        ('FE', 'FE'),  # First Year
        ('SE', 'SE'),  # Second Year
        ('TE', 'TE'),  # Third Year
        ('BE', 'BE'),  # Final Year
    ]

class Mentor(models.Model):
    """Mentor models"""
    user = models.OneToOneField(User, primary_key=True, on_delete=models.CASCADE)
    image = models.ImageField(default='default.png', upload_to="mentors/", blank=True, null=True)
    name = models.CharField(max_length=150, blank=True, null=True)
    department = models.CharField(max_length=150, choices=DEPARTMENT_CHOICES, blank=True, null=True)
    expertise = models.TextField(blank=True, null=True)

    def __str__(self):
        if self.user and self.user.username:
            return self.user.username
        elif self.name:
            return self.name
        else:
            return f"Mentor {self.pk}"


class Profile(models.Model):
    """Extended Profile Model"""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    forget_password_token = models.CharField(max_length=500, blank=True, null=True)
    image = models.ImageField(default='default.png', upload_to='profile_pics')

    # --- Personal Details ---
    moodle_id = models.CharField(max_length=20, blank=True, null=True)
    student_name = models.CharField(max_length=200, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, blank=True, null=True)
    branch = models.CharField(max_length=100, choices=DEPARTMENT_CHOICES, blank=True, null=True)
    career_domain = models.CharField(max_length=200, blank=True)

    address = models.TextField(blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    hobby = models.TextField(blank=True, null=True)
    about_me = models.TextField(blank=True, null=True)

    # --- Family Details ---
    mother_name = models.CharField(max_length=100, blank=True, null=True)
    mother_occupation = models.CharField(max_length=100, blank=True, null=True)
    mother_contact = models.CharField(max_length=15, blank=True, null=True)

    father_name = models.CharField(max_length=100, blank=True, null=True)
    father_occupation = models.CharField(max_length=100, blank=True, null=True)
    father_contact = models.CharField(max_length=15, blank=True, null=True)

    sibling1_name = models.CharField(max_length=100, blank=True, null=True)
    sibling2_name = models.CharField(max_length=100, blank=True, null=True)


    def __str__(self):
        if self.user:
            return f"{self.user.username}'s Profile"
        return "Profile (no user)"

    def save(self, **kwargs):
        super().save()
        img = Image.open(self.image.path)

        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.image.path)

    @property
    def age(self):
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - (
                (today.month, today.day) < (self.dob.month, self.dob.day)
        )

    def is_complete(self):
        required_fields = [
            self.student_name,
            self.year,
            self.branch,
            self.image,
            self.semester,
            self.dob,
            self.address,
            self.contact_number,
            self.career_domain,
            self.father_name,
            self.father_contact,
            self.mother_name,
            self.mother_contact
        ]
        return all(required_fields)


class MentorMentee(models.Model):
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE, related_name="mentor_mappings")
    mentee = models.OneToOneField(Mentee, on_delete=models.CASCADE, related_name="assigned_mentor")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("mentor", "mentee")

    def __str__(self):
        mentor_str = self.mentor.user.username if self.mentor and self.mentor.user and self.mentor.user.username else "Unknown Mentor"
        mentee_str = self.mentee.user.username if self.mentee and self.mentee.user and self.mentee.user.username else "Unknown Mentee"
        return f"{mentor_str} → {mentee_str}"


class InternshipPBL(models.Model):
    TYPE_CHOICES = [
        ("Internship in Industry", "Internship in Industry"),
        ("Internship through APSIT SKILLS Platform", "Internship through APSIT SKILLS Platform"),
        ("Internship through AICTE Virtual Internship Platform", "Internship through AICTE Virtual Internship Platform"),
        ("PBL", "PBL"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    title = models.CharField(max_length=200, blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    type = models.CharField(max_length=200, choices=TYPE_CHOICES, blank=True, null=True)
    company_name = models.CharField(max_length=100, blank=True, null=True)
    details = models.TextField(max_length=500, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    no_of_days = models.IntegerField(blank=True, null=True)
    certificate = models.FileField(upload_to="certificates/internships/", blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            self.no_of_days = delta if delta > 0 else None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.academic_year})"


class Project(models.Model):
    TYPE_CHOICES = [
        ("Mini Project", "Mini Project"),
        ("Major Project", "Major Project"),
        ("Research", "Research"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    title = models.CharField(max_length=200, blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    project_type = models.CharField(max_length=50, choices=TYPE_CHOICES, blank=True, null=True)
    details = models.TextField(max_length=1000, blank=True, null=True)
    guide_name = models.CharField(max_length=100, blank=True, null=True)
    link = models.URLField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or "Untitled Project"


class SportsCulturalEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ("Indoor", "Indoor"),
        ("Outdoor", "Outdoor"),
    ]
    LEVEL_CHOICES = [
        ("Inter-College", "Inter-College"),
        ("Intra-College", "Intra-College"),
        ("District", "District"),
        ("State", "State"),
        ("National", "National"),
        ("International", "International"),
        ("Other", "Other"),
    ]
    PRIZE_CHOICES = [
        ("Participation", "Participation"),
        ("1st", "1st"),
        ("2nd", "2nd"),
        ("3rd", "3rd"),
        ("4th", "4th"),
        ("5th", "5th"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    name_of_event = models.CharField(max_length=200, blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, blank=True, null=True)
    venue = models.CharField(max_length=500, blank=True, null=True)
    level = models.CharField(max_length=50, choices=LEVEL_CHOICES, blank=True, null=True)
    prize_won = models.CharField(max_length=20, choices=PRIZE_CHOICES, blank=True, null=True)
    certificate = models.FileField(upload_to="sports_cultural_certificates/", null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.name_of_event or "Unnamed Event"
        ay = self.academic_year or "No AY"
        return f"{name} ({ay})"


class OtherEvent(models.Model):
    LEVEL_CHOICES = [
        ("College", "College"),
        ("University", "University"),
        ("District", "District"),
        ("State", "State"),
        ("National", "National"),
        ("International", "International"),
        ("Other", "Other"),
    ]
    PRIZE_CHOICES = [
        ("Participation", "Participation"),
        ("1st", "1st"),
        ("2nd", "2nd"),
        ("3rd", "3rd"),
        ("4th", "4th"),
        ("5th", "5th"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    name_of_event = models.CharField(max_length=200, blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    level = models.CharField(max_length=50, choices=LEVEL_CHOICES, blank=True, null=True)
    details = models.TextField(max_length=1000, blank=True, null=True)
    prize_won = models.CharField(max_length=20, choices=PRIZE_CHOICES, blank=True, null=True)
    amount_won = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    team_members = models.TextField(max_length=500, blank=True, null=True)
    certificate = models.FileField(upload_to="other_event_certificates/", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.name_of_event or "Unnamed Event"
        ay = self.academic_year or "No AY"
        return f"{name} ({ay})"


class CertificationCourse(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    certifying_authority = models.CharField(max_length=100, blank=True, null=True)
    valid_upto = models.CharField(max_length=50, null=True, blank=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    no_of_days = models.PositiveIntegerField(blank=True, null=True)
    domain = models.CharField(max_length=150, blank=True, null=True)
    level = models.CharField(max_length=20, blank=True, null=True)
    amount_reimbursed = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    certificate = models.FileField(upload_to="certificates/courses/", blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or "Unnamed Certification"


class PaperPublication(models.Model):
    TYPE_CHOICES = [
        ("Other", "Other"),
        ("Conference", "Conference"),
        ("Journal", "Journal"),
        ("Article", "Article"),
        ("Blog", "Blog"),
    ]

    LEVEL_CHOICES = [
        ("International", "International"),
        ("National", "National"),
        ("State", "State"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES, blank=True, null=True)
    conf_name = models.CharField(max_length=255, null=True, blank=True)
    details = models.TextField(max_length=500, blank=True, null=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, blank=True, null=True)
    amount_reimbursed = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    authors = models.TextField(max_length=255, help_text="Comma separated list of authors", blank=True, null=True)
    certificate = models.FileField(upload_to="publications/", blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or "Untitled Publication"


class SelfAssessment(models.Model):
    GOAL_CHOICES = [
        ("To clear A.T.K.T.", "To clear A.T.K.T."),
        ("Competitive Exams", "Competitive Exams"),
        ("Extra Curricular/Co- curricular Activities", "Extra Curricular/Co- curricular Activities"),
        ("Attendance", "Attendance"),
        ("Certification Courses", "Certification Courses"),
        ("Undertaking Projects", "Undertaking Projects"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    year = models.CharField(max_length=10, choices=YEAR_CHOICES, null=True, blank=True)
    goals = models.JSONField(default=list)  # stores multiple goals
    reason = models.TextField(max_length=500, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        sem = self.semester or "No Semester"
        user_name = self.user.username if self.user else "Unknown User"
        return f"{user_name} - {sem}"


class LongTermGoal(models.Model):
    PLAN_CHOICES = [
        ('Work', 'Work'),
        ('Post Graduation', 'Post Graduation'),
        ('Entrepreneurship', 'Entrepreneurship'),
        ('Other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, blank=True, null=True)
    custom_plan = models.CharField(max_length=100, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def get_plan_display_value(self):
        return self.custom_plan if self.plan == "Other" else self.get_plan_display()

    def __str__(self):
        user_name = self.user.username if self.user else "Unknown User"
        plan_name = self.get_plan_display() if self.plan else "No Plan"
        return f"{user_name} - {plan_name}"


class SubjectOfInterest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.subject}"


class EducationalDetail(models.Model):
    EXAM_CHOICES = [
        ("SSC", "SSC"),
        ("HSC", "HSC"),
        ("Diploma", "Diploma"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    examination = models.CharField(max_length=50, choices=EXAM_CHOICES, blank=True, null=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    university_board = models.CharField(max_length=200, blank=True, null=True)
    year_of_passing = models.IntegerField(blank=True, null=True)

    def __str__(self):
        exam = self.examination or "No Exam"
        user_name = self.user.username if self.user else "Unknown User"
        return f"{exam} - {user_name}"


class SemesterResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE,blank=True, null=True)
    academic_year = models.CharField(max_length=20, choices=AY, blank=True, null=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, blank=True, null=True)
    pointer = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True)  # Example: 9.25
    no_of_kt = models.PositiveIntegerField(default=0, blank=True, null=True)
    marksheet = models.FileField(upload_to="marksheets/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - Sem {self.semester}"


class StudentInterest(models.Model):
    INTEREST_CHOICES = [
        # Post BE Exam
        ('gre', 'GRE'),
        ('gate', 'GATE'),
        ('coach', 'GATE/GRE Coaching from College'),
        ('ent', 'Entrepreneur'),
        ('hs', 'Higher Studies'),
        ('place', 'On-campus placements'),

        # Honors/Minors
        ('cyber', 'Cyber Security'),
        ('robotics', 'Robotics'),
        ('struct', 'Professional Practices in Structural Engineering'),
        ('aiml', 'Artificial Intelligence and Machine Learning'),
        ('iot', 'Internet of Things'),

        # Sports
        ('athletics', 'Athletics'),
        ('badminton', 'Badminton'),
        ('table-tennis', 'Table Tennis'),
        ('carrom', 'Carrom'),
        ('chess', 'Chess'),
        ('kabaddi', 'Kabaddi'),
        ('cricket', 'Cricket'),
        ('football', 'Football'),
        ('tug-of-war', 'Tug of War'),
        ('dodgeball', 'Dodgeball'),
        ('volleyball', 'Volleyball'),
        ('throwball', 'Throwball'),
        ('dancing', 'Dancing'),
        ('singing', 'Singing'),

        # Volunteering
        ('volunteer', 'Volunteering'),
        ('leader', 'Leadership'),

        # Clubs
        ('blockchain', 'Blockchain'),
        ('design', 'Design'),
        ('mac', 'MAC Racing Club'),
        ('smart', 'Smart City Club'),
        ('web', 'Web Development'),
        ('software-dev', 'Software Development'),

        # OJUS
        ('design-team', 'OJUS Design Team'),
        ('tech-team', 'OJUS Technical Team'),
        ('creative-team', 'OJUS Creative Team'),
        ('photo-team', 'OJUS Photography Team'),
        ('pub-team', 'OJUS Publicity Team'),
        ('eve-team', 'OJUS Event Team'),

        # Student Council
        ('gen-sec', 'General Secretary'),
        ('gs-associate', 'General Secretary Associate'),
        ('edit-team', 'Editorial Team'),
        ('creative-media-team', 'Creative Media Team'),
        ('sports-sec', 'Sports Secretary'),
        ('cult-sec', 'Cultural Secretary'),
        ('joint-cult-sec', 'Joint Cultural Secretary'),
        ('ladies-rep', 'Ladies Representative'),
        ('joint-ladies-rep', 'Joint Ladies Representative'),

        # Dept Societies
        ('society', 'Department Level Societies'),
    ]

    student = models.OneToOneField(User, on_delete=models.CASCADE, blank=True, null=True)  # only 1 entry per user
    interests = models.JSONField(default=list)  # stores multiple interests in one field
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_name = self.student.username if self.student else "Unknown User"
        interests_list = ", ".join(self.interests) if self.interests else "No Interests"
        return f"{user_name} - {interests_list}"


class StudentProfileOverview(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Editable overview fields
    profile_summary = models.TextField(
        blank=True,
        help_text="Short professional overview for resume/CV"
    )
    key_skills = models.TextField(
        blank=True,
        help_text="Comma separated skills (Python, Django, ML, etc.)"
    )

    # Public portfolio
    is_public = models.BooleanField(default=False)
    public_slug = models.SlugField(max_length=40, unique=True, blank=True, null=True)

    # Optional: store last computed completeness
    completeness_score = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Profile Overview"

    def ensure_public_slug(self):
        if not self.public_slug:
            self.public_slug = uuid.uuid4().hex[:12]  # short random id

    def save(self, *args, **kwargs):
        if self.is_public and not self.public_slug:
            self.ensure_public_slug()
        super().save(*args, **kwargs)


class Reply(models.Model):
    """Reply Model"""

    sender = models.ForeignKey(User, related_name="sender2", on_delete=models.CASCADE, null=True)
    reply = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    replied_at = models.DateTimeField(blank=True, null=True)
    conversation = models.ForeignKey('Conversation', related_name='replies', on_delete=models.CASCADE)
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        sender_name = self.sender.username if self.sender else "Unknown"
        return f"Reply from {sender_name}"

    def save(self, *args, **kwargs):
        if (self.reply or self.file) and self.replied_at is None:
            self.replied_at = now()
        super().save(*args, **kwargs)

    def get_file_url(self):
        return self.file.url if self.file else None

    def seen_count(self):
        return self.seen_by.count()


class Reaction(models.Model):
    reply = models.ForeignKey('Reply', related_name='reactions', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=20, null=True, blank=True)
    reacted_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('reply', 'user')  # one reaction per user per message

    def __str__(self):
        return f"{self.user} → {self.emoji} on {self.reply_id}"


class ReplySeen(models.Model):
    reply = models.ForeignKey('Reply', related_name='seen_by', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('reply', 'user')

    def __str__(self):
        return f"{self.user} saw reply {self.reply_id} at {self.seen_at}"


class Conversation(models.Model):
    """Conversation Model"""

    sender = models.ForeignKey(User, related_name="sender1", on_delete=models.CASCADE, null=True)
    receipient = models.ForeignKey(User, related_name="receipient1", on_delete=models.CASCADE)
    conversation = models.TextField(max_length=100)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

    @property
    def get_replies(self):
        return self.replies.all()

    def __str__(self):
        sender_name = self.sender.username if self.sender else "Unknown"
        recipient_name = self.receipient.username if self.receipient else "Unknown"
        return f"From {sender_name} to {recipient_name}"

    def save(self, *args, **kwargs):
        if not self.id:
            self.sent_at = timezone.now()

        super(Conversation, self).save(*args, **kwargs)


class Msg(models.Model):
    """Message Model"""

    sender = models.ForeignKey(User, related_name="sender", on_delete=models.CASCADE, null=True)
    receipient = models.ForeignKey(User, related_name="receipient", on_delete=models.CASCADE)
    msg_content = models.TextField(max_length=100)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, null=True)
    comment_at = models.DateTimeField(blank=True, null=True)
    is_approved = models.BooleanField(default=False, verbose_name="Approve?")
    chat_started = models.BooleanField(default=False)
    date_approved = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        sender_name = self.sender.username if self.sender else "Unknown"
        recipient_name = self.receipient.username if self.receipient else "Unknown"
        return f"From {sender_name} to {recipient_name}"

    def save(self, *args, **kwargs):
        if not self.id:
            self.sent_at = timezone.now()
        if self.comment and self.date_approved is None:
            self.date_approved = now()
        if self.comment and self.comment_at is None:
            self.comment_at = now()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-sent_at']


class MentorAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    availability_start = models.TimeField()
    availability_end = models.TimeField()

    def __str__(self):
        return self.user.username if self.user and self.user.username else f"MentorAdmin {self.pk}"


class MenteeAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.username if self.user and self.user.username else f"MenteeAdmin {self.pk}"


class Meeting(models.Model):
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE, related_name='meetings')
    mentee = models.ForeignKey(Mentee, on_delete=models.CASCADE, related_name='meetings')

    appointment_date = models.DateField()
    time_slot = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=2)

    created_at = models.DateTimeField(auto_now_add=True)
    video_room_name = models.CharField(max_length=255, unique=True, blank=True, null=True, default=uuid.uuid4)
    STATUS_CHOICES = (
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')



    def save(self, *args, **kwargs):
        if not self.video_room_name:
            self.video_room_name = str(uuid.uuid4())  # auto-generate unique room
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.mentee.user.username} & {self.mentor.user.username} on {self.appointment_date} at {self.time_slot}"

    @property
    def meeting_datetime(self):
        """Returns timezone-aware datetime of meeting start"""
        dt = datetime.combine(self.appointment_date, self.time_slot)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    @property
    def meeting_end_datetime(self):
        """Returns timezone-aware datetime of meeting end"""
        return self.meeting_datetime + timedelta(minutes=self.duration_minutes)

    @property
    def can_join(self):
        """Meeting can be joined only during scheduled window"""
        now = timezone.localtime(timezone.now())
        return self.meeting_datetime <= now <= self.meeting_end_datetime


class Query(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('moderate', 'Moderate'),
        ('low', 'Low'),
    ]

    mentee = models.ForeignKey(Mentee, on_delete=models.CASCADE)
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)
    text = models.TextField(blank=True, null=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='low')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    status = models.CharField(max_length=20, default="pending")

    def __str__(self):
        return f"Query by {self.mentee} to {self.mentor}"


class MentorMenteeInteraction(models.Model):
    mentor = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(null=True, blank=True)
    semester = models.CharField(max_length=10, choices=SEM_CHOICES, null=True, blank=True)
    class_year = models.CharField(max_length=10, blank=True, null=True)
    agenda = models.TextField(null=True, blank=True)
    mentees = models.ManyToManyField(User, related_name="mentor_interactions")
    ai_summary = models.TextField(blank=True, null=True)
    ai_summary_generated = models.BooleanField(default=False, null=True, blank=True)
    last_ai_summary = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.mentor.username} – {self.date}"

    def mentee_list(self):
        return ", ".join([m.username for m in self.mentees.all()])


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField(null=True, blank=True)
    is_read = models.BooleanField(default=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:30]}"


class ReminderLog(models.Model):
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)
    mentee = models.ForeignKey(Mentee, on_delete=models.CASCADE)
    last_sent_at = models.DateTimeField(auto_now_add=True)
    is_auto = models.BooleanField(default=False)  # False = manual, True = auto

    def __str__(self):
        return f"Reminder: {self.mentor.user.username} → {self.mentee.user.username} on {self.last_sent_at}"

class ActivityLog(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    action = models.CharField(max_length=500, blank=True, null=True)
    module = models.CharField(max_length=100, blank=True, null=True)  # e.g. "Internship", "Projects"
    details = models.TextField(blank=True, null=True)
    ip_address = models.CharField(null=True, blank=True)
    browser = models.CharField(max_length=255, blank=True, null=True)
    request_path = models.CharField(max_length=500, blank=True, null=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} - {self.action} @ {self.timestamp.strftime('%d-%m-%Y %H:%M')}"


class WeeklyAgenda(models.Model):
    date = models.DateField(null=True, blank=True)
    academic_year = models.CharField(max_length=20, choices=AY, null=True, blank=True)
    week = models.CharField(max_length=15, choices=WEEK_CHOICES, null=True, blank=True)
    year = models.CharField(max_length=5, choices=YEAR_CHOICES, null=True, blank=True)
    sem = models.CharField(max_length=5, choices=SEM_CHOICES, null=True, blank=True)
    agenda_file = models.FileField(upload_to="agendas/", null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_agendas")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-week", "-sem", "-created_at"]

    def __str__(self):
        return f"Week {self.week} - {self.year} - Sem {self.sem}"
