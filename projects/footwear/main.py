"""The deployable footwear ASGI app.

TODO(4.4): becomes `app = create_app(FootwearDomain())`. For now chatkit.app
still selects the domain itself via config.CHAT_DOMAIN.
"""
from chatkit.app import app  # noqa: F401
