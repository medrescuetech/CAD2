"""
Patch for Flask-ReCaptcha to fix Markup import issue
"""
from markupsafe import Markup
import importlib.util
import sys

# Check if flask_recaptcha is in the modules
if 'flask_recaptcha' in sys.modules:
    # Monkey patch the Markup class directly into the flask_recaptcha module
    flask_recaptcha = sys.modules['flask_recaptcha']
    flask_recaptcha.Markup = Markup
    print("ReCaptcha patch applied - fixed Markup import for flask_recaptcha module")

# Fix for when the module is imported later
original_import = __import__

def patched_import(name, *args, **kwargs):
    module = original_import(name, *args, **kwargs)
    if name == 'flask_recaptcha':
        module.Markup = Markup
        print("ReCaptcha patch applied - fixed Markup import during import")
    return module

sys.modules['builtins'].__import__ = patched_import
