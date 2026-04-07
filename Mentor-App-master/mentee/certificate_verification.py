import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

import requests
from django.utils import timezone

try:
    import cv2
except Exception:
    cv2 = None

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


def _normalize(text: str) -> str:
    base = (text or "")
    # OCR/extracted text can split acronyms like "A W S"; compact them first.
    base = re.sub(
        r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b",
        lambda m: re.sub(r"\s+", "", m.group(0)),
        base,
    )
    return re.sub(r"\s+", " ", base.lower()).strip()


def _tokens(text: str):
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2]


def _token_match_ratio(source_text: str, expected_text: str) -> float:
    expected = _tokens(expected_text)
    if not expected:
        return 0.0

    source_tokens = _tokens(source_text)
    source_set = set(source_tokens)
    source_compact = re.sub(r"[^a-z0-9]+", "", (source_text or "").lower())

    def _is_matched(token: str) -> bool:
        if token in source_set:
            return True
        if len(token) >= 4 and token in source_compact:
            return True
        for src in source_tokens:
            if len(token) >= 4 and len(src) >= 4 and (token in src or src in token):
                return True
        return False

    matched = sum(1 for t in expected if _is_matched(t))
    return matched / max(len(expected), 1)


def _name_match_ok(source_text: str, expected_name: str) -> bool:
    expected_tokens = _tokens(expected_name)
    if not expected_tokens:
        return False

    source_set = set(_tokens(source_text))
    matched_count = sum(1 for t in expected_tokens if t in source_set)
    ratio = matched_count / max(len(expected_tokens), 1)

    # Accept partial-name matches when at least two meaningful name tokens match.
    if matched_count >= min(2, len(expected_tokens)) and ratio >= 0.5:
        return True

    # For 2-part names, allow first-name-only certificates when other checks pass.
    if len(expected_tokens) == 2 and matched_count >= 1 and ratio >= 0.5:
        return True

    # For very short names (1 token), require full match.
    if len(expected_tokens) <= 2 and matched_count == len(expected_tokens):
        return True

    return ratio >= 0.7


def _extract_pdf_text(file_path: str) -> str:
    if not PdfReader:
        return ""
    try:
        reader = PdfReader(file_path)
    except Exception:
        return ""

    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _extract_qr_payloads_from_pdf(file_path: str, max_pages: int = 3):
    if not cv2 or not pdfium:
        return [], "QR scanner dependencies are unavailable"

    payloads = []
    detector = cv2.QRCodeDetector()

    def _decode_from_image(img):
        decoded = []
        variants = [img]
        gray = None
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            variants.append(gray)
        else:
            gray = img

        try:
            variants.append(cv2.equalizeHist(gray))
        except Exception:
            pass
        try:
            variants.append(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 11))
        except Exception:
            pass
        try:
            variants.append(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        except Exception:
            pass
        try:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            variants.append(cv2.dilate(gray, kernel, iterations=1))
        except Exception:
            pass

        for variant in variants:
            try:
                ok, infos, _, _ = detector.detectAndDecodeMulti(variant)
                if ok and infos:
                    for info in infos:
                        if info and info.strip():
                            decoded.append(info.strip())
            except Exception:
                pass

            try:
                single_info, _, _ = detector.detectAndDecode(variant)
                if single_info and single_info.strip():
                    decoded.append(single_info.strip())
            except Exception:
                pass

        return decoded

    try:
        doc = pdfium.PdfDocument(file_path)
    except Exception as exc:
        return [], f"Unable to open PDF for QR scan: {exc}"

    try:
        total_pages = min(len(doc), max_pages)
        scales = (2, 3, 4)
        for page_index in range(total_pages):
            for scale in scales:
                page = doc[page_index]
                bmp = page.render(scale=scale)
                img = bmp.to_numpy()
                if img is None:
                    continue

                if len(img.shape) == 3 and img.shape[2] == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)

                decoded_items = _decode_from_image(img)
                if decoded_items:
                    payloads.extend(decoded_items)
    finally:
        doc.close()

    unique = []
    seen = set()
    for p in payloads:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique, ""


def _is_safe_public_url(url: str):
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return False, "Unsupported URL scheme"

    host = (parsed.hostname or "").strip()
    if not host:
        return False, "URL hostname missing"

    if host in ("localhost", "127.0.0.1"):
        return False, "Localhost URLs are blocked"

    try:
        ip_str = socket.gethostbyname(host)
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, "Private/reserved target blocked"
    except Exception:
        return False, "Hostname resolution failed"

    return True, ""


def _validate_qr_payload(payload: str, expected_name: str, expected_title: str, expected_authority: str):
    payload_text = _normalize(payload)

    if payload_text.startswith("http://") or payload_text.startswith("https://"):
        safe, reason = _is_safe_public_url(payload)
        if not safe:
            return False, True, False, reason

        try:
            response = requests.get(payload, timeout=8, allow_redirects=True)
        except Exception as exc:
            return False, True, False, f"QR URL request failed: {exc}"

        if response.status_code >= 400:
            return False, True, False, f"QR URL returned HTTP {response.status_code}"

        page_text = _normalize(response.text[:300000])
        name_ratio = _token_match_ratio(page_text, expected_name)
        title_ratio = _token_match_ratio(page_text, expected_title)
        authority_ratio = _token_match_ratio(page_text, expected_authority)

        parsed = urlparse(payload)
        host = (parsed.netloc or "").lower()
        path_and_query = f"{parsed.path or ''} {parsed.query or ''}".lower()
        verification_endpoint_hint = any(
            token in path_and_query for token in ("verify", "cert", "certificate", "credential", "token", "id=")
        )
        trusted_host_hint = any(
            token in host for token in ("eduskillsfoundation.org", "cognitiveclass.ai", "coursera.org", "udemy.com")
        )

        looks_valid = (
            name_ratio >= 0.45
            or (title_ratio >= 0.45 and authority_ratio >= 0.45)
            or verification_endpoint_hint
            or trusted_host_hint
        )
        note = "QR URL reachable"
        if looks_valid and (verification_endpoint_hint or trusted_host_hint):
            note += "; certificate verification URL pattern matched"
        elif looks_valid:
            note += "; matched credential metadata"
        else:
            note += "; no strong metadata match"
        return looks_valid, True, True, note

    name_ratio = _token_match_ratio(payload_text, expected_name)
    title_ratio = _token_match_ratio(payload_text, expected_title)
    authority_ratio = _token_match_ratio(payload_text, expected_authority)
    looks_valid = name_ratio >= 0.6 or (title_ratio >= 0.5 and authority_ratio >= 0.5)
    return looks_valid, False, False, "QR payload parsed"



def _extract_urls_from_text(text: str):
    return re.findall(r"https?://[^\s)\]>]+", text or "", flags=re.IGNORECASE)
def verify_course_certificate(course):
    result = {
        "verification_status": "verify_physically",
        "verification_notes": "",
        "verification_checked_at": timezone.now(),
        "qr_detected": False,
        "qr_payload": "",
        "qr_url_checked": False,
        "qr_url_accessible": False,
    }

    if not course.certificate:
        result["verification_notes"] = "No certificate file uploaded"
        return result

    try:
        file_path = course.certificate.path
    except Exception as exc:
        result["verification_notes"] = f"Could not resolve certificate path: {exc}"
        return result

    if not file_path or not os.path.exists(file_path):
        result["verification_notes"] = "Certificate file is missing on server"
        return result

    full_text = _normalize(_extract_pdf_text(file_path))
    expected_name = ""
    profile_name = ""
    profile_moodle_id = ""
    if course.user:
        try:
            profile_name = (course.user.profile.student_name or "").strip()
            profile_moodle_id = (course.user.profile.moodle_id or "").strip()
        except Exception:
            profile_name = ""
            profile_moodle_id = ""
        expected_name = profile_name

    title = (course.title or "").strip()
    authority = (course.certifying_authority or "").strip()

    name_ratio = _token_match_ratio(full_text, expected_name)
    title_ratio = _token_match_ratio(full_text, title)
    authority_ratio = _token_match_ratio(full_text, authority)

    qr_payloads, qr_error = _extract_qr_payloads_from_pdf(file_path)

    if not qr_payloads:
        fallback_urls = _extract_urls_from_text(full_text)
        if fallback_urls:
            qr_payloads = list(dict.fromkeys(fallback_urls[:5]))
            if qr_error:
                qr_error += " | "
            qr_error += "QR image not decoded; using verification URL detected from certificate text"

    result["qr_detected"] = bool(qr_payloads)
    if qr_payloads:
        result["qr_payload"] = "\n".join(qr_payloads[:5])

    notes = []
    diagnostics = []
    qr_valid = False

    if qr_error:
        diagnostics.append(qr_error)

    if qr_payloads:
        for payload in qr_payloads[:3]:
            is_valid, url_checked, url_accessible, reason = _validate_qr_payload(
                payload,
                expected_name,
                title,
                authority,
            )
            if url_checked:
                result["qr_url_checked"] = True
            if url_accessible:
                result["qr_url_accessible"] = True
            diagnostics.append(reason)
            if is_valid:
                qr_valid = True
                break
    else:
        diagnostics.append("No QR code detected in first pages of certificate")

    name_required = bool(profile_name)
    name_ok = _name_match_ok(full_text, expected_name) if expected_name else False
    title_ok = title_ratio >= 0.45 if title else True
    authority_ok = authority_ratio >= 0.45 if authority else True
    profile_ready = bool(profile_name and profile_moodle_id)
    strong_text_match = name_ok and title_ok and authority_ok
    qr_name_match = qr_valid and name_ok

    if profile_ready and (qr_name_match or strong_text_match or (name_ok and title_ratio >= 0.4 and authority_ratio >= 0.35)):
        result["verification_status"] = "verified"
        if qr_name_match:
            notes.append("Certificate verified by QR and student-name match")
            if not title_ok:
                notes.append("Note: course title text did not strongly match")
            if not authority_ok:
                notes.append("Note: certifying authority text did not strongly match")
        elif qr_valid:
            notes.append("Certificate verified by QR and content match")
        else:
            notes.append("Certificate verified by strong content match")
    else:
        result["verification_status"] = "verify_physically"
        if not profile_name:
            notes.append("Profile student name is missing")
        if not profile_moodle_id:
            notes.append("Profile Moodle ID is missing")
        if name_required and not name_ok:
            notes.append("Student name on certificate does not match your profile name")
        if not title_ok:
            notes.append("Course title on certificate does not match entered course title")
        if not authority_ok:
            notes.append("Certifying authority on certificate does not match entered authority")
        if not qr_valid:
            notes.append("QR/verification URL could not be validated automatically")
        if not notes and diagnostics:
            notes.append("Automatic checks were inconclusive")
        notes.append("Automatic verification not conclusive; physical verification required")

    result["verification_notes"] = " | ".join(notes)[:2000]
    return result


def apply_course_certificate_verification(course, save=True):
    data = verify_course_certificate(course)
    for key, value in data.items():
        setattr(course, key, value)

    if save:
        course.save(
            update_fields=[
                "verification_status",
                "verification_notes",
                "verification_checked_at",
                "qr_detected",
                "qr_payload",
                "qr_url_checked",
                "qr_url_accessible",
            ]
        )
    return data



