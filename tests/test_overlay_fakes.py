"""Panel fakes for `test_overlay`. Separate so the AppKit fake in
`test_indicator` stays the minimum surface Phase 2b needed."""

from __future__ import annotations

from typing import Any, ClassVar


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
        self.frames_set = 0
        #: `setFrame:display:animate:` — the call that blocks the main queue
        #: for the length of the animation. Recorded so a test can assert it is
        #: never made, which is the only assertion that protects the daemon.
        self.animated_frames: list[Any] = []
        self.owner: Any = None

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

    def setFrame_display_animate_(
        self, rect: Any, _display: bool, animate: bool
    ) -> None:
        if animate:
            self.animated_frames.append(rect)
        self.setFrame_display_(rect, _display)

    def setFrame_display_(self, rect: Any, _display: bool) -> None:
        self.frame = rect
        self.frames_set += 1

    def _maybe_fail(self) -> None:
        """Raise if the owning fake is armed. Added 2026-09-10.

        Arming `NSPanel.alloc` only fails a render that *builds*, and the
        overlay builds once — so a second burst of injected failures silently
        injected nothing, and a test of the failure budget could not fail. The
        show and hide calls happen on every render whether or not a panel
        already exists, which is where a render failure has to be injected to
        mean anything.
        """
        owner = self.owner
        if owner is not None and getattr(owner, "render_failures", 0) > 0:
            owner.render_failures -= 1
            raise RuntimeError("AppKit said no")

    def orderFrontRegardless(self) -> None:
        self._maybe_fail()
        self.ordered_front_regardless = True
        self.ordered_out = False

    def orderOut_(self, _sender: Any) -> None:
        self._maybe_fail()
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
        #: Which form is drawn. The bars and the idle dot share a parent and
        #: are toggled rather than rebuilt, so this is how a test tells the
        #: idle pill from the recording one.
        self.hidden = False
        self.border_width = 0.0
        self.border_color: Any = None

    @classmethod
    def layer(cls) -> _FakeLayer:
        return cls()

    def setFrame_(self, rect: Any) -> None:
        """Validated, because the un-validated version shipped a crash.

        PyObjC depythonifies an `NSRect` as `((x, y), (width, height))` — two
        members, nested. A flat four-tuple raises
        `ValueError: depythonifying struct of 2 members, got tuple of 4`, and
        on 2026-09-17 the idle pill shipped with exactly that: `pill_frame`
        returns the module's flat convention and it was handed to `setFrame_`
        without conversion.

        **The suite was green the whole time**, because this method used to
        store whatever it was given. A fake that accepts a shape the framework
        rejects is not a test double, it is a second implementation with a
        bug — and it is the *forgiving* direction, which is the one that
        cannot be caught by reading. The module preamble already records the
        same error crashing a daemon on 2026-09-02 with every test passing
        against a flat fake; this is the second occurrence and the first one
        this file could have prevented.
        """
        if not (
            isinstance(rect, tuple)
            and len(rect) == 2
            and all(isinstance(part, tuple) and len(part) == 2 for part in rect)
        ):
            raise ValueError(
                f"depythonifying struct of 2 members, got tuple of {len(rect)}"
            )
        self.frame_rect = rect

    def frame(self) -> Any:
        return self.frame_rect

    def setCornerRadius_(self, value: float) -> None:
        self.corner_radius = value

    def setBackgroundColor_(self, value: Any) -> None:
        self.background = value

    def setBorderWidth_(self, value: float) -> None:
        self.border_width = value

    def setBorderColor_(self, value: Any) -> None:
        self.border_color = value

    def setHidden_(self, value: bool) -> None:
        self.hidden = bool(value)

    def isHidden(self) -> bool:
        return self.hidden

    def addSublayer_(self, layer: _FakeLayer) -> None:
        self.sublayers.append(layer)


class _FakeTextLayer(_FakeLayer):
    """A `CATextLayer`. The string is the assertion for the two controls —
    a ✕ drawn where ✓ belongs is a destructive button wearing the safe one's
    glyph, which no geometry check can see."""

    def __init__(self) -> None:
        super().__init__()
        self.string_value = ""
        self.font_size = 0.0
        self.alignment = ""
        self.foreground: Any = None
        self.contents_scale = 1.0

    def setString_(self, value: str) -> None:
        self.string_value = value

    def setFontSize_(self, value: float) -> None:
        self.font_size = value

    def setAlignmentMode_(self, value: str) -> None:
        self.alignment = value

    def setForegroundColor_(self, value: Any) -> None:
        self.foreground = value

    def setContentsScale_(self, value: float) -> None:
        self.contents_scale = value


class _FakeView:
    """Stands in for the click-taking container view.

    `click(x, y)` is how a test presses a control: the real view converts an
    `NSEvent`'s window coordinates and calls `handler`, and reproducing an
    `NSEvent` here would be faking AppKit rather than testing the overlay.
    What matters is that the overlay's handler receives view coordinates, which
    is exactly what this hands it.
    """

    def __init__(self) -> None:
        self._layer = _FakeLayer()
        self.wants_layer = False
        self.handler: Any = None
        self.frame_rect: Any = None

    def click(self, x: float, y: float) -> None:
        assert self.handler is not None, "nothing is listening for clicks"
        self.handler(x, y)

    #: Every view built, in order, so a test can press the one on screen.
    #: Assigned by `install` — a class attribute rather than a parameter,
    #: because `alloc` is a classmethod on AppKit's side and has nowhere to
    #: take one.
    built: ClassVar[list[_FakeView]] = []

    @classmethod
    def alloc(cls) -> _FakeView:
        view = cls()
        cls.built.append(view)
        return view

    def initWithFrame_(self, rect: Any) -> _FakeView:
        self.frame_rect = rect
        return self

    def setWantsLayer_(self, value: bool) -> None:
        self.wants_layer = value

    def layer(self) -> _FakeLayer:
        return self._layer


def install(fake: Any) -> None:
    """Give an AppKit fake the panel surface the overlay needs."""
    fake.panels = []
    fake.render_failures = 0

    class NSPanel:
        @staticmethod
        def alloc() -> _FakePanel:
            panel = _FakePanel()
            panel.owner = fake
            fake.panels.append(panel)
            return panel

    fake.NSPanel = NSPanel
    fake.NSTextField = _FakeTextField
    _FakeView.built = []
    fake.NSView = _FakeView
    fake.views = _FakeView.built
    fake.CALayer = _FakeLayer
    class _FakeQuartz:
        """`CGColor` plus the `CATransaction` the pill's resize runs inside.

        The transaction is recorded rather than executed. What a test needs to
        know is the *decision* — how long, and whether animation was disabled —
        and that is exactly what a real `CATransaction` swallows into the render
        server where nothing can read it back.
        """

        transactions: ClassVar[list[dict[str, Any]]] = []
        _open: ClassVar[list[dict[str, Any]]] = []

        CATextLayer = _FakeTextLayer

        @staticmethod
        def CGColorCreateGenericGray(_gray: float, _alpha: float) -> str:
            return "cgcolor"

        class CATransaction:
            """Mirrors the real shape: a class with class methods.

            The first version of this fake invented four free functions —
            `CATransactionBegin` and friends — which do not exist in Quartz.
            The suite was green and the first transition on a real machine
            raised `AttributeError`, swallowed by the overlay's render guard
            into "the recording overlay failed and will retry". A fake whose
            *shape* is invented tests nothing about the framework; see
            `test_quartz_exposes_the_transaction_api_this_module_calls`.
            """

            @staticmethod
            def begin() -> None:
                _FakeQuartz._open.append({"duration": None, "disabled": False})

            @staticmethod
            def setAnimationDuration_(value: float) -> None:
                _FakeQuartz._open[-1]["duration"] = value

            @staticmethod
            def setDisableActions_(value: bool) -> None:
                _FakeQuartz._open[-1]["disabled"] = bool(value)

            @staticmethod
            def commit() -> None:
                _FakeQuartz.transactions.append(_FakeQuartz._open.pop())

    _FakeQuartz.transactions = []
    _FakeQuartz._open = []
    fake.Quartz = _FakeQuartz
    # macOS's Reduce Motion switch, read through `NSWorkspace`. Default off:
    # the animation is the behaviour under test almost everywhere, and a fake
    # that reduced motion by default would make every animation assertion pass
    # for the wrong reason.
    if not hasattr(fake, "reduce_motion"):
        fake.reduce_motion = False

    class _Workspace:
        @staticmethod
        def sharedWorkspace() -> Any:
            return _Workspace

        @staticmethod
        def accessibilityDisplayShouldReduceMotion() -> bool:
            return bool(fake.reduce_motion)

    fake.NSWorkspace = _Workspace
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
            "colorWithCalibratedWhite_alpha_": staticmethod(lambda _w, _a: _Color()),
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

    # Swappable, because gate finding 1's second mechanism is the panel being
    # built once against a screen that later moves. A fake that can only ever
    # report one screen cannot express the defect, and every overlay test
    # passed against exactly that fake while the operator's panel sat on a
    # display that was no longer there.
    fake.screen_frame = ((0.0, 0.0), (1440.0, 900.0))

    class _MovableScreen:
        @staticmethod
        def frame() -> tuple[tuple[float, float], tuple[float, float]]:
            """The shape PyObjC actually returns for `NSRect` -- `((x, y), (w, h))`.

            Flat 4-tuples here crashed a daemon on 2026-09-02 while every test
            passed, which is why this stays nested.
            """
            return fake.screen_frame

    class NSScreen:
        @staticmethod
        def mainScreen() -> _MovableScreen:
            return _MovableScreen()

    fake.NSScreen = NSScreen
