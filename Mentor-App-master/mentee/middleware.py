from .request_local import set_current_request, clear_current_request

class RequestCaptureMiddleware:
    """
    Stores the current request in thread-local storage so signals can read IP/user/UA/path.
    Add 'mentee.middleware.RequestCaptureMiddleware' early in MIDDLEWARE.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            response = self.get_response(request)
            return response
        finally:
            clear_current_request()
