import threading

_thread_locals = threading.local()

def set_current_request(request):
    _thread_locals.request = request

def get_current_request():
    return getattr(_thread_locals, "request", None)

def clear_current_request():
    if hasattr(_thread_locals, "request"):
        del _thread_locals.request