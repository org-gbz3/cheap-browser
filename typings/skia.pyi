from typing import Any, SupportsFloat, SupportsIndex, SupportsInt

class FontStyle:
    class Weight: ...
    class Slant: ...
    class Width: ...
    kBold_Weight: Weight
    kNormal_Weight: Weight
    kItalic_Slant: Slant
    kUpright_Slant: Slant
    kNormal_Width: Width
    def __init__(
        self,
        weight: Weight | SupportsInt | SupportsIndex = ...,
        width: Width | SupportsInt | SupportsIndex = ...,
        slant: Slant = ...,
    ) -> None: ...

class Typeface:
    def __init__(self, familyName: object = None, fontStyle: FontStyle | None = None) -> None: ...
    @staticmethod
    def MakeFromName(familyName: object, fontStyle: FontStyle | None = None) -> Typeface: ...

class FontMetrics:
    fAscent: float
    fDescent: float
    fLeading: float
    fTop: float
    fBottom: float

class Font:
    def __init__(
        self, typeface: object = None, size: SupportsFloat | SupportsIndex = 0
    ) -> None: ...
    def measureText(self, text: str) -> int: ...
    def getMetrics(self) -> FontMetrics: ...

class Path:
    def __init__(self) -> None: ...
    def moveTo(
        self, x: SupportsFloat | SupportsIndex, y: SupportsFloat | SupportsIndex
    ) -> Path: ...
    def lineTo(
        self, x: SupportsFloat | SupportsIndex, y: SupportsFloat | SupportsIndex
    ) -> Path: ...

class Paint:
    class Style: ...
    kStroke_Style: Style
    def __init__(self, **kwargs: Any) -> None: ...

class ColorType: ...
class AlphaType: ...
class ColorSpace: ...
class SurfaceProps: ...

class Rect:
    @staticmethod
    def MakeLTRB(
        l: SupportsFloat | SupportsIndex,
        t: SupportsFloat | SupportsIndex,
        r: SupportsFloat | SupportsIndex,
        b: SupportsFloat | SupportsIndex,
    ) -> Rect: ...
    def top(self) -> int: ...
    def bottom(self) -> int: ...
    def left(self) -> int: ...
    def right(self) -> int: ...
    def width(self) -> int: ...
    def height(self) -> int: ...
    def makeOffset(
        self, dx: SupportsFloat | SupportsIndex, dy: SupportsFloat | SupportsIndex
    ) -> Rect: ...
    def contains(
        self, x: SupportsFloat | SupportsIndex, y: SupportsFloat | SupportsIndex
    ) -> bool: ...

class RRect:
    @staticmethod
    def MakeRectXY(
        rect: Rect,
        xRad: SupportsFloat | SupportsIndex,
        yRad: SupportsFloat | SupportsIndex,
    ) -> RRect: ...
    def makeOffset(
        self,
        dx: SupportsFloat | SupportsIndex,
        dy: SupportsFloat | SupportsIndex,
    ) -> RRect: ...

class Canvas:
    def clear(self, color: SupportsInt | SupportsIndex) -> None: ...
    def drawPath(self, path: Path, paint: Paint) -> None: ...
    def drawRect(self, rect: Rect, paint: Paint) -> None: ...
    def drawRRect(self, rrect: RRect, paint: Paint) -> None: ...
    def drawString(
        self,
        text: str,
        x: SupportsFloat | SupportsIndex,
        y: SupportsFloat | SupportsIndex,
        font: Font,
        paint: Paint,
    ) -> None: ...

class Image:
    def tobytes(self) -> bytes: ...

class ImageInfo:
    @staticmethod
    def Make(
        width: SupportsInt | SupportsIndex,
        height: SupportsInt | SupportsIndex,
        ct: ColorType,
        at: AlphaType,
        cs: ColorSpace | None = None,
    ) -> ImageInfo: ...

class Surface:
    @staticmethod
    def MakeRaster(
        imageInfo: ImageInfo,
        rowBytes: SupportsInt | SupportsIndex = 0,
        surfaceProps: SurfaceProps | None = None,
    ) -> Surface: ...
    def getCanvas(self) -> Canvas: ...
    def makeImageSnapshot(self) -> Image: ...

ColorBLACK: int
ColorWHITE: int
kRGBA_8888_ColorType: ColorType
kUnpremul_AlphaType: AlphaType

def Color(
    r: SupportsInt | SupportsIndex,
    g: SupportsInt | SupportsIndex,
    b: SupportsInt | SupportsIndex,
    a: SupportsInt | SupportsIndex = 255,
) -> int: ...
