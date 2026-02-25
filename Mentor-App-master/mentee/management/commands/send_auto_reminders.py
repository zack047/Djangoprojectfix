from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from ...models import Mentor, MentorMentee, ReminderLog, Notification
from ...utils import get_document_progress
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = "Send automatic reminders every 7 days to mentees with pending documents"

    def handle(self, *args, **options):
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        for mapping in MentorMentee.objects.select_related("mentor__user", "mentee__user"):
            mentor = mapping.mentor
            mentee = mapping.mentee
            user = mentee.user

            completed_count, total_required, has_pending = get_document_progress(user)

            if not has_pending:
                continue  # no pending docs, skip

            # Check last reminder
            last_reminder = ReminderLog.objects.filter(mentor=mentor, mentee=mentee).order_by("-last_sent_at").first()

            if last_reminder and last_reminder.last_sent_at > seven_days_ago:
                # Last reminder was within 7 days → skip
                continue

            # 1️⃣ Create notification
            Notification.objects.create(
                user=user,
                message="⏰ Auto Reminder: Please complete your pending profile documents."
            )

            # 2️⃣ Send email
            if user.email:
                send_mail(
                    subject="Auto Reminder: Complete Your Profile Documents",
                    message=(
                        f"Dear {user.profile.student_name}({user.username}),\n\n"
                        f"Your mentor {mentor.name} has reminded you to upload your pending documents.\n"
                        f"You need to complete the profile and pending uploads\n"
                        f"Please log in to MentorConnect and upload them as soon as possible.\n\n"
                        f"Regards,\nMentorConnect Team\n\n\n"
                        f"*This is a system generated mail do not reply to it.*"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )

            # 3️⃣ Log Reminder (auto)
            ReminderLog.objects.create(
                mentor=mentor,
                mentee=mentee,
                is_auto=True,
            )

            self.stdout.write(self.style.SUCCESS(f"Auto reminder sent to {user.username} - {user.profile.student_name}"))
