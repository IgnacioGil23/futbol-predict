"""Ligas publicadas en la web (solo datos: lo importan también la API y la etapa de datos de la imagen Docker).

Cada liga: primera y segunda división de Football-Data, nombre de la competición, slug de la web, zona horaria de
su calendario, puestos de descenso directo de la temporada en curso, puesto de promoción (no cuenta como descenso),
si el primer desempate es el enfrentamiento directo (no se modela en la simulación) y el calendario de openfootball.
"""

OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball"
# Ligas publicadas en la web además de la Premier. "relegation": puestos de descenso directo en la temporada en curso;
# "playoff": puesto que juega la promoción (no cuenta como descenso). Los horarios de openfootball son locales.
LEAGUES: dict[str, dict] = {
    "ESP": {"name": "España", "top": "SP1", "second": "SP2", "competition": "LaLiga", "second_name": "Segunda División",
            "slug": "laliga", "timezone": "Europe/Madrid", "relegation": 3, "playoff": None, "head_to_head": True,
            "schedule_url": OPENFOOTBALL + "/espana/master/{season}/1-liga.txt"},
    "ITA": {"name": "Italia", "top": "I1", "second": "I2", "competition": "Serie A", "second_name": "Serie B",
            "slug": "serie-a", "timezone": "Europe/Rome", "relegation": 3, "playoff": None, "head_to_head": True,
            "schedule_url": OPENFOOTBALL + "/italy/master/{season}/1-seriea.txt"},
    "GER": {"name": "Alemania", "top": "D1", "second": "D2", "competition": "Bundesliga", "second_name": "2. Bundesliga",
            "slug": "bundesliga", "timezone": "Europe/Berlin", "relegation": 2, "playoff": 16, "head_to_head": False,
            "schedule_url": OPENFOOTBALL + "/deutschland/master/{season}/1-bundesliga.txt"},
    "FRA": {"name": "Francia", "top": "F1", "second": "F2", "competition": "Ligue 1", "second_name": "Ligue 2",
            "slug": "ligue-1", "timezone": "Europe/Paris", "relegation": 2, "playoff": 16, "head_to_head": False,
            "schedule_url": OPENFOOTBALL + "/europe/master/france/{season}_fr1.txt"},
}
PRODUCT_LEAGUES: dict[str, dict] = {
    "ENG": {"name": "Inglaterra", "top": "E0", "second": "E1", "competition": "Premier League",
            "second_name": "Championship", "slug": "premier", "timezone": "Europe/London", "relegation": 3,
            "playoff": None, "head_to_head": False,
            "schedule_url": OPENFOOTBALL + "/england/master/{season}/1-premierleague.txt"},
    **LEAGUES,
}
