"""ka11y.auth — OAuth 2.0 / OpenID Connect sign-in and cookie sessions.

    from ka11y.auth import require_user, CurrentUser
"""

from ka11y.auth.dependencies import ANONYMOUS, CurrentUser, optional_user, require_user

__all__ = ["ANONYMOUS", "CurrentUser", "optional_user", "require_user"]
