from django import forms

class PDFValidationMixin:
    def clean_certificate(self):
        certificate = self.cleaned_data.get("certificate", False)
        if certificate:
            # ✅ Size check (1 MB)
            if certificate.size > 1024 * 1024:
                raise forms.ValidationError("Certificate size must be less than 1 MB.")

            # ✅ Extension check (case-insensitive)
            if not certificate.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Only PDF files are allowed.")

            # ✅ MIME type check (optional extra safety)
            if hasattr(certificate, "content_type") and certificate.content_type != "application/pdf":
                raise forms.ValidationError("Invalid file type. Upload a valid PDF.")

        return certificate
