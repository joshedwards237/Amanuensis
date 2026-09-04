"""Panel fakes for `test_overlay`. Separate so the AppKit fake in
`test_indicator` stays the minimum surface Phase 2b needed."""

from __future__ import annotations

from typing import Any


class _FakePanel:
    def __init__(self) -> None:
        self.collection_behavior = 0
        self.ordered_front_regardless = False
        self.ordered_out = False
        self.made_key = False
        self.ignores_mouse = False
        self.level = 0
        self.frame: tuple[float, float, float, float] | None = None
        self.content: Any = None

    def initWithContentRect_styleMask_backing_defer_(
        self, rect: Any, _mask: int, _backing: int, _defer: bool
    ) -> _FakePanel:
        self.frame = rect
        return self

    def setCollectionBehavior_(self, value: int) -> None:
        self.collection_behavior = value

    def setLevel_(self, value: int) -> None:
        self.level = value

    def setIgnoresMouseEvents_(self, value: bool) -> None:
        self.ignores_mouse = value

    def setOpaque_(self, value: bool) -> None:
        pass

    def setBackgroundColor_(self, value: Any) -> None:
        pass

    def setHasShadow_(self, value: bool) -> None:
        pass

    def setContentView_(self, view: Any) -> None:
        self.content = view

    def setFrame_display_(self, rect: Any, _display: bool) -> None:
        self.frame = rect

    def orderFrontRegardless(self) -> None:
        self.ordered_front_regardless = True
        self.ordered_out = False

    def orderOut_(self, _sender: Any) -> None:
        self.ordered_out = True

    def makeKeyAndOrderFront_(self, _sender: Any) -> None:
        self.made_key = True


class _FakeTextField:
    def __init__(self) -> None:
        self.value = ""

    @classmethod
    def alloc(cls) -> _FakeTextField:
        return cls()

    def initWithFrame_(self, _rect: Any) -> _FakeTextField:
        return self

    def setStringValue_(self, value: str) -> None:
        self.value = value

    def __getattr__(self, _name: str) -> Any:
        return lambda *a, **k: None


class _FakeLayer:
    """A `CALayer` stand-in. Records the frame, which is what the waveform
    changes thirty times a second."""

    def __init__(self) -> None:
        self.frame_rect: Any = ((0.0, 0.0), (0.0, 0.0))
        self.corner_radius = 0.0
        self.background: Any = None
        self.sublayers: list[_FakeLayer] = []

    @classmethod
    def layer(cls) -> _FakeLayer:
        return cls()

    def setFrame_(self, rect: Any) -> None:
        self.frame_rect = rect

    def frame(self) -> Any:
        return self.frame_rect

    def setCornerRadius_(self, value: float) -> None:
        self.corner_radius = value

    def setBackgroundColor_(self, value: Any) -> None:
        self.background = value

    def addSublayer_(self, layer: _FakeLayer) -> None:
        self.sublayers.append(layer)


class _FakeView:
    def __init__(self) -> None:
        self._layer = _FakeLayer()
        self.wants_layer = False

    @classmethod
    def alloc(cls) -> _FakeView:
        return cls()

    def initWithFrame_(self, _rect: Any) -> _FakeView:
        return self

    def setWantsLayer_(self, value: bool) -> None:
        self.wants_layer = value

    def layer(self) -> _FakeLayer:
        return self._layer


def install(fake: Any) -> None:
    """Give an AppKit fake the panel surface the overlay needs."""
    fake.panels = []

    class NSPanel:
        @staticmethod
        def alloc() -> _FakePanel:
            panel = _FakePanel()
            fake.panels.append(panel)
            return panel

    fake.NSPanel = NSPanel
    fake.NSTextField = _FakeTextField
    fake.NSView = _FakeView
    fake.CALayer = _FakeLayer
    fake.Quartz = type(
        "Quartz",
        (),
        {"CGColorCreateGenericGray": staticmethod(lambda _g, _a: "cgcolor")},
    )
    fake.NSWindowStyleMaskBorderless = 0
    fake.NSWindowStyleMaskNonactivatingPanel = 128
    fake.NSBackingStoreBuffered = 2
    fake.NSWindowCollectionBehaviorCanJoinAllSpaces = 1
    fake.NSWindowCollectionBehaviorFullScreenAuxiliary = 256
    fake.NSWindowCollectionBehaviorStationary = 16
    fake.NSStatusWindowLevel = 25
    fake.NSMakeRect = staticmethod(lambda x, y, w, h: (x, y, w, h))
    class _Color:
        @staticmethod
        def CGColor() -> str:
            return "cgcolor"

    fake.NSColor = type(
        "NSColor",
        (),
        {
            "clearColor": staticmethod(lambda: "clear"),
            "whiteColor": staticmethod(lambda: "white"),
            "colorWithCalibratedWhite_alpha_": staticmethod(
                lambda _w, _a: _Color()
            ),
        },
    )

    class _Screen:
        @staticmethod
        def frame() -> tuple[tuple[float, float], tuple[float, float]]:
            """The shape PyObjC actually returns for `NSRect`.

            This fake returned a flat 4-tuple until 2026-09-02, when the real
            one crashed a daemon: `NSRect` unpacks as `((x, y), (w, h))`, and
            every overlay test passed against the invented shape.
            """
            return ((0.0, 0.0), (1440.0, 900.0))

    class NSScreen:
        @staticmethod
        def mainScreen() -> _Screen:
            return _Screen()

    fake.NSScreen = NSScreen
