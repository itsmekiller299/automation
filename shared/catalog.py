"""Demo product catalog used by the sample dataset, FAQ fixtures, and rules.

Replace this with your PIM/catalog integration. Prices are intentionally not
stored here: the bot may only quote prices retrieved from a verified FAQ or
product source, never from model memory.
"""

PRODUCTS = [
    {"id": "aria-lamp", "name": "Aria Lamp", "aliases": ["aria", "aria lamp"], "category": "lighting"},
    {"id": "nimbus-chair", "name": "Nimbus Chair", "aliases": ["nimbus", "nimbus chair"], "category": "seating"},
    {"id": "luna-rug", "name": "Luna Rug", "aliases": ["luna", "luna rug"], "category": "rugs"},
    {"id": "solstice-mug", "name": "Solstice Mug", "aliases": ["solstice", "solstice mug"], "category": "kitchen"},
    {"id": "cloud-sofa", "name": "Cloud Sofa", "aliases": ["cloud sofa", "cloud"], "category": "seating"},
    {"id": "ember-candle", "name": "Ember Candle", "aliases": ["ember candle", "ember"], "category": "decor"},
    {"id": "dune-table", "name": "Dune Table", "aliases": ["dune table", "dune"], "category": "tables"},
    {"id": "terra-planter", "name": "Terra Planter", "aliases": ["terra planter", "terra"], "category": "decor"},
    {"id": "orbit-mirror", "name": "Orbit Mirror", "aliases": ["orbit mirror", "orbit"], "category": "decor"},
    {"id": "moss-throw", "name": "Moss Throw", "aliases": ["moss throw", "moss"], "category": "textiles"},
    {"id": "harbor-shelf", "name": "Harbor Shelf", "aliases": ["harbor shelf", "harbor"], "category": "storage"},
    {"id": "willow-diffuser", "name": "Willow Diffuser", "aliases": ["willow diffuser", "willow"], "category": "decor"},
]

PRODUCT_NAMES = [p["name"] for p in PRODUCTS]
PRODUCT_ALIASES = [alias for p in PRODUCTS for alias in p["aliases"]]
