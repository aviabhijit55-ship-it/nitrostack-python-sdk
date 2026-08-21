from nitrostack import ExecutionContext
from nitrostack.auth.oauth import is_oauth_required

def create_scope_guard(required_scopes: list):
    class ScopeGuard:
        async def can_activate(self, context: ExecutionContext) -> bool:
            # TS tools only use OAuthGuard; scope checks apply when auth is enforced.
            if not is_oauth_required():
                return True
            user_scopes = getattr(context.auth, "scopes", []) or []
            missing_scopes = [s for s in required_scopes if s not in user_scopes]
            if missing_scopes:
                raise ValueError(
                    f"Insufficient scope. Required: {', '.join(required_scopes)}. "
                    f"Missing: {', '.join(missing_scopes)}"
                )
            return True
    return ScopeGuard
