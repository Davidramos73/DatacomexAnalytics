"""The deployable footwear ASGI app."""
from chatkit import create_app
from projects.footwear.domain import FootwearDomain

app = create_app(FootwearDomain())
