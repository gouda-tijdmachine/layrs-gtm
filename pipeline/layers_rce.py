"""The "rce" layer set: context layers any Dutch municipality can build from the national registers.

Every source is fetched by s00_fetch_rce (monument register, CC0): the monuments with their BAG panden, the
register's descriptions and styles, and the protected townscapes. Texts name the city from its config, in English
and Dutch; group labels carry their Dutch as a third element.
"""
import json
import re
from pathlib import Path

import geopandas as gpd

from .city import LABEL
from .layers import RAW, by_monument, layer, monuments, rce_texts, within

REGISTER = ("Rijksmonumentenregister, RCE", "https://monumentenregister.cultureelerfgoed.nl")

FUNCTIONS = [
    # (group, label, label_nl, pattern on the original function as the register names it)
    ("home", "Houses", "Woonhuizen", r"woonhuis|woning|landhuis|pastorie|koetshuis|herenhuis|villa"),
    ("faith", "Faith and care", "Geloof en zorg",
     r"kerk|kapel|klooster|synagoge|hofje|gasthuis|zorg|liefdadig|infirmerie|gesticht|begraaf|graf"),
    ("defence", "Defence", "Verdediging", r"kazemat|stelling|fort|vesting|kazerne|tankhindernis|poort|stadsmuur|wal"),
    ("work", "Trade and work", "Handel en bedrijf",
     r"opslag|pakhuis|werkplaats|winkel|handel|kantoor|industrie|fabriek|molen|bank|waag|boerderij|stal|melk"),
    ("works", "Water, power and roads", "Water, energie en verkeer",
     r"transformator|watertoren|pomp|brug|stuw|sluis|transport|station|weeg"),
    ("green", "Gardens and parks", "Tuinen en parken", r"tuin|park|plantsoen|aanleg|orangerie"),
]


@layer(
    set="rce", id="register", section="Architecture", section_nl="Architectuur",
    title="National monuments", title_nl="Rijksmonumenten", era="All periods", era_nl="Alle perioden",
    text=(f"The State lists the buildings of national value in {LABEL} in its monument register, with what each "
          "was built for: houses, churches and convents, defences, warehouses and shops, waterworks, gardens."),
    text_nl=(f"Het Rijk legt de gebouwen van nationale waarde in {LABEL} vast in het monumentenregister, met waarvoor "
             "elk gebouwd werd: woonhuizen, kerken en kloosters, verdediging, pakhuizen en winkels, waterwerken, tuinen."),
    caveat="Grouped by the original function the register gives; a monument without one is left out.",
    caveat_nl="Gegroepeerd naar de oorspronkelijke functie die het register noemt; een monument zonder functie valt weg.",
    source=REGISTER,
    groups=[(k, label, nl) for k, label, nl, _ in FUNCTIONS],
)
def register():
    keyed = {}
    for m in monuments():
        f = (m.get("function") or "").lower()
        k = next((k for k, _, _, pat in FUNCTIONS if re.search(pat, f)), None)
        if k:
            keyed[str(m["nr"])] = k
    return by_monument(keyed)


@layer(
    set="rce", id="gables", section="Architecture", section_nl="Architectuur",
    title="Gables", title_nl="Gevels", era="1500–1800", era_nl="1500–1800",
    text=("An old town house shows its age in its top. Stepped gables belong to the late Middle Ages and the early "
          "1600s, neck gables to the middle of that century, bell gables to the decades around 1700, and the flat "
          "cornice to the 1700s and after."),
    text_nl=("Een oud stadshuis toont zijn leeftijd in de top. Trapgevels horen bij de late middeleeuwen en de vroege "
             "zeventiende eeuw, halsgevels bij het midden van die eeuw, klokgevels bij de jaren rond 1700 en de "
             "rechte lijst bij de achttiende eeuw en later."),
    caveat="Listed houses only: the register's description names the gable.",
    caveat_nl="Alleen rijksmonumenten: de omschrijving in het register noemt de gevel.",
    source=REGISTER,
    groups=[("trap", "Stepped gable", "Trapgevel"), ("hals", "Neck gable", "Halsgevel"),
            ("klok", "Bell gable", "Klokgevel"), ("lijst", "Cornice", "Rechte lijst")],
)
def gables():
    pats = [("trap", r"trapgevel"), ("hals", r"halsgevel"), ("klok", r"klokgevel"),
            ("lijst", r"rechte lijst|lijstgevel|verhoogde lijst")]
    keyed = {}
    for nr, t in rce_texts().items():
        t = t.lower()
        hits = [(m.start(), k) for k, p in pats for m in [re.search(p, t)] if m]
        if hits:
            keyed[nr] = min(hits)[1]  # the first gable named is the house's own
    return by_monument(keyed)


STYLES = [
    # (group, label, label_nl, the register's style names)
    ("classic", "Classicism", "Classicisme", ("Hollands classicisme", "Neo-Classicisme", "Um 1800-stijl", "Lodewijk XIV",
                                              "Lodewijk XV", "Lodewijk XVI", "Empire")),
    ("neo", "Neo-styles", "Neostijlen", ("Neo-Renaissance", "Neo-Hollandse Renaissance", "Neo-Franse Renaissance",
                                         "Neo-Gotiek", "Neo-Romaanse stijl", "Neo-Barok", "Eclecticisme")),
    ("villa", "Chalets, cottages and Art Nouveau", "Chalets, cottages en jugendstil",
     ("Chalet-stijl", "Cottage-stijl", "Overgangsarchitectuur", "Art Nouveau", "Jugendstil", "Wrightiaanse stijl")),
    ("as", "Amsterdam School and Dudok", "Amsterdamse School en Dudok",
     ("Amsterdamse school", "Late Amsterdamse school", "Zakelijk Expressionisme", "Expressionisme", "Dudok-trant",
      "Art Déco")),
    ("trad", "Traditionalism", "Traditionalisme", ("Traditionalisme", "Delftse School", "ambachtelijk-traditionele bouwtrant")),
    ("modern", "Rationalism and Nieuwe Bouwen", "Rationalisme en Nieuwe Bouwen",
     ("Rationalisme", "Berlagianisme", "Nieuwe Bouwen", "Functionalisme", "Nieuwe Zakelijkheid")),
]


@layer(
    set="rce", id="styles", section="Architecture", section_nl="Architectuur",
    title="Architecture styles", title_nl="Bouwstijlen", era="1800–1940", era_nl="1800–1940",
    text=(f"From the sober classicism around 1800, through the revival styles and the villa parks of the railway era, "
          f"to the brick expressionism and the Nieuwe Bouwen between the wars: {LABEL} tried on the styles of its time."),
    text_nl=(f"Van het sobere classicisme rond 1800, via de neostijlen en de villaparken van de spoorwegtijd, naar het "
             f"baksteenexpressionisme en het Nieuwe Bouwen tussen de oorlogen: {LABEL} paste de stijlen van zijn tijd."),
    caveat="Listed buildings only: the register names a style for part of the national monuments.",
    caveat_nl="Alleen rijksmonumenten: het register noemt bij een deel van de monumenten een stijl.",
    source=REGISTER,
    groups=[(k, label, nl) for k, label, nl, _ in STYLES],
)
def styles():
    to_group = {s.lower(): k for k, _, _, names in STYLES for s in names}
    keyed = {}
    for r in json.load(open(f"{RAW}/rce_styles.json", encoding="utf-8")):
        g = to_group.get(r["style"].lower())
        if g:
            keyed.setdefault(r["nr"], g)
    return by_monument(keyed)


def _townscapes() -> gpd.GeoDataFrame:
    f = Path(f"{RAW}/gezichten.geojson")
    g = gpd.read_file(f).set_crs(28992, allow_override=True) if f.exists() else gpd.GeoDataFrame(
        {"nr": [], "naam": []}, geometry=[], crs=28992)
    g["nr"] = g.nr.astype(str)
    return g


@layer(
    set="rce", id="townscapes", section="Architecture", section_nl="Architectuur",
    title="Protected townscapes", title_nl="Beschermde gezichten", era="All periods", era_nl="Alle perioden",
    text=("Beyond single buildings the State protects whole areas whose streets, buildings and greenery together "
          "tell the history of a place: the beschermde stads- en dorpsgezichten."),
    text_nl=("Naast losse gebouwen beschermt het Rijk hele gebieden waarvan straten, bebouwing en groen samen de "
             "geschiedenis van een plek vertellen: de beschermde stads- en dorpsgezichten."),
    caveat="Every building whose centre lies inside the protected area, listed or not.",
    caveat_nl="Elk gebouw waarvan het midden binnen het beschermde gebied ligt, monument of niet.",
    source=("Beschermde stads- en dorpsgezichten, RCE", "https://linkeddata.cultureelerfgoed.nl"),
    groups=[(str(nr), naam, naam) for nr, naam in zip(_townscapes().nr, _townscapes().naam)],
)
def townscapes():
    g = _townscapes()
    return within(g, "nr") if len(g) else {}


@layer(
    set="rce", id="heritage", section="Architecture", section_nl="Architectuur",
    title="Protected heritage", title_nl="Beschermd erfgoed", era="All periods", era_nl="Alle perioden",
    text=f"The buildings of {LABEL} that the State lists as national monuments.",
    text_nl=f"De gebouwen in {LABEL} die het Rijk als rijksmonument beschermt.",
    source=REGISTER,
    groups=[("Rijksmonument", "National monument", "Rijksmonument")],
)
def heritage():
    return {p: "Rijksmonument" for m in monuments() for p in m["panden"]}
