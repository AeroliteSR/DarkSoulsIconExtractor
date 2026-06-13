from enum import Enum, auto

class ExportMode(Enum):
    ATLAS = auto()
    SUBTEXTURE = auto()

class GameType(Enum):
    OLD = auto()
    MODERN = auto()
    PS = auto()

class Modified(Enum):
    FALSE = auto()
    ADDED = auto()
    REPLACED = auto()

class ImageType(Enum):
    Atlas = auto()
    Texture = auto()
    Subtexture = auto()
    Custom = auto()

class IconMode(Enum):
    Define = auto()
    Append = auto()

class Game():
    OLD_GAMES = {"Dark Souls 1", "Dark Souls 2", "Dark Souls 3"}
    PS_GAMES = {"Bloodborne", "Demon's Souls"}

    def __init__(self, name: str):
        self.name = name
        self.type = self.classify(name)

    def classify(self, name: str | None) -> GameType | None:
        if name is None:
            return None

        if name in self.OLD_GAMES:
            return GameType.OLD
        elif name in self.PS_GAMES:
            return GameType.PS
        else:
            return GameType.MODERN

    def __repr__(self):
        type_name = self.type.name if self.type else None
        return f"Game({self.name}, {type_name})"

class Resolution(Enum):
    HIGH = auto()
    LOW = auto()

    @property
    def display(self):
        return {
            Resolution.HIGH: "High",
            Resolution.LOW: "Low"
        }[self]

class ResFormat(Enum):
    NIGHTREIGN = ("Nightreign", {Resolution.HIGH: "High", Resolution.LOW: "Low"})
    ELDEN_RING = ("Elden Ring", {Resolution.HIGH: "Hi", Resolution.LOW: "Low"})
    SEKIRO = ("Sekiro", {Resolution.HIGH: "Hi", Resolution.LOW: "Low"})

    @property
    def game_name(self):
        return self.value[0]

    @property
    def mapping(self):
        return self.value[1]

    def get(self, resolution: Resolution) -> str:
        return self.mapping[resolution]

    @classmethod
    def from_name(cls, name: str) -> "ResFormat":
        for g in cls:
            if g.game_name == name:
                return g
        raise ValueError(f"Unknown game: {name}")
