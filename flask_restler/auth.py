from __future__ import absolute_import

try:
    from flask_login import current_user
except ImportError:
    class current_user:
        is_authenticated = False
        is_anonimous = True

        @staticmethod
        def get_id():
            return None
